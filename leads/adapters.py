"""Small, deterministic source adapters. Tool schemas remain the runtime source of truth."""

import math
from dataclasses import dataclass

from .mcp_client import MCPSourceError


@dataclass
class AdapterResult:
    records: list
    truncated: bool = False


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
        "query": ("query", "what", "name", "activity"),
        "city": ("city",),
        "province": ("province",),
        "page": ("page",),
        "limit": ("limit", "page_size", "per_page", "size"),
        "product_id": ("product_id", "product", "id"),
        "shop_id": ("shop_id", "vendor_id", "vendor", "id"),
        "company_id": ("company_id", "national_id", "id"),
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


class SourceAdapter:
    source_id = ""
    mode = ""

    async def discover(self, client, invoke, query, city, province, limit):
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

    async def discover(self, client, invoke, query, city, province, limit):
        tools = client_source_tool
        search_name = tools(client, self.source_id, "search")
        found = []
        seen_shops = set()
        page_size = min(10, max(1, limit))
        max_pages = min(5, max(1, math.ceil(limit / page_size)))
        truncated = False
        try:
            for page in range(1, max_pages + 1):
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
        return AdapterResult(found, truncated)


class BasalamAdapter(SourceAdapter):
    source_id = "basalam"
    mode = "product_to_public_vendor_profile"

    async def discover(self, client, invoke, query, city, province, limit):
        search_name = client_source_tool(client, self.source_id, "search")
        found = []
        seen_shops = set()
        detail_name = client_source_tool(client, self.source_id, "detail")
        page_size = min(20, max(1, limit))
        max_pages = min(5, max(1, math.ceil(limit / page_size)))
        truncated = False
        try:
            for page in range(1, max_pages + 1):
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
        return AdapterResult(found, truncated)


class RasmioAdapter(SourceAdapter):
    source_id = "rasmio"
    mode = "company_registry_search"

    async def discover(self, client, invoke, query, city, province, limit):
        search_name = client_source_tool(client, self.source_id, "search")
        # Guest profile opens are capped by the upstream service; search records already include public ids.
        found = []
        page_size = min(20, max(1, limit))
        max_pages = min(5, max(1, math.ceil(limit / page_size)))
        truncated = False
        try:
            for page in range(1, max_pages + 1):
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
        return AdapterResult(found, truncated)


SOURCE_ADAPTERS = {
    "emalls": EmallsAdapter(),
    "basalam": BasalamAdapter(),
    "rasmio": RasmioAdapter(),
}
