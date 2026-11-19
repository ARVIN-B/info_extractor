import asyncio
from datetime import datetime, timezone as datetime_timezone
from email.utils import parsedate_to_datetime
import json
import logging
import os
import random
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass

from django.conf import settings
from jsonschema import Draft202012Validator, ValidationError
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from redis import Redis

logger = logging.getLogger(__name__)

SOURCE_REGISTRY = {
    "neshan": {
        "package": "neshan-mcp==0.2.0",
        "tools": {"search": "ns_search", "detail": "ns_place"},
        "proxy_env": "NESHAN_MCP_PROXY",
        "display_name": "نشان",
        "kind": "local_business",
        "categories": ["local", "all"],
        "fields": ["name", "category", "address", "phone", "website", "location"],
        "coverage": "شهرهای پشتیبانی‌شده در ابزار نشان؛ نتایج محدود به سقف ابزار",
        "access": "unofficial public read-only MCP",
        "fallback_group": "local_business", "fallback_order": 2,
        "detail_min_interval_seconds": 6.0,
    },
    "balad": {
        "package": "balad-mcp==0.2.0",
        "tools": {"search": "bl_search", "nearby": "bl_nearby", "detail": "bl_place"},
        "proxy_env": "BALAD_MCP_PROXY",
        "display_name": "بلد",
        "kind": "local_business",
        "categories": ["local", "all"],
        "fields": ["name", "category", "address", "phone", "website", "location"],
        "coverage": "شهرهای تحت پوشش ابزار بلد",
        "access": "unofficial public read-only MCP",
        "fallback_group": "local_business", "fallback_order": 1,
        "detail_min_interval_seconds": float(settings.BALAD_DETAIL_MIN_INTERVAL_SECONDS),
    },
    "emalls": {
        "package": "emalls-ir-mcp==0.2.0",
        "tools": {"search": "em_search", "offers": "em_offers", "shops": "em_shops", "detail": "em_shop"},
        "proxy_env": "EMALLS_MCP_PROXY",
        "display_name": "ایمالز",
        "kind": "online_shop",
        "categories": ["online_shop", "retail", "all"],
        "fields": ["name", "website", "address", "phone", "public shop profile"],
        "coverage": "فروشگاه‌های فهرست‌شده در ایمالز؛ جست‌وجو با نام فروشگاه",
        "access": "unofficial public read-only MCP",
        "fallback_group": "online_shop", "fallback_order": 1,
    },
    "basalam": {
        "package": "basalam-mcp==0.2.0",
        "tools": {"search": "bs_search", "detail": "bs_vendor"},
        "proxy_env": "BASALAM_MCP_PROXY",
        "display_name": "باسلام",
        "kind": "marketplace_seller",
        "categories": ["online_shop", "retail", "home_business", "all"],
        "fields": ["name", "public vendor profile", "listing lead"],
        "coverage": "غرفه‌ها و فروشندگان حاضر در بازارگاه؛ تماس مستقل تضمین نمی‌شود",
        "access": "unofficial public read-only MCP",
        "fallback_group": "marketplace_seller", "fallback_order": 1,
    },
    "rasmio": {
        "package": "rasmio-mcp==0.2.0",
        "tools": {"search": "rs_search_companies", "detail": "rs_company"},
        "proxy_env": "RASMIO_MCP_PROXY",
        "display_name": "رسمیو",
        "kind": "registered_company",
        "categories": ["company", "technology", "industry", "all"],
        "fields": ["name", "national_id", "registration_id", "activity", "address"],
        "coverage": "شرکت‌های ثبت‌شده؛ جست‌وجو عمومی، بازکردن پروندهٔ مهمان بسیار محدود",
        "access": "unofficial public registry MCP; guest detail quota",
    },
    "torob": {
        "package": "torob-mcp==0.2.2", "executable": "torob-mcp", "tools": {"search": "tb_find_shops"},
        "proxy_env": "TOROB_MCP_PROXY", "display_name": "ترب", "kind": "marketplace_seller",
        "categories": ["online_shop", "retail", "all"], "fields": ["name", "shop_id", "public shop profile", "website when published"],
        "coverage": "فروشگاه‌های فهرست‌شده در ترب؛ اطلاعات تماس مستقل تضمین نمی‌شود", "access": "unofficial public read-only MCP",
        "license": "PolyForm-Noncommercial-1.0.0",
        "fallback_group": "online_shop", "capabilities": ["shop_search", "seller_identity"], "enabled": True,
    },
    "iran_jobs": {
        "package": "iran-jobs-mcp==0.2.1", "executable": "iran-jobs-mcp", "tools": {"search": "job_companies"},
        "proxy_env": "IRAN_JOBS_MCP_PROXY", "display_name": "ایران جابز", "kind": "recruitment_company",
        "categories": ["recruitment_company", "company", "all"], "fields": ["name", "company profile", "industry", "city", "website", "public jobs"],
        "coverage": "شرکت‌های IranTalent، Jobinja و Jobvision؛ اطلاعات تماس فقط در صورت انتشار", "access": "unofficial public read-only MCP",
        "fallback_group": "recruitment_company", "capabilities": ["company_search", "job_evidence"], "enabled": True,
        "license": "PolyForm-Noncommercial-1.0.0",
    },
    "quera": {
        "package": "quera-mcp==0.2.0", "executable": "quera-mcp", "tools": {"search": "qr_companies", "detail": "qr_company"},
        "proxy_env": "QUERA_MCP_PROXY", "display_name": "کوئرا", "kind": "recruitment_company",
        "categories": ["recruitment_company", "technology", "company", "all"], "fields": ["name", "public company profile", "industry", "city", "address", "website", "social links"],
        "coverage": "شرکت‌های دارای پروفایل عمومی در کوئرا مگنت؛ تمرکز بر شرکت‌های فناوری", "access": "unofficial public read-only MCP; MIT",
        "fallback_group": "recruitment_company", "fallback_order": 2, "capabilities": ["company_search", "company_profile", "public_business_links"], "enabled": True,
    },
    "digikala": {
        "package": "digikala-mcp==0.6.2", "executable": "digikala-mcp", "tools": {"search": "dk_search", "detail": "dk_product"},
        "proxy_env": "DIGIKALA_MCP_PROXY", "display_name": "دیجی‌کالا", "kind": "marketplace_seller",
        "categories": ["online_shop", "retail", "all"], "fields": ["name", "seller_id", "public seller profile", "website when published"],
        "coverage": "فروشندگان محصولات جست‌وجوشده؛ وب‌سایت یا تلفن مستقل تضمین نمی‌شود", "access": "unofficial public read-only MCP",
        "fallback_group": "online_shop", "capabilities": ["product_search", "seller_offers"], "enabled": True,
        "license": "PolyForm-Noncommercial-1.0.0",
    },
    "snappshop": {
        "package": "snappshop-mcp==0.2.1", "executable": "snappshop-mcp", "tools": {"search": "ss_search", "detail": "ss_product"},
        "proxy_env": "SNAPPSHOP_MCP_PROXY", "display_name": "اسنپ‌شاپ", "kind": "marketplace_seller",
        "categories": ["online_shop", "retail", "all"], "fields": ["name", "seller_id", "public seller profile", "website when published"],
        "coverage": "فروشندگان محصولات جست‌وجوشده؛ ممکن است به دسترسی شبکه‌ای ایران نیاز باشد", "access": "unofficial public read-only MCP",
        "fallback_group": "online_shop", "capabilities": ["product_search", "seller_offers"], "enabled": True,
        "license": "PolyForm-Noncommercial-1.0.0",
    },
}

# Keep a complete, stable public metadata contract for forms, reports and adapters.
for _source_id, _metadata in SOURCE_REGISTRY.items():
    _metadata.setdefault("executable", _metadata.get("package", "").split("==", 1)[0])
    _metadata.setdefault("source_type", _metadata.get("kind", "business_directory"))
    _metadata.setdefault("capabilities", ["business_search"])
    _metadata.setdefault("supported_fields", _metadata.get("fields", []))
    _metadata.setdefault("rate_limit_policy", "honor retry-after; persistent shared cooldown; no long inline wait")
    _metadata.setdefault("retry_policy", "one bounded retry for transient errors; short rate-limit retry only when configured")
    _metadata.setdefault("timeout_policy", "SOURCE_TIMEOUT_SECONDS")
    _metadata.setdefault("fallback_group", "")
    _metadata.setdefault("fallback_order", 99)
    _metadata["enabled"] = _source_id in settings.ENABLED_MCP_SOURCES
    _metadata.setdefault("health_status", "not_checked")


class MCPSourceError(Exception):
    """Safe, source-specific MCP error suitable for the job log."""

    def __init__(self, message, duration_ms=0, retryable=False, rate_limited=False, retry_after_seconds=None, error_type=None):
        safe_message = re.sub(r"(https?://)[^/@\s]+:[^/@\s]+@", r"\1[redacted]@", str(message))
        safe_message = re.sub(r"(?i)(api[_-]?key|token|authorization)(\s*[:=]\s*)[^\s,;]+", r"\1\2[redacted]", safe_message)
        super().__init__(safe_message)
        self.duration_ms = duration_ms
        self.retryable = retryable
        detected, detected_after = _rate_limit_details(safe_message)
        self.rate_limited = rate_limited or detected
        self.retry_after_seconds = retry_after_seconds or _rate_limit_reset_seconds(safe_message) or detected_after
        quota_type = "monthly_quota_exceeded" if "monthly" in safe_message.lower() else "daily_quota_exceeded" if "daily" in safe_message.lower() else "daily_quota_exceeded" if "quota exceeded" in safe_message.lower() else ""
        self.error_type = error_type or (quota_type or ("rate_limit" if self.rate_limited else "source_timeout" if "timed out" in safe_message.lower() else "source_unavailable" if retryable else "tool_schema_error" if "tool" in safe_message.lower() or "schema" in safe_message.lower() else "internal_error"))
        self.retry_count = 0


class MCPBudgetExhausted(Exception):
    """Expected internal budget boundary, not an upstream source error."""

    def __init__(self, message, global_budget=False):
        super().__init__(message)
        self.error_type = "global_budget_exhausted" if global_budget else "fair_share_exhausted"


def _rate_limit_details(message):
    text = str(message)
    limited = bool(re.search(r"\b429\b|rate[ -]?limit|too many requests|daily quota|monthly quota|quota exceeded", text, re.IGNORECASE))
    if not limited:
        return False, None
    retry_after = re.search(
        r"retry[- ]after\s*[:=]?\s*(\d+|[A-Za-z]{3},\s+\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\s+[\d:]+\s+GMT)",
        text, re.IGNORECASE,
    )
    if retry_after:
        raw = retry_after.group(1)
        if raw.isdigit():
            return True, max(1, int(raw))
        try:
            parsed = parsedate_to_datetime(raw)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=datetime_timezone.utc)
            seconds = int((parsed - datetime.now(datetime_timezone.utc)).total_seconds())
            return True, max(1, seconds)
        except (TypeError, ValueError, OverflowError):
            pass
    wait = re.search(r"wait\s+(\d+)\s*(seconds?|minutes?|hours?|days?)", text, re.IGNORECASE)
    if wait:
        amount = int(wait.group(1))
        unit = wait.group(2).lower()
        seconds = amount * (86400 if unit.startswith("day") else 3600 if unit.startswith("hour") else 60 if unit.startswith("minute") else 1)
        return True, max(1, seconds)
    if re.search(r"wait\s+a\s+minute", text, re.IGNORECASE):
        return True, 60
    if re.search(r"daily quota|monthly quota|quota exceeded", text, re.IGNORECASE):
        return True, None
    return True, 60


def _rate_limit_reset_seconds(message):
    match = re.search(r"(?i)(?:x-ratelimit-reset|rate.?limit.?reset|reset(?:s|_at|_time)?|quota.?reset)\s*[:=]\s*(\d{10,13})", str(message))
    if not match:
        return None
    value = int(match.group(1))
    timestamp = value / 1000 if value > 10**12 else value
    return max(1, int(timestamp - datetime.now(datetime_timezone.utc).timestamp()))


@dataclass
class MCPCallResult:
    data: object
    duration_ms: int


def _plain_response_data(value, seen=None):
    """Convert MCP/Pydantic response containers while retaining nested values."""
    seen = seen if seen is not None else set()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    marker = id(value)
    if marker in seen:
        return {"__cycle_reference__": True}
    if isinstance(value, dict):
        seen.add(marker)
        try:
            return {str(key): _plain_response_data(child, seen) for key, child in value.items()}
        finally:
            seen.remove(marker)
    if isinstance(value, (list, tuple)):
        seen.add(marker)
        try:
            return [_plain_response_data(child, seen) for child in value]
        finally:
            seen.remove(marker)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            seen.add(marker)
            return _plain_response_data(model_dump(mode="json"), seen)
        except Exception:
            pass
        finally:
            seen.discard(marker)
    if hasattr(value, "__dict__"):
        try:
            seen.add(marker)
            return {str(key): _plain_response_data(child, seen) for key, child in vars(value).items() if not key.startswith("_")}
        except (TypeError, AttributeError):
            pass
        finally:
            seen.discard(marker)
    return str(value)


def decode_result(result):
    is_error = getattr(result, "isError", None)
    if is_error is None:
        is_error = getattr(result, "is_error", False)
    if is_error:
        details = "; ".join(getattr(item, "text", "") for item in result.content if getattr(item, "text", ""))
        details = details[:1000] or "MCP tool returned an error"
        rate_limited, retry_after = _rate_limit_details(details)
        raise MCPSourceError(details, rate_limited=rate_limited, retry_after_seconds=retry_after)
    structured = getattr(result, "structuredContent", None)
    if structured is None:
        structured = getattr(result, "structured_content", None)
    if structured is not None:
        structured = _plain_response_data(structured)
    values = []
    for item in getattr(result, "content", []):
        if getattr(item, "type", "") == "text":
            try:
                values.append(json.loads(item.text))
            except (TypeError, json.JSONDecodeError):
                values.append(item.text)
    text_data = _plain_response_data(values[0] if len(values) == 1 else values)
    if structured is not None:
        # Keep all MCP representations. Some servers provide summary fields in
        # structuredContent and additional public fields in text content.
        if values:
            return {"_mcp_structured_content": structured, "_mcp_text_content": text_data}
        return structured
    return text_data


@asynccontextmanager
async def source_session(source_name, enforce_rate_limit=False):
    config = SOURCE_REGISTRY.get(source_name)
    if not config:
        raise MCPSourceError(f"Source is not configured: {source_name}")
    command = settings.MCP_SERVER_PATHS.get(source_name)
    if not command:
        raise MCPSourceError(f"{source_name} MCP executable is not configured in the project .venv")
    child_env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "TEMP", "TMP") if key in os.environ}
    if proxy := os.environ.get(config["proxy_env"]):
        child_env[config["proxy_env"]] = proxy
    server = StdioServerParameters(command=command, args=[], env=child_env)
    try:
        async with stdio_client(server) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                async with asyncio.timeout(settings.SOURCE_TIMEOUT_SECONDS):
                    await session.initialize()
                    listed = await session.list_tools()
                tool_map = {tool.name: tool for tool in listed.tools}
                missing = set(config["tools"].values()) - set(tool_map)
                if missing:
                    raise MCPSourceError(f"{source_name} MCP lacks expected tool(s): {', '.join(sorted(missing))}")
                yield MCPToolClient(
                    source_name, session, tool_map,
                    distributed_limit=enforce_rate_limit and settings.MCP_DISTRIBUTED_SOURCE_LIMITS,
                )
    except TimeoutError as exc:
        raise MCPSourceError(f"{source_name} MCP server timed out during startup or shutdown") from exc
    except FileNotFoundError as exc:
        raise MCPSourceError(f"{source_name} MCP executable is missing from the project .venv") from exc
    except MCPSourceError:
        raise
    except Exception as exc:
        nested = _nested_source_error(exc)
        if nested:
            raise nested from exc
        logger.exception("MCP session failed for source %s", source_name)
        retryable = isinstance(exc, (ConnectionError, OSError, TimeoutError))
        raise MCPSourceError(f"{source_name} MCP connection failed: {type(exc).__name__}", retryable=retryable) from exc


def _nested_source_error(error):
    """Unwrap MCP errors raised through AnyIO task groups during session cleanup."""
    children = getattr(error, "exceptions", ())
    for child in children:
        if isinstance(child, MCPSourceError):
            return child
        nested = _nested_source_error(child)
        if nested:
            return nested
    return None


class MCPToolClient:
    def __init__(self, source_name, session, tools, distributed_limit=False):
        self.source_name = source_name
        self.session = session
        self.tools = tools
        self.request_count = 0
        self.distributed_limit = distributed_limit
        self.request_allowance = None

    async def _call_with_source_limit(self, tool_name, arguments):
        config = SOURCE_REGISTRY[self.source_name]
        is_detail = tool_name == config["tools"].get("detail")
        detail_interval = float(config.get("detail_min_interval_seconds", 0)) if is_detail else 0
        if not self.distributed_limit:
            response = await self.session.call_tool(tool_name, arguments)
            if detail_interval:
                await asyncio.sleep(detail_interval)
            return response
        redis_client = Redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=5, socket_timeout=5)
        lock = redis_client.lock(
            f"info-extractor:mcp-source:{self.source_name}",
            timeout=settings.SOURCE_TIMEOUT_SECONDS + 10,
            blocking_timeout=settings.SOURCE_LOCK_WAIT_SECONDS,
            thread_local=False,
        )
        acquired = False
        try:
            acquired = await asyncio.to_thread(lock.acquire, blocking=True)
            if not acquired:
                raise MCPSourceError(f"Timed out waiting for the {self.source_name} source concurrency slot")
            response = await self.session.call_tool(tool_name, arguments)
            if detail_interval:
                # Keep the cross-worker source lock during the spacing interval.
                await asyncio.sleep(detail_interval)
            return response
        except MCPSourceError:
            raise
        except Exception as exc:
            raise MCPSourceError(f"{self.source_name} source rate-limit coordination failed: {type(exc).__name__}", retryable=True) from exc
        finally:
            if acquired:
                try:
                    await asyncio.to_thread(lock.release)
                except Exception:
                    logger.exception("Could not release source concurrency lock for %s", self.source_name)
            await asyncio.to_thread(redis_client.close)

    async def call(self, tool_name, arguments):
        allowed = set(SOURCE_REGISTRY[self.source_name]["tools"].values())
        if tool_name not in allowed:
            raise MCPSourceError(f"Tool {tool_name} is not allowed for {self.source_name}")
        tool = self.tools[tool_name]
        schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None) or {"type": "object", "properties": {}}
        try:
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(schema).validate(arguments)
        except ValidationError as exc:
            raise MCPSourceError(f"Invalid arguments for {tool_name}: {exc.message}") from exc
        except Exception as exc:
            raise MCPSourceError(f"Invalid input schema for {tool_name}") from exc
        loop = asyncio.get_running_loop()
        started = loop.time()
        attempts_started_at = self.request_count
        attempts = max(1, int(settings.SOURCE_RATE_LIMIT_MAX_RETRIES) + 1)
        for attempt in range(attempts):
            if self.request_allowance is not None and self.request_count - attempts_started_at >= self.request_allowance:
                raise MCPBudgetExhausted("No MCP calls remain in the reserved fair-share allowance.")
            self.request_count += 1
            try:
                async with asyncio.timeout(settings.SOURCE_TIMEOUT_SECONDS):
                    response = await self._call_with_source_limit(tool_name, arguments)
                data = decode_result(response)
                return MCPCallResult(data, round((loop.time() - started) * 1000))
            except MCPSourceError as exc:
                exc.duration_ms = round((loop.time() - started) * 1000)
                exc.retry_count = attempt
                inline_wait = exc.retry_after_seconds or 0
                can_retry_rate_limit = exc.rate_limited and 0 < inline_wait <= settings.SOURCE_RATE_LIMIT_MAX_INLINE_WAIT_SECONDS
                if not (exc.retryable or can_retry_rate_limit) or attempt + 1 == attempts:
                    raise
                logger.warning("Retrying transient MCP error for %s.%s", self.source_name, tool_name)
                if can_retry_rate_limit:
                    await asyncio.sleep(inline_wait + random.uniform(0, settings.SOURCE_RATE_LIMIT_JITTER))
            except TimeoutError as exc:
                if attempt + 1 == attempts:
                    duration = round((loop.time() - started) * 1000)
                    raise MCPSourceError(f"{tool_name} timed out after {attempts} attempts", duration) from exc
                logger.warning("Retrying timed out MCP call for %s.%s", self.source_name, tool_name)
            except Exception as exc:
                logger.warning("MCP call %s.%s failed on attempt %s: %s", self.source_name, tool_name, attempt + 1, type(exc).__name__)
                if attempt + 1 == attempts:
                    duration = round((loop.time() - started) * 1000)
                    retryable = isinstance(exc, (ConnectionError, OSError))
                    raise MCPSourceError(f"{tool_name} failed: {type(exc).__name__}", duration, retryable=retryable) from exc
            await asyncio.sleep(min(5.0, (0.5 * (2 ** attempt)) + random.uniform(0.05, 0.35)))
        raise MCPSourceError(f"{tool_name} failed after {attempts} attempts")


def run_source(source_name, coroutine_factory):
    """Run a source job with a fresh event loop and deterministically close MCP stdio."""
    return asyncio.run(coroutine_factory())
