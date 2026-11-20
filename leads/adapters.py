"""Small, deterministic source adapters. Tool schemas remain the runtime source of truth."""

import math
import re
from dataclasses import dataclass
from django.conf import settings

from .mcp_client import MCPSourceError
from .normalization import extract_iranian_mobiles


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
        if "_mcp_structured_content" in data:
            structured_rows = _records(data["_mcp_structured_content"])
            text_rows = _records(data.get("_mcp_text_content"))
            merged = list(structured_rows)
            for text_row in text_rows:
                identity = _record_identity(text_row)
                match_index = next((index for index, row in enumerate(merged)
                                    if identity and _record_identity(row) == identity), None)
                if match_index is None:
                    if text_row not in merged:
                        merged.append(text_row)
                else:
                    merged[match_index] = _merge_record(merged[match_index], text_row)
            return merged
        for key in ("results", "places", "businesses", "items", "shops", "vendors", "companies", "offers", "products"):
            if isinstance(data.get(key), list):
                return [row for row in data[key] if isinstance(row, dict)]
        for key in ("data", "result", "response"):
            if isinstance(data.get(key), (dict, list, str)):
                nested = _records(data[key])
                if nested:
                    return nested
        return [data] if any(key in data for key in ("id", "shop_id", "company_id", "name", "title")) else []
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def _record_identity(row):
    for key in ("id", "place_id", "shop_id", "seller_id", "vendor_id", "company_id", "slug", "uuid"):
        value = row.get(key)
        if value not in (None, ""):
            return key, str(value)
    name = _first(row, "name", "title", "company_name", "shop_name")
    return ("name", str(name).casefold()) if name else None


def _merge_record(left, right):
    merged = dict(left)
    for key, value in right.items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _merge_record(merged[key], value)
        elif isinstance(merged.get(key), list) and isinstance(value, list):
            combined = list(merged[key])
            combined.extend(item for item in value if item not in combined)
            merged[key] = combined
        elif value not in (None, "", [], {}):
            merged[key] = value
    return merged


def _seller_scoped_payload(payloads, seller_id):
    """Return only seller objects that explicitly carry this seller's ID."""
    wanted = str(seller_id)
    identity_keys = {"seller_id", "seller_code", "shop_id", "shopid", "vendor_id", "vendorid", "merchant_id", "merchantid"}
    matches = []
    seen = set()

    def visit(value, parent_key=""):
        if isinstance(value, dict):
            values = {str(key).casefold().replace("-", "_"): str(item) for key, item in value.items()
                      if key.casefold().replace("-", "_") in identity_keys and item is not None}
            if re.fullmatch(r"(?:seller|shop|vendor|merchant|seller_profile|shop_profile|vendor_profile)", parent_key.casefold().replace("-", "_")):
                if value.get("id") is not None:
                    values["id"] = str(value["id"])
            if wanted in values.values():
                marker = id(value)
                if marker not in seen:
                    seen.add(marker)
                    matches.append(value)
                return
            for key, child in value.items():
                visit(child, str(key))
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child, parent_key)

    for payload in payloads:
        visit(payload)
    return matches


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


def _with_phone_filter(client, tool_name, arguments):
    """Request phone-bearing records only when the live tool schema exposes it."""
    tool = client.tools[tool_name]
    schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None) or {}
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
    result = dict(arguments)
    for key in ("with_phone", "has_phone", "phone_only", "phone_required"):
        definition = properties.get(key)
        if isinstance(definition, dict) and definition.get("type") == "boolean":
            result[key] = True
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
        tool_name = client_source_tool(client, self.source_id, "search")
        return _with_phone_filter(client, tool_name, _arguments(client, tool_name, values))


def client_source_tool(client, source_id, role):
    # The client already restricts calls to its source's allowlisted tools.
    from .mcp_client import SOURCE_REGISTRY
    return SOURCE_REGISTRY[source_id]["tools"][role]


class EmallsAdapter(SourceAdapter):
    source_id = "emalls"
    mode = "direct_shop_search_with_bounded_detail"

    async def discover(self, client, invoke, query, city, province, limit, start_page=1):
        tools = client_source_tool
        search_name = tools(client, self.source_id, "shops")
        found = []
        seen_shops = set()
        max_pages = _max_pages(client, search_name, limit, 48)
        truncated = False
        try:
            end_page = min(max_pages, start_page + settings.SEARCH_PAGES_PER_BATCH - 1)
            for page in range(start_page, end_page + 1):
                search_args = _arguments(client, search_name, {"query": query, "page": page})
                search_response = (await invoke(client, search_name, search_args)).data
                shops = _records(search_response)
                for shop in shops:
                    shop_id = _first(shop, "shop_id", "shopId", "id")
                    if not shop_id or str(shop_id) in seen_shops:
                        continue
                    seen_shops.add(str(shop_id))
                    record = dict(shop)
                    record["_source_id"] = str(shop_id)
                    record["_source_city"] = _first(shop, "city") or city
                    record["_source_province"] = _first(shop, "province") or province
                    record["_source_raw"] = {"shops_response": search_response, "shop": shop}
                    record["_phone_extraction_payload"] = {"shop": shop}
                    # Shop search can already return full contact data. Spend a detail call only
                    # when it did not provide a mobile, keeping the total MCP budget bounded.
                    profile = {}
                    if not extract_iranian_mobiles(record["_phone_extraction_payload"]):
                        profile_name = tools(client, self.source_id, "detail")
                        profile_args = _arguments(client, profile_name, {"shop_id": int(shop_id) if str(shop_id).isdigit() else str(shop_id)})
                        profile = (await invoke(client, profile_name, profile_args)).data
                        profile_payload = profile if isinstance(profile, (dict, list)) else {"value": profile}
                        record["_source_raw"]["shop_profile"] = profile_payload
                        record["_phone_extraction_payload"] = {"shop": shop, "profile": profile_payload}
                    profile_data = profile if isinstance(profile, dict) else {}
                    record["name"] = _first(profile_data, "name", "shop_name", "title") or _first(shop, "name", "shop_name", "title")
                    # Provider profile URLs are provenance, never the store's own website.
                    record["website"] = _first(profile_data, "website", "business_website", "official_website", "web") or _first(shop, "website", "business_website", "official_website", "web")
                    record["_source_city"] = _first(profile_data, "city") or record["_source_city"]
                    record["_source_province"] = _first(profile_data, "province") or record["_source_province"]
                    found.append((record, profile))
                    if len(found) >= limit:
                        return AdapterResult(found, True)
                if len(shops) < 48:
                    break
                if page == max_pages:
                    truncated = True
        except MCPSourceError as exc:
            exc.partial_records = found
            exc.truncated = truncated
            raise
        next_page = page + 1 if page == end_page and page < max_pages and len(shops) >= 48 else None
        return AdapterResult(found, bool(next_page) or truncated, next_page)


SOURCE_ADAPTERS = {
    "emalls": EmallsAdapter(),
}
