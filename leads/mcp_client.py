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
}


class MCPSourceError(Exception):
    """Safe, source-specific MCP error suitable for the job log."""

    def __init__(self, message, duration_ms=0, retryable=False, rate_limited=False, retry_after_seconds=None):
        safe_message = re.sub(r"(https?://)[^/@\s]+:[^/@\s]+@", r"\1[redacted]@", str(message))
        safe_message = re.sub(r"(?i)(api[_-]?key|token|authorization)(\s*[:=]\s*)[^\s,;]+", r"\1\2[redacted]", safe_message)
        super().__init__(safe_message)
        self.duration_ms = duration_ms
        self.retryable = retryable
        detected, detected_after = _rate_limit_details(safe_message)
        self.rate_limited = rate_limited or detected
        self.retry_after_seconds = retry_after_seconds or detected_after


def _rate_limit_details(message):
    text = str(message)
    limited = bool(re.search(r"\b429\b|rate[ -]?limit|too many requests", text, re.IGNORECASE))
    if not limited:
        return False, None
    retry_after = re.search(r"retry[- ]after\s*[:=]?\s*([^\s,;]+)", text, re.IGNORECASE)
    if retry_after:
        raw = retry_after.group(1)
        if raw.isdigit():
            return True, max(1, min(3600, int(raw)))
        try:
            parsed = parsedate_to_datetime(raw)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=datetime_timezone.utc)
            seconds = int((parsed - datetime.now(datetime_timezone.utc)).total_seconds())
            return True, max(1, min(3600, seconds))
        except (TypeError, ValueError, OverflowError):
            pass
    wait = re.search(r"wait\s+(\d+)\s*(seconds?|minutes?|hours?)", text, re.IGNORECASE)
    if wait:
        amount = int(wait.group(1))
        unit = wait.group(2).lower()
        seconds = amount * (3600 if unit.startswith("hour") else 60 if unit.startswith("minute") else 1)
        return True, max(1, min(3600, seconds))
    if re.search(r"wait\s+a\s+minute", text, re.IGNORECASE):
        return True, 60
    return True, 60


@dataclass
class MCPCallResult:
    data: object
    duration_ms: int


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
        return structured
    values = []
    for item in getattr(result, "content", []):
        if getattr(item, "type", "") == "text":
            try:
                values.append(json.loads(item.text))
            except (TypeError, json.JSONDecodeError):
                values.append(item.text)
    return values[0] if len(values) == 1 else values


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
        attempts = 2
        for attempt in range(attempts):
            self.request_count += 1
            try:
                async with asyncio.timeout(settings.SOURCE_TIMEOUT_SECONDS):
                    response = await self._call_with_source_limit(tool_name, arguments)
                data = decode_result(response)
                return MCPCallResult(data, round((loop.time() - started) * 1000))
            except MCPSourceError as exc:
                exc.duration_ms = round((loop.time() - started) * 1000)
                if not exc.retryable or attempt + 1 == attempts:
                    raise
                logger.warning("Retrying transient MCP error for %s.%s", self.source_name, tool_name)
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
