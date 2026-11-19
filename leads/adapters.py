"""Small, deterministic source adapters. Tool schemas remain the runtime source of truth."""

import math
from dataclasses import dataclass
from django.conf import settings

from .mcp_client import MCPSourceError


@dataclass
class AdapterResult:
    records: list
    truncated: bool = False
    next_page: int | None = None


def _first(data, *keys):
    if not isinstance(data, dict):
        return ""
    for key in keys:
        value = data.get(key)
        if value not in (None, "", [], {}):
            return value
    return ""


def _records(data):
    if isinstance(data, str):
        import json
        try:
            data = json.loads(data)
        except (TypeError, json.JSONDecodeError):
            return []
    if isinstance(data, dict):
        for key in ("results", "places", "businesses", "items", "shops", "vendors", "companies", "offers", "products"):
            if isinstance(data.get(key), list):
                return [row for row in data[key] if isinstance(row, dict)]
        return [data] if any(key in data for key in ("id", "shop_id", "company_id", "name", "title")) else []
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def _arguments(client, tool_name, values):
    """Map normalized query values to fields present in the live MCP tool schema."""
    tool = client.tools[tool_name]
    schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None) or {}
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
    aliases = {
        "query": ("query", "search", "what", "name", "activity"),
        "city": ("city",),
        "province": ("province",),
        "page": ("page",),
        "limit": ("limit", "page_size", "per_page", "size"),
        "product_id": ("product_id", "product", "id"),
        "shop_id": ("shop_id", "vendor_id", "vendor", "id"),
        "company_id": ("company_id", "national_id", "id"),
        "seller_id": ("seller_id", "seller_code", "shop_id", "vendor_id", "id"),
    }
    result = {}
    for key, value in values.items():
        for candidate in aliases.get(key, (key,)):
            if candidate in properties and candidate not in result:
                definition = properties[candidate]
                value_type = definition.get("type") if isinstance(definition, dict) else None
                if not value_type and isinstance(definition, dict):
                    value_type = next((option.get("type") for option in definition.get("anyOf", []) if isinstance(option, dict) and option.get("type") not in {"null", None}), None)
                if value_type == "integer" and isinstance(value, str) and value.isdigit():
                    value = int(value)
                result[candidate] = value
                break
    required = schema.get("required", []) if isinstance(schema, dict) else []
    missing = [name for name in required if name not in result]
    if missing:
        raise MCPSourceError(f"{tool_name} schema requires unsupported field(s): {', '.join(missing)}")
    return result


def _max_pages(client, tool_name, requested, page_size):
    """Respect the live page schema and a finite application ceiling."""
    tool = client.tools[tool_name]
    schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None) or {}
    properties = schema.get("properties") or {} if isinstance(schema, dict) else {}
    if "page" not in properties:
        return 1
    page = properties.get("page", {})
    upper = page.get("maximum", 100) if isinstance(page, dict) else 100
    minimum = page.get("minimum", 1) if isinstance(page, dict) else 1
    page_count_limit = int(upper) - int(minimum) + 1
    target_pages = math.ceil(max(1, settings.SEARCH_MAX_RESULTS) / max(1, page_size))
    return max(1, min(page_count_limit, int(settings.SEARCH_MAX_PAGES_PER_SOURCE), target_pages))


class SourceAdapter:
    source_id = ""
    mode = ""

    async def discover(self, client, invoke, query, city, province, limit, start_page=1):
        raise NotImplementedError

    def _search_args(self, client, query, city, province, limit, page=1):
        values = {"query": query, "city": city, "province": province, "page": page, "limit": limit}
        return _arguments(client, client_source_tool(client, self.source_id, "search"), values)


def client_source_tool(client, source_id, role):
    # The client already restricts calls to its source's allowlisted tools.
    from .mcp_client import SOURCE_REGISTRY
    return SOURCE_REGISTRY[source_id]["tools"][role]


class EmallsAdapter(SourceAdapter):
    source_id = "emalls"
    mode = "product_offers_to_shop_profiles"

    async def discover(self, client, invoke, query, city, province, limit, start_page=1):
        tools = client_source_tool
        search_name = tools(client, self.source_id, "search")
        found = []
        seen_shops = set()
        page_size = min(10, max(1, limit))
        max_pages = _max_pages(client, search_name, limit, page_size)
        truncated = False
        try:
            end_page = min(max_pages, start_page + settings.SEARCH_PAGES_PER_BATCH - 1)
            for page in range(start_page, end_page + 1):
                products = _records((await invoke(client, search_name, self._search_args(client, query, city, province, page_size, page=page))).data)
                for product in products:
                    product_id = _first(product, "id", "product_id", "productId")
                    if not product_id:
                        continue
                    offers_name = tools(client, self.source_id, "offers")
                    offers_args = _arguments(client, offers_name, {"product_id": str(product_id), "city": city})
                    offers = _records((await invoke(client, offers_name, offers_args)).data)
                    for offer in offers:
                        shop_id = _first(offer, "shop_id", "shopId", "id")
                        if not shop_id or str(shop_id) in seen_shops:
                            continue
                        seen_shops.add(str(shop_id))
                        profile_name = tools(client, self.source_id, "detail")
                        profile_args = _arguments(client, profile_name, {"shop_id": str(shop_id)})
                        profile = (await invoke(client, profile_name, profile_args)).data
                        record = dict(offer)
                        record["name"] = _first(profile if isinstance(profile, dict) else {}, "name", "shop_name", "title") or _first(offer, "shop_name", "shop", "merchant") or _first(product, "shop_name")
                        record["_source_id"] = str(shop_id)
                        record["_source_city"] = _first(profile if isinstance(profile, dict) else {}, "city") or _first(offer, "city") or city
                        record["_source_province"] = _first(profile if isinstance(profile, dict) else {}, "province") or _first(offer, "province") or province
                        record["_source_raw"] = {"product": product, "offer": offer}
                        found.append((record, profile))
                        if len(found) >= limit:
                            return AdapterResult(found, True)
                if len(products) < page_size:
                    break
                if page == max_pages:
                    truncated = True
        except MCPSourceError as exc:
            exc.partial_records = found
            exc.truncated = truncated
            raise
        next_page = page + 1 if page == end_page and page < max_pages and len(products) >= page_size else None
        return AdapterResult(found, bool(next_page) or truncated, next_page)


class BasalamAdapter(SourceAdapter):
    source_id = "basalam"
    mode = "product_to_public_vendor_profile"

    async def discover(self, client, invoke, query, city, province, limit, start_page=1):
        search_name = client_source_tool(client, self.source_id, "search")
        found = []
        seen_shops = set()
        detail_name = client_source_tool(client, self.source_id, "detail")
        page_size = min(20, max(1, limit))
        max_pages = _max_pages(client, search_name, limit, page_size)
        truncated = False
        try:
            end_page = min(max_pages, start_page + settings.SEARCH_PAGES_PER_BATCH - 1)
            for page in range(start_page, end_page + 1):
                products = _records((await invoke(client, search_name, self._search_args(client, query, city, province, page_size, page=page))).data)
                for product in products:
                    shop_id = _first(product, "shop_id", "vendor_id", "vendorId")
                    if not shop_id or str(shop_id) in seen_shops:
                        continue
                    seen_shops.add(str(shop_id))
                    args = _arguments(client, detail_name, {"shop_id": str(shop_id)})
                    profile = (await invoke(client, detail_name, args)).data
                    record = dict(product)
                    record["_source_id"] = str(shop_id)
                    record["name"] = _first(profile if isinstance(profile, dict) else {}, "name", "vendor_name", "title") or _first(product, "shop_name", "vendor_name")
                    record["_source_city"] = _first(profile if isinstance(profile, dict) else {}, "city")
                    record["_source_province"] = _first(profile if isinstance(profile, dict) else {}, "province")
                    record["_source_raw"] = {"product": product}
                    found.append((record, profile))
                    if len(found) >= limit:
                        return AdapterResult(found, True)
                if len(products) < page_size:
                    break
                if page == max_pages:
                    truncated = True
        except MCPSourceError as exc:
            exc.partial_records = found
            exc.truncated = truncated
            raise
        next_page = page + 1 if page == end_page and page < max_pages and len(products) >= page_size else None
        return AdapterResult(found, bool(next_page) or truncated, next_page)


class RasmioAdapter(SourceAdapter):
    source_id = "rasmio"
    mode = "company_registry_search"

    async def discover(self, client, invoke, query, city, province, limit, start_page=1):
        search_name = client_source_tool(client, self.source_id, "search")
        # Guest profile opens are capped by the upstream service; search records already include public ids.
        found = []
        page_size = min(20, max(1, limit))
        max_pages = _max_pages(client, search_name, limit, page_size)
        truncated = False
        try:
            end_page = min(max_pages, start_page + settings.SEARCH_PAGES_PER_BATCH - 1)
            for page in range(start_page, end_page + 1):
                args = _arguments(client, search_name, {"query": query, "city": city, "province": province, "page": page, "limit": page_size})
                rows = _records((await invoke(client, search_name, args)).data)
                for row in rows:
                    company_id = _first(row, "company_id", "national_id", "nationalId", "id")
                    if not company_id:
                        continue
                    record = dict(row)
                    record["_source_id"] = str(company_id)
                    record["national_id"] = str(company_id)
                    record["name"] = _first(row, "name", "company_name", "title")
                    record["_source_city"] = _first(row, "city") or city
                    record["_source_province"] = _first(row, "province") or province
                    found.append((record, {}))
                    if len(found) >= limit:
                        return AdapterResult(found, True)
                if len(rows) < page_size:
                    break
                if page == max_pages:
                    truncated = True
        except MCPSourceError as exc:
            exc.partial_records = found
            exc.truncated = truncated
            raise
        next_page = page + 1 if page == end_page and page < max_pages and len(rows) >= page_size else None
        return AdapterResult(found, bool(next_page) or truncated, next_page)


def _nested_rows(data, keys):
    """Find seller/company rows in documented nested MCP result shapes."""
    if isinstance(data, list):
        return [row for item in data for row in _nested_rows(item, keys)]
    if not isinstance(data, dict):
        return []
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    if _first(data, "company_id", "seller_id", "seller_code", "shop_id", "vendor_id", "id") and _first(data, "name", "company_name", "seller", "seller_name", "shop_name", "vendor_name", "title"):
        return [data]
    result = []
    for value in data.values():
        if isinstance(value, (dict, list)):
            result.extend(_nested_rows(value, keys))
    return result


class TorobShopAdapter(SourceAdapter):
    """Search actual shop records; no product card is misrepresented as a shop."""
    source_id = "torob"
    mode = "direct_shop_search"

    async def discover(self, client, invoke, query, city, province, limit, start_page=0):
        tool = client_source_tool(client, self.source_id, "search")
        page_size = min(30, max(1, limit))
        page_count = _max_pages(client, tool, limit, page_size)
        found, seen = [], set()
        end_page = min(page_count - 1, start_page + settings.SEARCH_PAGES_PER_BATCH - 1)
        for page in range(start_page, end_page + 1):
            args = _arguments(client, tool, {"query": query, "city": city or province or None, "kind": "all", "page": page, "limit": page_size})
            rows = _nested_rows((await invoke(client, tool, args)).data, ("shops", "results", "stores", "items"))
            for row in rows:
                shop_id = _first(row, "shop_id", "id", "seller_id")
                name = _first(row, "name", "shop_name", "seller_name", "title")
                if not shop_id or not name or str(shop_id) in seen:
                    continue
                seen.add(str(shop_id))
                record = dict(row, _source_id=str(shop_id), name=name, _source_city=_first(row, "city") or city,
                              _source_province=_first(row, "province") or province)
                found.append((record, row))
                if len(found) >= limit:
                    return AdapterResult(found, True)
            if len(rows) < page_size:
                return AdapterResult(found, False)
        next_page = page + 1 if page == end_page and page < page_count - 1 else None
        return AdapterResult(found, bool(next_page is not None), next_page)


class MarketplaceProductAdapter(SourceAdapter):
    """Find shops only through seller offers returned for matching products."""
    mode = "product_search_to_seller_offers"
    seller_keys = ("offers", "seller_offers", "product_offers", "sellers", "vendors", "shops", "merchants", "listings")

    async def discover(self, client, invoke, query, city, province, limit, start_page=1):
        search_tool = client_source_tool(client, self.source_id, "search")
        detail_tool = client_source_tool(client, self.source_id, "detail")
        page_size = min(10, max(1, limit))
        page_count = _max_pages(client, search_tool, limit, page_size)
        found, seen = [], set()
        try:
            end_page = min(page_count, start_page + settings.SEARCH_PAGES_PER_BATCH - 1)
            for page in range(start_page, end_page + 1):
                search_args = _arguments(client, search_tool, {"query": query, "page": page, "limit": page_size})
                products = _records((await invoke(client, search_tool, search_args)).data)
                for product in products:
                    product_id = _first(product, "product_id", "id", "productId") if self.source_id == "snappshop" else _first(product, "id", "product_id", "productId")
                    if not product_id:
                        continue
                    detail_values = {"product": str(product_id)} if self.source_id == "snappshop" else {"product_id": product_id}
                    detail_args = _arguments(client, detail_tool, detail_values)
                    detail = (await invoke(client, detail_tool, detail_args)).data
                    offers = _nested_rows(detail, self.seller_keys)
                    for offer in offers:
                        seller_id = _first(offer, "seller_id", "seller_code", "shop_id", "vendor_id", "merchant_id", "id")
                        seller_name = _first(offer, "seller_name", "seller", "shop_name", "vendor_name", "merchant_name", "name", "title")
                        if not seller_id or not seller_name or str(seller_id) in seen:
                            continue
                        seen.add(str(seller_id))
                        row = dict(offer, _source_id=str(seller_id), name=seller_name,
                                   _source_city=_first(offer, "city") or city,
                                   _source_province=_first(offer, "province") or province,
                                   _source_raw={"seller_offer": offer})
                        found.append((row, offer))
                        if len(found) >= limit:
                            return AdapterResult(found, True)
                if len(products) < page_size:
                    return AdapterResult(found, False)
        except MCPSourceError as exc:
            exc.partial_records = found
            raise
        next_page = page + 1 if page == end_page and page < page_count else None
        return AdapterResult(found, bool(next_page), next_page)


class DigikalaAdapter(MarketplaceProductAdapter):
    source_id = "digikala"


class SnappShopAdapter(MarketplaceProductAdapter):
    source_id = "snappshop"


class IranJobsCompanyAdapter(SourceAdapter):
    source_id = "iran_jobs"
    mode = "company_search_with_job_evidence"

    async def discover(self, client, invoke, query, city, province, limit, start_page=1):
        tool = client_source_tool(client, self.source_id, "search")
        page_count = _max_pages(client, tool, limit, 20)
        found, seen = [], set()
        end_page = min(page_count, start_page + settings.SEARCH_PAGES_PER_BATCH - 1)
        for page in range(start_page, end_page + 1):
            args = _arguments(client, tool, {"query": query, "page": page, "site": "all"})
            companies = _nested_rows((await invoke(client, tool, args)).data, ("companies", "results", "items", "irantalent", "jobinja", "jobvision"))
            for company in companies:
                name = _first(company, "name", "company_name", "title")
                identifier = _first(company, "company_id", "id", "uuid", "national_id")
                if not identifier or not name or str(identifier) in seen:
                    continue
                seen.add(str(identifier))
                record = dict(company, _source_id=str(identifier), name=name,
                              _source_city=_first(company, "city", "location") or city,
                              _source_province=_first(company, "province") or province)
                found.append((record, company))
                if len(found) >= limit:
                    return AdapterResult(found, True)
            if len(companies) < 20:
                return AdapterResult(found, False)
        next_page = page + 1 if page == end_page and page < page_count else None
        return AdapterResult(found, bool(next_page), next_page)


class QueraCompanyAdapter(SourceAdapter):
    source_id = "quera"
    mode = "company_search_and_public_profile"

    async def discover(self, client, invoke, query, city, province, limit, start_page=1):
        search_tool = client_source_tool(client, self.source_id, "search")
        detail_tool = client_source_tool(client, self.source_id, "detail")
        page_count = _max_pages(client, search_tool, limit, 10)
        end_page = min(page_count, start_page + settings.SEARCH_PAGES_PER_BATCH - 1)
        found, seen = [], set()
        try:
            for page in range(start_page, end_page + 1):
                args = _arguments(client, search_tool, {"query": query, "city": city or province or None, "page": page})
                companies = _records((await invoke(client, search_tool, args)).data)
                for company in companies:
                    slug = _first(company, "slug", "company_id", "id")
                    name = _first(company, "name", "company_name", "title")
                    if not slug or not name or str(slug) in seen:
                        continue
                    seen.add(str(slug))
                    profile_args = _arguments(client, detail_tool, {"slug": str(slug)})
                    profile = (await invoke(client, detail_tool, profile_args)).data
                    details = profile if isinstance(profile, dict) else {}
                    record = dict(company)
                    record.update({key: value for key, value in details.items() if value not in (None, "", [], {})})
                    record.update(_source_id=str(slug), name=_first(details, "name", "company_name") or name,
                                  _source_city=_first(details, "city") or city,
                                  _source_province=_first(details, "province") or province)
                    record["_source_raw"] = {"company": company}
                    found.append((record, details))
                    if len(found) >= limit:
                        return AdapterResult(found, True)
                if len(companies) < 10:
                    return AdapterResult(found, False)
        except MCPSourceError as exc:
            exc.partial_records = found
            raise
        next_page = page + 1 if page == end_page and page < page_count else None
        return AdapterResult(found, bool(next_page), next_page)


SOURCE_ADAPTERS = {
    "emalls": EmallsAdapter(),
    "basalam": BasalamAdapter(),
    "rasmio": RasmioAdapter(),
    "torob": TorobShopAdapter(),
    "iran_jobs": IranJobsCompanyAdapter(),
    "quera": QueraCompanyAdapter(),
    "digikala": DigikalaAdapter(),
    "snappshop": SnappShopAdapter(),
}
