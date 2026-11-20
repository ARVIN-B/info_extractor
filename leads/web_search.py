from __future__ import annotations

import ipaddress
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import httpx
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import JobContact, SearchJob, SourceExecution
from .normalization import extract_iranian_mobiles

logger = logging.getLogger(__name__)
_CONTACT_PATHS = ["^/$", "^/.*/?contact.*$", "^/.*/?about.*$", "^/.*/?branches?.*$", "^/.*/?stores?.*$", "^/.*/?locations?.*$"]


class WebServiceError(RuntimeError):
    """A sanitized failure that names the web service and stage."""


def _endpoint_label(value: str) -> str:
    parsed = urlparse(str(value or ""))
    if not parsed.scheme or not parsed.hostname:
        return "آدرس تنظیم نشده"
    port = f":{parsed.port}" if parsed.port else ""
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


def _search_queries(job):
    scope = job.geographic_scope_name if job.geographic_scope_type != SearchJob.ScopeType.IRAN else "ایران"
    base = " ".join(part for part in (job.trade_name, scope) if part)
    # One broad query returns URLs, titles, and snippets in a single SearXNG request.
    return [f"{base} کسب و کار شماره تماس وب سایت آدرس"]


def search_domains(job, client: httpx.Client | None = None) -> list[dict]:
    if not settings.WEB_SEARCH_ENABLED:
        return []
    if not settings.SEARXNG_BASE_URL:
        raise WebServiceError("SearXNG: آدرس سرویس تنظیم نشده است.")
    own_client = client is None
    client = client or httpx.Client(timeout=settings.WEB_SEARCH_TIMEOUT, follow_redirects=True)
    results, seen_domains = [], set()
    try:
        query = _search_queries(job)[0]
        try:
            response = client.get(
                f"{settings.SEARXNG_BASE_URL.rstrip('/')}/search",
                params={"q": query, "format": "json", "language": "fa-IR", "safesearch": 1},
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise WebServiceError(f"SearXNG در {_endpoint_label(settings.SEARXNG_BASE_URL)} پاسخ HTTP {exc.response.status_code} داد.") from None
        except httpx.TransportError as exc:
            raise WebServiceError(f"اتصال به SearXNG در {_endpoint_label(settings.SEARXNG_BASE_URL)} برقرار نشد ({type(exc).__name__}). سرویس و دسترسی شبکهٔ worker را بررسی کنید.") from None
        except ValueError:
            raise WebServiceError("SearXNG پاسخ JSON معتبر برنگرداند؛ فعال‌بودن فرمت JSON را بررسی کنید.") from None
        for item in payload.get("results", []):
            if not isinstance(item, dict):
                continue
            url = _public_http_url(item.get("url", ""))
            domain = _domain_key(url) if url else ""
            if url and domain and domain not in seen_domains:
                seen_domains.add(domain)
                results.append({"url": url, "title": str(item.get("title") or "")[:255], "content": str(item.get("content") or "")[:3000]})
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
    parsed_url = urlparse(safe_url)
    crawl_start_url = f"{parsed_url.scheme}://{parsed_url.netloc}/"
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
    description = metadata.get("description") or metadata.get("ogDescription") or ""
    address = metadata.get("address") or metadata.get("businessAddress") or ""
    content = "\n".join(str(data.get(key) or "") for key in ("markdown", "content", "html"))
    page_url = str(metadata.get("sourceURL") or metadata.get("url") or "")
    website = _root_website(page_url)
    return content, page_url, str(address), str(title)[:255], str(description)[:5000], website


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
        execution.query_variants = _search_queries(job)
        execution.request_count += 1  # The single SearXNG request, including failed attempts.
        execution.save(update_fields=["query_variants", "request_count"])
        search_results = search_domains(job)[:settings.WEB_SEARCH_MAX_DOMAINS]
        execution.result_count = len(search_results)
        execution.save(update_fields=["result_count"])
        errors = []
        seen_initial_numbers = set()
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
                        defaults={"source_name": "web", "business_name": title[:255], "website": _root_website(item["url"]), "description": snippet[:5000], "evidence_url": item["url"][:1000]},
                    )
                seen_initial_numbers.add(contact.normalized_number)
            if job.contacts.count() >= job.requested_phone_count:
                break

        domains = list(dict.fromkeys((item["url"], _domain_key(item["url"])) for item in search_results))
        pending = iter(domains)
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
                                    defaults={"source_name": "web", "business_name": name[:255], "website": website[:500], "address": address, "description": description[:5000], "evidence_url": (page_url or url)[:1000]},
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
        execution.status = SourceExecution.Status.PARTIAL if errors else SourceExecution.Status.COMPLETED
        execution.error_type = "firecrawl_partial" if errors else ""
        execution.completed_at = timezone.now()
        execution.save(update_fields=["status", "error_type", "error_count", "error_details", "completed_at"])
        return job.contacts.count()
    except Exception as exc:
        logger.error("Web discovery failed for job %s (%s)", job.pk, type(exc).__name__)
        execution.status = SourceExecution.Status.PARTIAL if execution.result_count else SourceExecution.Status.FAILED
        execution.error_type = "web_search_error"
        execution.error_count = max(1, execution.error_count)
        execution.error_details = str(exc)[:2000] if isinstance(exc, WebServiceError) else f"{type(exc).__name__}: web service request failed"
        execution.completed_at = timezone.now()
        execution.save(update_fields=["status", "error_type", "error_count", "error_details", "completed_at"])
        return job.contacts.count()
