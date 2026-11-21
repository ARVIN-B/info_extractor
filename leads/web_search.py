from __future__ import annotations

import ipaddress
import logging
import re
import ssl
import time
from datetime import datetime, timedelta, timezone as datetime_timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import JobContact, SearchJob, SourceExecution, SourceRateLimit
from .normalization import extract_iranian_mobiles, normalize_text, short_business_description

logger = logging.getLogger(__name__)
_CONTACT_PATHS = ["^/$", "^/.*/?contact.*$", "^/.*/?about.*$", "^/.*/?branches?.*$", "^/.*/?stores?.*$", "^/.*/?locations?.*$"]


class WebServiceError(RuntimeError):
    """A sanitized failure that names the web service and stage."""

    def __init__(self, message, *, status_code=None, rate_limited=False, retry_after_seconds=None, partial_results=None):
        super().__init__(message)
        self.status_code = status_code
        self.rate_limited = rate_limited
        self.retry_after_seconds = retry_after_seconds
        self.partial_results = partial_results or []


def _endpoint_label(value: str) -> str:
    parsed = urlparse(str(value or ""))
    if not parsed.scheme or not parsed.hostname:
        return "آدرس تنظیم نشده"
    try:
        port = f":{parsed.port}" if parsed.port else ""
    except ValueError:
        port = ""
    return f"{parsed.scheme}://{parsed.hostname}{port}"


def _public_http_url(value: str) -> str:
    parsed = urlparse(str(value or ""))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return ""
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith((".localhost", ".local", ".internal", ".test")):
        return ""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address and (address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_unspecified):
        return ""
    return parsed.geturl()


def _domain_key(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def _root_website(url: str) -> str:
    parsed = urlparse(_public_http_url(url))
    return f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""


def _normalized_search_url(value: str) -> str:
    safe_url = _public_http_url(value)
    if not safe_url:
        return ""
    parsed = urlparse(safe_url)
    host = (parsed.hostname or "").rstrip(".").lower()
    port = parsed.port
    netloc = host if not port or (parsed.scheme == "https" and port == 443) or (parsed.scheme == "http" and port == 80) else f"{host}:{port}"
    ignored = {"fbclid", "gclid", "ref", "source"}
    query = [(key, val) for key, val in parse_qsl(parsed.query, keep_blank_values=True) if key.lower() not in ignored and not key.lower().startswith("utm_")]
    return urlunparse((parsed.scheme.lower(), netloc, parsed.path.rstrip("/") or "/", "", urlencode(sorted(query)), ""))


def _searxng_queries(job):
    scope = job.geographic_scope_name if job.geographic_scope_type != SearchJob.ScopeType.IRAN else "ایران"
    expansion = job.query_expansion if isinstance(job.query_expansion, dict) else {}
    category = expansion.get("category") if isinstance(expansion.get("category"), dict) else {}
    aliases = category.get("aliases", []) if isinstance(category.get("aliases"), list) else []
    variants = expansion.get("variants", []) if isinstance(expansion.get("variants"), list) else []
    alternative = next((item.get("query") for item in variants if isinstance(item, dict) and isinstance(item.get("query"), str)), "")
    candidates = [
        f"{job.trade_name} {scope} شماره موبایل تماس",
        f"{(aliases[0] if aliases else alternative or job.trade_name)} {scope} شماره تماس وب‌سایت",
        f"{job.trade_name} {scope} business mobile phone website contact",
    ]
    output, seen = [], set()
    for query in candidates:
        query = " ".join(query.split())
        normalized = normalize_text(query)
        if normalized and normalized not in seen:
            output.append(query)
            seen.add(normalized)
        if len(output) >= settings.SEARXNG_MAX_QUERIES:
            break
    return output


def _searxng_http_client():
    verify = ssl.create_default_context(cafile=settings.SEARXNG_CA_BUNDLE) if settings.SEARXNG_CA_BUNDLE else settings.SEARXNG_VERIFY_TLS
    return httpx.Client(timeout=settings.SEARXNG_TIMEOUT, follow_redirects=True, verify=verify)


def _retry_after_seconds(value):
    if not value:
        return None
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        try:
            when = parsedate_to_datetime(str(value))
            if when.tzinfo is None:
                when = when.replace(tzinfo=datetime_timezone.utc)
            return max(1, int((when - datetime.now(datetime_timezone.utc)).total_seconds()))
        except (TypeError, ValueError, OverflowError):
            return None


def _result_record(item):
    url = _normalized_search_url(item.get("url", ""))
    if not url:
        return None
    metadata = {}
    for key in ("engines", "engine", "publishedDate", "category", "score", "positions", "template"):
        value = item.get(key)
        if isinstance(value, (str, int, float, bool, list, dict)) and value not in (None, "", [], {}):
            metadata[key] = value
    return {
        "url": url,
        "normalized_url": url,
        "title": short_business_description(item.get("title"), 255),
        "content": str(item.get("content") or "")[:3000],
        "engines": item.get("engines", []) if isinstance(item.get("engines", []), list) else [],
        "published_date": str(item.get("publishedDate") or "")[:80],
        "score": item.get("score") if isinstance(item.get("score"), (int, float)) else None,
        "metadata": metadata,
    }


def fetch_searxng_page(query, page=1, *, client=None, request_counter=None):
    """Fetch and normalize one authenticated SearXNG page; safe for manual smoke tests."""
    base = settings.SEARXNG_BASE_URL.rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise WebServiceError("SEARXNG_BASE_URL must be an HTTPS URL without embedded credentials.")
    if not settings.SEARXNG_API_KEY:
        raise WebServiceError("SEARXNG_API_KEY is not configured.")
    if not isinstance(query, str) or not query.strip():
        raise WebServiceError("SearXNG query must not be empty.")
    own_client = client is None
    if own_client:
        try:
            client = _searxng_http_client()
        except (OSError, ValueError):
            raise WebServiceError("SearXNG TLS configuration is invalid; check SEARXNG_CA_BUNDLE and SEARXNG_VERIFY_TLS.") from None
    params = {"q": query.strip(), "format": "json", "language": settings.SEARXNG_LANGUAGE, "pageno": max(1, int(page))}
    headers = {"X-API-Key": settings.SEARXNG_API_KEY}
    try:
        for attempt in range(settings.SEARXNG_RETRIES + 1):
            if request_counter is not None:
                request_counter[0] += 1
            try:
                response = client.get(f"{base}/search", headers=headers, params=params)
            except httpx.TransportError as exc:
                if attempt < settings.SEARXNG_RETRIES:
                    time.sleep(min(0.5 * (attempt + 1), 1.0))
                    continue
                detail = str(exc).lower()
                error_name = "TLS certificate verification failed" if "certificate" in detail or "ssl" in detail else type(exc).__name__
                raise WebServiceError(f"SearXNG connection failed at {_endpoint_label(base)} ({error_name}). Check service reachability and TLS configuration.") from None
            status = response.status_code
            if status == 429:
                raise WebServiceError(
                    f"SearXNG rate limited the request at {_endpoint_label(base)} (HTTP 429).",
                    status_code=status, rate_limited=True,
                    retry_after_seconds=_retry_after_seconds(response.headers.get("Retry-After")),
                )
            if status in {401, 403}:
                raise WebServiceError(f"SearXNG authentication or JSON access was rejected at {_endpoint_label(base)} (HTTP {status}). Check the API key and JSON format setting.", status_code=status)
            if status == 400:
                raise WebServiceError(f"SearXNG rejected the query (HTTP 400); check query parameters and language configuration.", status_code=status)
            if status >= 500 and attempt < settings.SEARXNG_RETRIES:
                time.sleep(min(0.5 * (attempt + 1), 1.0))
                continue
            if status >= 400:
                raise WebServiceError(f"SearXNG returned HTTP {status} at {_endpoint_label(base)}.", status_code=status)
            try:
                payload = response.json()
            except ValueError:
                raise WebServiceError("SearXNG returned malformed JSON.") from None
            if not isinstance(payload, dict) or not isinstance(payload.get("results", []), list):
                raise WebServiceError("SearXNG returned an unexpected JSON structure.")
            normalized = [_result_record(item) for item in payload.get("results", []) if isinstance(item, dict)]
            return [item for item in normalized if item]
        raise WebServiceError(f"SearXNG returned a transient server error at {_endpoint_label(base)}.")
    finally:
        if own_client:
            client.close()


def _search_queries(job):
    return _searxng_queries(job)


def search_domains(job, client: httpx.Client | None = None, request_counter=None) -> list[dict]:
    if not settings.SEARXNG_ENABLED or not settings.WEB_SEARCH_ENABLED:
        return []
    if not settings.SEARXNG_BASE_URL:
        raise WebServiceError("SEARXNG_BASE_URL is not configured.")
    own_client = client is None
    if own_client:
        try:
            client = _searxng_http_client()
        except (OSError, ValueError):
            raise WebServiceError("SearXNG TLS configuration is invalid; check SEARXNG_CA_BUNDLE and SEARXNG_VERIFY_TLS.") from None
    results, by_url = [], {}
    try:
        for query in _search_queries(job):
            seen_pages = set()
            for page_number in range(1, settings.SEARXNG_MAX_PAGES + 1):
                try:
                    page_results = fetch_searxng_page(query, page_number, client=client, request_counter=request_counter)
                except WebServiceError as exc:
                    exc.partial_results = results
                    raise
                if not page_results:
                    break
                fingerprint = tuple(item["normalized_url"] for item in page_results)
                if fingerprint in seen_pages:
                    break
                seen_pages.add(fingerprint)
                new_urls = 0
                for item in page_results:
                    url_key = item["normalized_url"]
                    existing = by_url.get(url_key)
                    if existing:
                        existing["engines"] = list(dict.fromkeys([*existing["engines"], *item["engines"]]))
                        existing["metadata"].update({key: value for key, value in item["metadata"].items() if key not in existing["metadata"]})
                        if not existing["content"] and item["content"]:
                            existing["content"] = item["content"]
                        continue
                    by_url[url_key] = item
                    results.append(item)
                    new_urls += 1
                    if len(results) >= settings.WEB_SEARCH_MAX_RESULTS:
                        break
                if len(results) >= settings.WEB_SEARCH_MAX_RESULTS:
                    break
                if new_urls == 0 and page_number > 1:
                    break
            if len(results) >= settings.WEB_SEARCH_MAX_RESULTS:
                break
        return results
    finally:
        if own_client:
            client.close()


def _api_base():
    base = settings.FIRECRAWL_BASE_URL.rstrip("/")
    if base.endswith(("/v1", "/v2")):
        return base
    return f"{base}/v2"


def crawl_domain(url: str, client: httpx.Client | None = None, request_counter: list | None = None) -> list[dict]:
    safe_url = _public_http_url(url)
    if not safe_url:
        return []
    crawl_start_url = safe_url
    if not settings.FIRECRAWL_BASE_URL:
        raise WebServiceError("Firecrawl: آدرس سرویس تنظیم نشده است.")
    own_client = client is None
    client = client or httpx.Client(timeout=min(settings.WEB_CRAWL_TIMEOUT, 60), follow_redirects=True)
    api = _api_base()
    headers = {"Authorization": f"Bearer {settings.FIRECRAWL_API_KEY}"} if settings.FIRECRAWL_API_KEY else {}

    def counted_request(method, *args, **kwargs):
        if request_counter is not None:
            request_counter[0] += 1
        try:
            response = getattr(client, method)(*args, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            raise WebServiceError(f"Firecrawl در {_endpoint_label(settings.FIRECRAWL_BASE_URL)} پاسخ HTTP {exc.response.status_code} داد.") from None
        except httpx.TransportError as exc:
            raise WebServiceError(f"اتصال به Firecrawl در {_endpoint_label(settings.FIRECRAWL_BASE_URL)} برقرار نشد ({type(exc).__name__}). سرویس و دسترسی شبکهٔ worker را بررسی کنید.") from None

    try:
        response = counted_request(
            "post", f"{api}/crawl", headers=headers,
            json={
                "url": crawl_start_url,
                "limit": settings.WEB_CRAWL_MAX_PAGES_PER_DOMAIN,
                "maxDiscoveryDepth": settings.WEB_CRAWL_MAX_DEPTH,
                "includePaths": _CONTACT_PATHS,
                "allowExternalLinks": False,
                "allowSubdomains": False,
                "crawlEntireDomain": False,
                "scrapeOptions": {"formats": ["markdown", "html"]},
            },
        )
        try:
            crawl_id = response.json().get("id")
        except ValueError:
            crawl_id = None
        if not crawl_id:
            raise WebServiceError("Firecrawl درخواست crawl را پذیرفت اما شناسهٔ crawl برنگرداند.")
        deadline = time.monotonic() + settings.WEB_CRAWL_TIMEOUT
        while time.monotonic() < deadline:
            result = counted_request("get", f"{api}/crawl/{crawl_id}", params={"limit": settings.WEB_CRAWL_MAX_PAGES_PER_DOMAIN}, headers=headers)
            try:
                payload = result.json()
            except ValueError:
                raise WebServiceError("Firecrawl پاسخ وضعیت JSON معتبر برنگرداند.") from None
            if payload.get("status") in {"completed", "failed", "cancelled"}:
                if payload.get("status") != "completed":
                    raise WebServiceError(f"Firecrawl وضعیت crawl را {payload.get('status')} اعلام کرد.")
                return payload.get("data") or []
            time.sleep(min(4, max(0.1, deadline - time.monotonic())))
        raise WebServiceError("Firecrawl از مهلت تعیین‌شده عبور کرد؛ تنظیم WEB_CRAWL_TIMEOUT را بررسی کنید.")
    finally:
        if own_client:
            client.close()


def _page_info(page):
    data = page.get("data", page) if isinstance(page, dict) else {}
    metadata = data.get("metadata") or {}
    html = str(data.get("html") or "")
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
    title = metadata.get("title") or metadata.get("ogTitle") or (re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else "")
    description = metadata.get("description") or metadata.get("ogDescription") or _meta_description(html)
    address = metadata.get("address") or metadata.get("businessAddress") or ""
    content = "\n".join(str(data.get(key) or "") for key in ("markdown", "content", "html"))
    page_url = str(metadata.get("sourceURL") or metadata.get("url") or "")
    website = _root_website(page_url)
    return content, page_url, str(address), short_business_description(title, 255), short_business_description(description, 1000), website


def _meta_description(html):
    for tag in re.findall(r"<meta\b[^>]*>", str(html or ""), flags=re.I):
        attrs = {key.lower(): value for key, _, value in re.findall(r"([\w:-]+)\s*=\s*(['\"])(.*?)\2", tag, flags=re.I)}
        name = (attrs.get("name") or attrs.get("property") or "").lower()
        if name in {"description", "og:description", "twitter:description"}:
            return attrs.get("content", "")
    return ""


def _active_searxng_cooldown():
    state = SourceRateLimit.objects.filter(source_name="searxng").first()
    return state if state and state.cooldown_until > timezone.now() else None


def _remember_searxng_rate_limit(error):
    seconds = error.retry_after_seconds or settings.SOURCE_RATE_LIMIT_DEFAULT_COOLDOWN_SECONDS
    cooldown_until = timezone.now() + timedelta(seconds=max(1, seconds))
    state, _ = SourceRateLimit.objects.get_or_create(
        source_name="searxng",
        defaults={"cooldown_until": cooldown_until, "reason": "HTTP 429 rate limit"},
    )
    if state.cooldown_until < cooldown_until:
        state.cooldown_until = cooldown_until
    state.reason = "HTTP 429 rate limit"
    state.updated_at = timezone.now()
    state.save(update_fields=["cooldown_until", "reason", "updated_at"])
    return state.cooldown_until


def run_web_lane(job: SearchJob, execution: SourceExecution) -> int:
    execution.status = SourceExecution.Status.RUNNING
    execution.started_at = execution.last_attempt_at = timezone.now()
    execution.save(update_fields=["status", "started_at", "last_attempt_at"])
    try:
        if job.contacts.count() >= job.requested_phone_count:
            execution.status = SourceExecution.Status.SKIPPED
            execution.error_details = "Requested unique phone target is already reached."
            execution.completed_at = timezone.now()
            execution.save(update_fields=["status", "error_details", "completed_at"])
            return job.contacts.count()
        if not settings.WEB_SEARCH_ENABLED:
            execution.status = SourceExecution.Status.SKIPPED
            execution.error_details = "Web search lane is disabled."
            execution.completed_at = timezone.now()
            execution.save(update_fields=["status", "error_details", "completed_at"])
            return 0
        cooldown = _active_searxng_cooldown()
        if cooldown:
            execution.status = SourceExecution.Status.RATE_LIMITED
            execution.error_type = "rate_limit"
            execution.cooldown_until = cooldown.cooldown_until
            execution.error_details = f"SearXNG is cooling down until {timezone.localtime(cooldown.cooldown_until).strftime('%H:%M:%S')} after HTTP 429."
            execution.completed_at = timezone.now()
            execution.save(update_fields=["status", "error_type", "cooldown_until", "error_details", "completed_at"])
            return job.contacts.count()
        execution.query_variants = _search_queries(job)
        execution.save(update_fields=["query_variants"])
        search_counter = [0]
        search_error = None
        try:
            search_results = search_domains(job, request_counter=search_counter)[:settings.WEB_SEARCH_MAX_DOMAINS]
        except WebServiceError as exc:
            search_error = exc
            search_results = exc.partial_results[:settings.WEB_SEARCH_MAX_DOMAINS]
            if not search_results:
                raise
        finally:
            execution.request_count += search_counter[0]
            execution.save(update_fields=["request_count"])
        execution.result_count = len(search_results)
        diagnostics = dict(execution.diagnostics or {})
        diagnostics["searxng"] = {
            "pages_requested": search_counter[0],
            "results": [{"url": row.get("url", ""), "title": row.get("title", ""), "engines": row.get("engines", []), "published_date": row.get("published_date", ""), "score": row.get("score"), "metadata": row.get("metadata", {})} for row in search_results],
        }
        execution.diagnostics = diagnostics
        execution.save(update_fields=["result_count", "diagnostics"])
        errors = [str(search_error)] if search_error else []
        for item in search_results:
            title, snippet = item.get("title", ""), item.get("content", "")
            for candidate in extract_iranian_mobiles(f"{title}\n{snippet}", path="searx_result"):
                number = "0" + candidate.normalized_number[3:]
                with transaction.atomic():
                    locked = SearchJob.objects.select_for_update().get(pk=job.pk)
                    if locked.contacts.count() >= locked.requested_phone_count:
                        break
                    contact, _ = JobContact.objects.get_or_create(
                        search_job=locked, normalized_number=number,
                        defaults={"source_name": "web", "business_name": title[:255], "website": _root_website(item["url"]), "description": short_business_description(snippet), "evidence_url": item["url"][:1000]},
                    )
            if job.contacts.count() >= job.requested_phone_count:
                break

        domains_by_site = {}
        for item in search_results:
            domains_by_site.setdefault(_domain_key(item["url"]), (item["url"], _domain_key(item["url"])))
        pending = iter(domains_by_site.values())
        active = {}
        with ThreadPoolExecutor(max_workers=settings.WEB_CRAWL_CONCURRENCY, thread_name_prefix=f"web-{job.pk}") as pool:
            def submit_next():
                if job.contacts.count() >= job.requested_phone_count:
                    return False
                try:
                    url, domain = next(pending)
                except StopIteration:
                    return False
                counter = [0]
                active[pool.submit(crawl_domain, url, request_counter=counter)] = (url, domain, counter)
                return True

            for _ in range(settings.WEB_CRAWL_CONCURRENCY):
                if not submit_next():
                    break
            while active:
                completed = next(as_completed(active))
                url, domain, counter = active.pop(completed)
                try:
                    pages = completed.result()
                    for page in pages[:settings.WEB_CRAWL_MAX_PAGES_PER_DOMAIN]:
                        if job.contacts.count() >= job.requested_phone_count:
                            break
                        content, page_url, address, title, description, website = _page_info(page)
                        name = title or next((item["title"] for item in search_results if _domain_key(item["url"]) == domain), "")
                        for candidate in extract_iranian_mobiles(content, path="public_business_website"):
                            national = "0" + candidate.normalized_number[3:]
                            with transaction.atomic():
                                locked_job = SearchJob.objects.select_for_update().get(pk=job.pk)
                                if locked_job.contacts.count() >= locked_job.requested_phone_count:
                                    break
                                JobContact.objects.get_or_create(
                                    search_job=locked_job,
                                    normalized_number=national,
                                defaults={"source_name": "web", "business_name": name[:255], "website": website[:500], "address": address, "description": short_business_description(description or content), "evidence_url": (page_url or url)[:1000]},
                                )
                except Exception as exc:
                    errors.append(f"{domain}: {exc if isinstance(exc, WebServiceError) else type(exc).__name__}")
                    logger.warning("Web crawl failed for domain %s in job %s (%s)", domain, job.pk, type(exc).__name__)
                execution.request_count += counter[0]
                execution.save(update_fields=["request_count"])
                if job.contacts.count() < job.requested_phone_count:
                    submit_next()
        execution.error_count = len(errors)
        execution.error_details = "\n".join(errors)[:2000]
        if search_error and search_error.rate_limited:
            execution.status = SourceExecution.Status.RATE_LIMITED
            execution.error_type = "rate_limit"
            execution.cooldown_until = _remember_searxng_rate_limit(search_error)
        else:
            execution.status = SourceExecution.Status.PARTIAL if errors else SourceExecution.Status.COMPLETED
            execution.error_type = "searxng_partial" if search_error else "firecrawl_partial" if errors else ""
        execution.completed_at = timezone.now()
        execution.save(update_fields=["status", "error_type", "cooldown_until", "error_count", "error_details", "completed_at"])
        return job.contacts.count()
    except Exception as exc:
        logger.error("Web discovery failed for job %s (%s)", job.pk, type(exc).__name__)
        if isinstance(exc, WebServiceError) and exc.rate_limited:
            execution.status = SourceExecution.Status.RATE_LIMITED
            execution.error_type = "rate_limit"
            execution.cooldown_until = _remember_searxng_rate_limit(exc)
        else:
            execution.status = SourceExecution.Status.PARTIAL if execution.result_count else SourceExecution.Status.FAILED
            execution.error_type = "web_search_error"
        execution.error_count = max(1, execution.error_count)
        execution.error_details = str(exc)[:2000] if isinstance(exc, WebServiceError) else f"{type(exc).__name__}: web service request failed"
        execution.completed_at = timezone.now()
        execution.save(update_fields=["status", "error_type", "cooldown_until", "error_count", "error_details", "completed_at"])
        return job.contacts.count()
