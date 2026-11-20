from __future__ import annotations

import ipaddress
import logging
import time
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import JobContact, SearchJob, SourceExecution
from .normalization import extract_iranian_mobiles

logger = logging.getLogger(__name__)
_CONTACT_PATHS = ["^/$", "^/.*/?contact.*$", "^/.*/?about.*$", "^/.*/?branches?.*$", "^/.*/?stores?.*$", "^/.*/?locations?.*$"]


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


def _search_queries(job):
    scope = job.geographic_scope_name if job.geographic_scope_type != SearchJob.ScopeType.IRAN else "ایران"
    base = " ".join(part for part in (job.trade_name, scope) if part)
    return list(dict.fromkeys((base, f'{base} تماس تلفن', f'{base} شماره موبایل', f'{base} آدرس تلفن تماس')))


def search_domains(job, client: httpx.Client | None = None) -> list[str]:
    if not settings.WEB_SEARCH_ENABLED:
        return []
    if not settings.SEARXNG_BASE_URL:
        raise RuntimeError("SEARXNG_BASE_URL is not configured")
    own_client = client is None
    client = client or httpx.Client(timeout=settings.WEB_SEARCH_TIMEOUT, follow_redirects=True)
    urls, seen_domains = [], set()
    try:
        for query in _search_queries(job):
            response = client.get(
                f"{settings.SEARXNG_BASE_URL}/search",
                params={"q": query, "format": "json", "language": "fa-IR", "safesearch": 1},
            )
            response.raise_for_status()
            payload = response.json()
            for result in payload.get("results", []):
                url = _public_http_url(result.get("url", "")) if isinstance(result, dict) else ""
                domain = _domain_key(url) if url else ""
                if url and domain and domain not in seen_domains:
                    seen_domains.add(domain)
                    urls.append(url)
                    if len(urls) >= settings.WEB_SEARCH_MAX_RESULTS:
                        return urls
        return urls
    finally:
        if own_client:
            client.close()


def _api_base():
    base = settings.FIRECRAWL_BASE_URL.rstrip("/")
    if base.endswith(("/v1", "/v2")):
        return base
    return f"{base}/v2"


def crawl_domain(url: str, client: httpx.Client | None = None) -> list[dict]:
    safe_url = _public_http_url(url)
    if not safe_url:
        return []
    parsed_url = urlparse(safe_url)
    crawl_start_url = f"{parsed_url.scheme}://{parsed_url.netloc}/"
    if not settings.FIRECRAWL_BASE_URL:
        raise RuntimeError("FIRECRAWL_BASE_URL is not configured")
    own_client = client is None
    client = client or httpx.Client(timeout=min(settings.WEB_CRAWL_TIMEOUT, 60), follow_redirects=True)
    api = _api_base()
    headers = {"Authorization": f"Bearer {settings.FIRECRAWL_API_KEY}"} if settings.FIRECRAWL_API_KEY else {}
    try:
        response = client.post(
            f"{api}/crawl",
            headers=headers,
            json={
                "url": crawl_start_url,
                "limit": settings.WEB_CRAWL_MAX_PAGES_PER_DOMAIN,
                "maxDiscoveryDepth": settings.WEB_CRAWL_MAX_DEPTH,
                "includePaths": _CONTACT_PATHS,
                "allowExternalLinks": False,
                "allowSubdomains": False,
                "crawlEntireDomain": False,
                "scrapeOptions": {"formats": ["markdown"]},
            },
        )
        response.raise_for_status()
        crawl_id = response.json().get("id")
        if not crawl_id:
            raise RuntimeError("Firecrawl did not return a crawl id")
        deadline = time.monotonic() + settings.WEB_CRAWL_TIMEOUT
        while time.monotonic() < deadline:
            result = client.get(f"{api}/crawl/{crawl_id}", params={"limit": settings.WEB_CRAWL_MAX_PAGES_PER_DOMAIN}, headers=headers)
            result.raise_for_status()
            payload = result.json()
            if payload.get("status") in {"completed", "failed", "cancelled"}:
                if payload.get("status") != "completed":
                    raise RuntimeError(f"Firecrawl crawl {payload.get('status')}")
                return payload.get("data") or []
            time.sleep(min(2, max(0.1, deadline - time.monotonic())))
        raise TimeoutError("Firecrawl crawl exceeded WEB_CRAWL_TIMEOUT")
    finally:
        if own_client:
            client.close()


def _page_text(page):
    data = page.get("data", page) if isinstance(page, dict) else {}
    metadata = data.get("metadata") or {}
    address = metadata.get("address") or metadata.get("businessAddress") or ""
    return str(data.get("markdown") or data.get("content") or ""), str(metadata.get("sourceURL") or metadata.get("url") or ""), str(address)


def run_web_lane(job: SearchJob, execution: SourceExecution) -> int:
    execution.status = SourceExecution.Status.RUNNING
    execution.started_at = execution.last_attempt_at = timezone.now()
    execution.save(update_fields=["status", "started_at", "last_attempt_at"])
    try:
        if not settings.WEB_SEARCH_ENABLED:
            execution.status = SourceExecution.Status.SKIPPED
            execution.error_details = "Web search lane is disabled."
            execution.completed_at = timezone.now()
            execution.save(update_fields=["status", "error_details", "completed_at"])
            return 0
        domains = search_domains(job)[:settings.WEB_SEARCH_MAX_DOMAINS]
        execution.query_variants = _search_queries(job)
        execution.result_count = len(domains)
        execution.save(update_fields=["query_variants", "result_count"])
        errors = []
        pending = iter(dict.fromkeys((url, _domain_key(url)) for url in domains))
        active = {}
        with ThreadPoolExecutor(max_workers=settings.WEB_CRAWL_CONCURRENCY, thread_name_prefix=f"web-{job.pk}") as pool:
            def submit_next():
                if job.contacts.count() >= job.requested_phone_count:
                    return False
                try:
                    url, domain = next(pending)
                except StopIteration:
                    return False
                active[pool.submit(crawl_domain, url)] = (url, domain)
                return True

            for _ in range(settings.WEB_CRAWL_CONCURRENCY):
                if not submit_next():
                    break
            while active:
                completed = next(as_completed(active))
                url, domain = active.pop(completed)
                try:
                    pages = completed.result()
                    for page in pages[:settings.WEB_CRAWL_MAX_PAGES_PER_DOMAIN]:
                        if job.contacts.count() >= job.requested_phone_count:
                            break
                        content, page_url, address = _page_text(page)
                        for candidate in extract_iranian_mobiles(content, path="public_business_website"):
                            national = "0" + candidate.normalized_number[3:]
                            with transaction.atomic():
                                locked_job = SearchJob.objects.select_for_update().get(pk=job.pk)
                                if locked_job.contacts.count() >= locked_job.requested_phone_count:
                                    break
                                JobContact.objects.get_or_create(
                                    search_job=locked_job,
                                    normalized_number=national,
                                    defaults={"source_name": "web", "address": address, "evidence_url": (page_url or url)[:1000]},
                                )
                except Exception as exc:
                    errors.append(f"{domain}: {type(exc).__name__}; crawl failed")
                    logger.warning("Firecrawl failed for domain %s in job %s (%s)", domain, job.pk, type(exc).__name__)
                execution.request_count += 1
                execution.save(update_fields=["request_count"])
                if not errors or len(errors) < len(domains):
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
        execution.error_details = f"{type(exc).__name__}: web service request failed"
        execution.completed_at = timezone.now()
        execution.save(update_fields=["status", "error_type", "error_count", "error_details", "completed_at"])
        return job.contacts.count()
