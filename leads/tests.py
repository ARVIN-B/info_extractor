import json
import threading
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.db import transaction as db_transaction
from django.db.utils import OperationalError
from openpyxl import load_workbook
from asgiref.sync import async_to_sync

from .adapters import EmallsAdapter, _with_phone_filter
from .forms import SearchJobForm
from .mcp_client import MCPSourceError, SOURCE_REGISTRY
from .models import JobContact, SearchJob, SourceExecution, SourceRateLimit
from .normalization import extract_iranian_mobiles, normalize_iranian_mobile, normalize_phone
from .sources import _field_values, execute_source
from .tasks import run_search_job
from .web_search import WebServiceError, _normalized_search_url, _public_http_url, _search_queries, crawl_domain, fetch_searxng_page, run_web_lane, search_domains


def make_job(*, requested=3, status=SearchJob.Status.QUEUED):
    user = get_user_model().objects.create_user(username=f"test-{threading.get_ident()}-{SearchJob.objects.count()}")
    job = SearchJob.objects.create(
        owner=user, trade_name="شیشه‌فروشی", geographic_scope_type=SearchJob.ScopeType.CITY,
        geographic_scope_name="اصفهان", selected_sources=["neshan", "balad", "emalls", "web"],
        max_results=requested, requested_phone_count=requested, status=status,
    )
    return job


class PhoneOutputTests(TestCase):
    def test_mobile_regex_normalizes_supported_iranian_forms_and_rejects_landlines(self):
        self.assertEqual(normalize_phone("۰۹۱۲ ۳۴۵ ۶۷۸۹"), "09123456789")
        self.assertEqual(normalize_phone("+989123456789"), "09123456789")
        self.assertEqual(normalize_phone("0098 912 345 6789"), "09123456789")
        self.assertEqual(normalize_phone("989123456789"), "09123456789")
        self.assertEqual(normalize_iranian_mobile("9123456789"), "+989123456789")
        self.assertEqual(normalize_phone("02112345678"), "02112345678")
        self.assertEqual(normalize_iranian_mobile("02112345678"), "")
        self.assertEqual(extract_iranian_mobiles("تلفن ۰۲۱۱۲۳۴۵۶۷۸، همراه ۰۹۱۲۳۴۵۶۷۸۹")[0].normalized_number, "+989123456789")

    def test_job_contact_normalizes_and_database_constraint_deduplicates_by_job_and_phone(self):
        job = make_job()
        row, created = JobContact.objects.get_or_create(
            search_job=job, normalized_number="+989123456789",
            defaults={"source_name": "neshan", "address": "نشانی نمونه"},
        )
        duplicate, duplicate_created = JobContact.objects.get_or_create(
            search_job=job, normalized_number="۰۹۱۲۳۴۵۶۷۸۹",
            defaults={"source_name": "web"},
        )
        self.assertTrue(created)
        self.assertFalse(duplicate_created)
        self.assertEqual(row.pk, duplicate.pk)
        self.assertEqual(row.normalized_number, "09123456789")
        self.assertEqual(row.source_name, "neshan")
        JobContact.objects.get_or_create(
            search_job=job, normalized_number="09123456789",
            defaults={"source_name": "web", "business_name": "فروشگاه نمونه", "website": "https://shop.example", "description": "توضیح"},
        )
        row.refresh_from_db()
        self.assertEqual(row.business_name, "فروشگاه نمونه")
        self.assertEqual(row.website, "https://shop.example")
        self.assertEqual(row.description, "توضیح")

    def test_registry_and_form_only_offer_the_three_mcp_lanes_and_requested_count(self):
        self.assertEqual(set(SOURCE_REGISTRY), {"neshan", "balad", "emalls"})
        form = SearchJobForm(data={
            "trade_name": "کافه", "geographic_scope_type": "city", "geographic_scope_name": "اصفهان",
            "requested_phone_count": "17",
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["requested_phone_count"], 17)
        self.assertNotIn("sources", form.fields)
        invalid = SearchJobForm(data={
            "trade_name": "کافه", "geographic_scope_type": "city", "geographic_scope_name": "اصفهان",
            "requested_phone_count": "1001",
        })
        self.assertFalse(invalid.is_valid())

    def test_phone_search_filter_is_added_only_if_declared_as_boolean(self):
        tool = SimpleNamespace(input_schema={"type": "object", "properties": {"query": {"type": "string"}, "with_phone": {"type": "boolean"}}})
        client = SimpleNamespace(tools={"search": tool})
        self.assertEqual(_with_phone_filter(client, "search", {"query": "shop"}), {"query": "shop", "with_phone": True})
        tool.input_schema["properties"].pop("with_phone")
        self.assertEqual(_with_phone_filter(client, "search", {"query": "shop"}), {"query": "shop"})

    def test_source_field_extraction_includes_business_description_and_official_site(self):
        fields = _field_values({"name": "فروشگاه نمونه"}, {
            "website": "https://shop.example", "address": "اصفهان", "description": "فروش لوازم الکترونیکی",
        })
        self.assertEqual(fields["name"], "فروشگاه نمونه")
        self.assertEqual(fields["website"], "https://shop.example")
        self.assertEqual(fields["address"], "اصفهان")
        self.assertEqual(fields["description"], "فروش لوازم الکترونیکی")

    def test_emalls_uses_single_direct_shop_call_when_mobile_is_already_available(self):
        client = SimpleNamespace(tools={
            "em_shops": SimpleNamespace(input_schema={"type": "object", "properties": {"query": {"type": "string"}, "page": {"type": "integer", "minimum": 1, "maximum": 50}}, "required": ["query"]}),
            "em_shop": SimpleNamespace(input_schema={"type": "object", "properties": {"shop_id": {"type": "integer"}}, "required": ["shop_id"]}),
        })
        calls = []

        async def invoke(_client, name, arguments):
            calls.append((name, arguments))
            return SimpleNamespace(data={"shops": [{"id": 123, "name": "فروشگاه نمونه", "phone": "09123456789", "website": "https://shop.example"}]})

        result = async_to_sync(EmallsAdapter().discover)(client, invoke, "الکترونیکی", "اصفهان", "اصفهان", 1)
        self.assertEqual([call[0] for call in calls], ["em_shops"])
        self.assertEqual(result.records[0][0]["name"], "فروشگاه نمونه")
        self.assertEqual(result.records[0][0]["website"], "https://shop.example")

    @override_settings(SOURCE_RATE_LIMIT_DEFAULT_COOLDOWN_SECONDS=75, MCP_DISTRIBUTED_SOURCE_LIMITS=False)
    def test_mcp_429_sets_a_persistent_cooldown_for_later_jobs(self):
        job = make_job()
        execution = SourceExecution.objects.create(search_job=job, source_name="neshan")

        async def fail_with_429(*args, **kwargs):
            raise MCPSourceError("Neshan returned HTTP 429", rate_limited=True, retry_after_seconds=90)

        with patch("leads.sources._search_source", side_effect=fail_with_429):
            execute_source("neshan", job, execution)
        execution.refresh_from_db()
        cooldown = SourceRateLimit.objects.get(source_name="neshan")
        self.assertEqual(execution.status, SourceExecution.Status.RATE_LIMITED)
        self.assertEqual(execution.error_type, "rate_limit")
        self.assertGreaterEqual((cooldown.cooldown_until - timezone.now()).total_seconds(), 85)


class WebDiscoveryTests(TestCase):
    def test_query_strategy_includes_trade_area_phone_and_english_phrasing(self):
        queries = _search_queries(make_job())
        self.assertEqual(len(queries), 3)
        self.assertTrue(all("اصفهان" in query for query in queries))
        self.assertIn("شماره", queries[0])
        self.assertIn("business mobile phone website contact", queries[-1])
        self.assertEqual(len({query.casefold() for query in queries}), len(queries))

    @override_settings(SEARXNG_ENABLED=True, SEARXNG_MAX_PAGES=1, SEARXNG_MAX_QUERIES=1)
    def test_search_authenticates_configures_language_and_preserves_metadata(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={"results": [
                {"url": "https://www.example.ir/shops?utm_source=test", "title": "فروشگاه نمونه", "content": "09123456789", "engines": ["brave", "google"], "publishedDate": "2026-11-20", "score": 3.5},
                {"url": "https://example.ir/contact"},
                {"url": "https://shop.example.ir/contact"},
                {"url": "http://127.0.0.1/private"},
            ]})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        job = make_job()
        requests = [0]
        with override_settings(SEARXNG_BASE_URL="https://searx.test", SEARXNG_API_KEY="fixture-key", SEARXNG_LANGUAGE="fa", WEB_SEARCH_MAX_RESULTS=10):
            results = search_domains(job, client=client, request_counter=requests)
        client.close()
        self.assertEqual([item["url"] for item in results], ["https://www.example.ir/shops", "https://example.ir/contact", "https://shop.example.ir/contact"])
        self.assertEqual(results[0]["title"], "فروشگاه نمونه")
        self.assertEqual(results[0]["engines"], ["brave", "google"])
        self.assertEqual(results[0]["published_date"], "2026-11-20")
        self.assertTrue(all(request.headers.get("X-API-Key") == "fixture-key" for request in calls))
        self.assertTrue(all(request.url.params.get("format") == "json" for request in calls))
        self.assertTrue(all(request.url.params.get("language") == "fa" for request in calls))
        self.assertEqual(len(calls), 1)
        self.assertEqual(requests[0], 1)
        self.assertIn("اصفهان", calls[0].url.params["q"])

    def test_missing_key_is_rejected_without_sending_a_request(self):
        calls = []
        client = httpx.Client(transport=httpx.MockTransport(lambda request: calls.append(request)))
        with override_settings(SEARXNG_BASE_URL="https://searx.test", SEARXNG_API_KEY=""):
            with self.assertRaisesRegex(WebServiceError, "SEARXNG_API_KEY"):
                fetch_searxng_page("query", client=client)
        client.close()
        self.assertEqual(calls, [])

    def test_http_scheme_is_rejected_for_searxng(self):
        with override_settings(SEARXNG_BASE_URL="http://searx.test", SEARXNG_API_KEY="fixture-key"):
            with self.assertRaisesRegex(WebServiceError, "HTTPS"):
                fetch_searxng_page("query", client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200))))

    def test_invalid_key_response_is_reported_without_echoing_credentials(self):
        client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(403)))
        with override_settings(SEARXNG_BASE_URL="https://searx.test", SEARXNG_API_KEY="do-not-print-this"):
            with self.assertRaises(WebServiceError) as caught:
                fetch_searxng_page("query", client=client)
        client.close()
        self.assertIn("HTTP 403", str(caught.exception))
        self.assertNotIn("do-not-print-this", str(caught.exception))

    @override_settings(SEARXNG_ENABLED=True, SEARXNG_MAX_PAGES=2, SEARXNG_MAX_QUERIES=1)
    def test_search_paginates_and_deduplicates_normalized_urls_but_keeps_subdomains(self):
        calls = []

        def handler(request):
            calls.append(request)
            page = request.url.params.get("pageno")
            rows = [{"url": "https://example.ir/?utm_campaign=x", "title": "Main"}, {"url": "https://shop.example.ir/contact", "title": "Shop"}]
            if page == "2":
                rows = [{"url": "https://example.ir/", "title": "duplicate"}, {"url": "https://other.ir/contact", "title": "Other"}]
            return httpx.Response(200, json={"results": rows})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        with override_settings(SEARXNG_BASE_URL="https://searx.test", SEARXNG_API_KEY="fixture-key", WEB_SEARCH_MAX_RESULTS=10):
            rows = search_domains(make_job(), client=client)
        client.close()
        self.assertEqual(len(calls), 2)
        self.assertEqual([row["url"] for row in rows], ["https://example.ir/", "https://shop.example.ir/contact", "https://other.ir/contact"])
        self.assertEqual([call.url.params["pageno"] for call in calls], ["1", "2"])

    def test_empty_results_and_malformed_response_are_handled(self):
        empty_client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"results": []})))
        with override_settings(SEARXNG_BASE_URL="https://searx.test", SEARXNG_API_KEY="fixture-key"):
            self.assertEqual(fetch_searxng_page("query", client=empty_client), [])
        empty_client.close()
        malformed_client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"not json")))
        with override_settings(SEARXNG_BASE_URL="https://searx.test", SEARXNG_API_KEY="fixture-key"):
            with self.assertRaisesRegex(WebServiceError, "malformed JSON"):
                fetch_searxng_page("query", client=malformed_client)
        malformed_client.close()
        structure_client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"results": {"unexpected": True}})))
        with override_settings(SEARXNG_BASE_URL="https://searx.test", SEARXNG_API_KEY="fixture-key"):
            with self.assertRaisesRegex(WebServiceError, "unexpected JSON"):
                fetch_searxng_page("query", client=structure_client)
        structure_client.close()

    def test_http_400_is_not_retried_and_server_500_is_retried(self):
        bad_request = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(400)))
        with override_settings(SEARXNG_BASE_URL="https://searx.test", SEARXNG_API_KEY="fixture-key", SEARXNG_RETRIES=1):
            with self.assertRaises(WebServiceError) as caught:
                fetch_searxng_page("query", client=bad_request)
        bad_request.close()
        self.assertEqual(caught.exception.status_code, 400)

        calls = []
        def transient_server(request):
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(502)
            return httpx.Response(200, json={"results": []})
        server = httpx.Client(transport=httpx.MockTransport(transient_server))
        with override_settings(SEARXNG_BASE_URL="https://searx.test", SEARXNG_API_KEY="fixture-key", SEARXNG_RETRIES=1):
            self.assertEqual(fetch_searxng_page("query", client=server), [])
        server.close()
        self.assertEqual(len(calls), 2)

    def test_transient_network_error_retries_once_without_logging_request_data(self):
        calls = []

        def handler(request):
            calls.append(request)
            raise httpx.ConnectError("unreachable")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        with override_settings(SEARXNG_BASE_URL="https://searx.test", SEARXNG_API_KEY="fixture-key", SEARXNG_RETRIES=1):
            counter = [0]
            with self.assertRaises(WebServiceError) as caught:
                fetch_searxng_page("private query", client=client, request_counter=counter)
        client.close()
        self.assertEqual(len(calls), 2)
        self.assertEqual(counter[0], 2)
        self.assertNotIn("private query", str(caught.exception))

    def test_request_timeout_is_retried_once_and_sanitized(self):
        calls = []

        def handler(request):
            calls.append(request)
            raise httpx.ReadTimeout("timeout")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        with override_settings(SEARXNG_BASE_URL="https://searx.test", SEARXNG_API_KEY="fixture-key", SEARXNG_RETRIES=1):
            with self.assertRaises(WebServiceError) as caught:
                fetch_searxng_page("private query", client=client)
        client.close()
        self.assertEqual(len(calls), 2)
        self.assertIn("ReadTimeout", str(caught.exception))
        self.assertNotIn("private query", str(caught.exception))

    def test_searx_429_preserves_prior_page_results_and_sets_persistent_cooldown(self):
        calls = []

        def handler(request):
            calls.append(request)
            if request.url.params["pageno"] == "1":
                return httpx.Response(200, json={"results": [{
                    "url": "https://shop.example.ir", "title": "فروشگاه نمونه",
                    "content": "09123456789 فروش لوازم الکترونیکی",
                }]})
            return httpx.Response(429, headers={"Retry-After": "120"})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        job = make_job(requested=5, status=SearchJob.Status.RUNNING)
        execution = SourceExecution.objects.create(search_job=job, source_name="web")

        def fake_crawl(_url, request_counter=None):
            request_counter[0] = 2
            return []

        with override_settings(SEARXNG_BASE_URL="https://searx.test", SEARXNG_API_KEY="fixture-key", SEARXNG_MAX_PAGES=2, SEARXNG_MAX_QUERIES=1, SEARXNG_RETRIES=1, WEB_CRAWL_CONCURRENCY=1):
            with patch("leads.web_search._searxng_http_client", return_value=client), patch("leads.web_search.crawl_domain", side_effect=fake_crawl):
                run_web_lane(job, execution)
        execution.refresh_from_db()
        self.assertEqual(execution.status, SourceExecution.Status.RATE_LIMITED)
        self.assertEqual(execution.request_count, 4)
        self.assertEqual(len(calls), 2)  # HTTP 429 is not retried.
        self.assertTrue(job.contacts.filter(normalized_number="09123456789", business_name="فروشگاه نمونه").exists())
        self.assertGreaterEqual((SourceRateLimit.objects.get(source_name="searxng").cooldown_until - timezone.now()).total_seconds(), 115)

        later = make_job(requested=5, status=SearchJob.Status.RUNNING)
        later_execution = SourceExecution.objects.create(search_job=later, source_name="web")
        with patch("leads.web_search.search_domains") as search_again:
            run_web_lane(later, later_execution)
        later_execution.refresh_from_db()
        search_again.assert_not_called()
        self.assertEqual(later_execution.status, SourceExecution.Status.RATE_LIMITED)
        client.close()

    def test_url_normalization_strips_tracking_and_preserves_subdomain(self):
        self.assertEqual(_normalized_search_url("https://Shop.Example.ir/path/?utm_medium=x&ref=ads&id=4#section"), "https://shop.example.ir/path?id=4")

    def test_tls_client_uses_custom_ca_bundle_without_disabling_validation(self):
        with override_settings(SEARXNG_CA_BUNDLE="/etc/ssl/certs/searxng-ca.pem", SEARXNG_VERIFY_TLS=False):
            with patch("leads.web_search.ssl.create_default_context", return_value="verified-context") as context_factory, patch("leads.web_search.httpx.Client") as client_factory:
                from .web_search import _searxng_http_client
                _searxng_http_client()
        context_factory.assert_called_once_with(cafile="/etc/ssl/certs/searxng-ca.pem")
        self.assertEqual(client_factory.call_args.kwargs["verify"], "verified-context")

    def test_crawler_calls_self_hosted_v2_crawl_and_polls_until_complete(self):
        calls = []

        def handler(request):
            calls.append(request)
            self.assertEqual(request.headers.get("Authorization"), "Bearer fixture-key")
            if request.method == "POST":
                self.assertTrue(request.url.path.endswith("/v2/crawl"))
                self.assertEqual(json.loads(request.content)["limit"], 5)
                self.assertEqual(json.loads(request.content)["scrapeOptions"]["formats"], ["markdown", "html"])
                return httpx.Response(200, json={"id": "crawl-1"})
            return httpx.Response(200, json={"status": "completed", "data": [{"markdown": "تماس ۰۹۱۲۳۴۵۶۷۸۹", "metadata": {"sourceURL": "https://example.ir/contact"}}]})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        with override_settings(FIRECRAWL_BASE_URL="http://firecrawl.test", FIRECRAWL_API_KEY="fixture-key", WEB_CRAWL_MAX_PAGES_PER_DOMAIN=5, WEB_CRAWL_MAX_DEPTH=2, WEB_CRAWL_TIMEOUT=5):
            pages = crawl_domain("https://example.ir", client=client)
        client.close()
        self.assertEqual(len(pages), 1)
        self.assertEqual(len(calls), 2)

    def test_public_url_guard_rejects_private_hosts(self):
        self.assertEqual(_public_http_url("http://127.0.0.1/secret"), "")
        self.assertEqual(_public_http_url("file:///etc/passwd"), "")
        self.assertEqual(_public_http_url("https://example.ir/contact"), "https://example.ir/contact")

    def test_searx_connection_error_names_safe_endpoint_and_web_lane_records_it(self):
        def fail(_request):
            raise httpx.ConnectError("unreachable")
        client = httpx.Client(transport=httpx.MockTransport(fail))
        job = make_job(status=SearchJob.Status.RUNNING)
        execution = SourceExecution.objects.create(search_job=job, source_name="web")
        with override_settings(SEARXNG_ENABLED=True, SEARXNG_BASE_URL="https://127.0.0.1:8080/private?token=secret", SEARXNG_API_KEY="fixture-key"):
            with self.assertRaises(WebServiceError) as caught:
                search_domains(job, client=client)
            self.assertIn("https://127.0.0.1:8080", str(caught.exception))
            self.assertNotIn("secret", str(caught.exception))
        with patch("leads.web_search.search_domains", side_effect=caught.exception):
            run_web_lane(job, execution)
        execution.refresh_from_db()
        client.close()
        self.assertEqual(execution.status, SourceExecution.Status.FAILED)
        self.assertEqual(execution.request_count, 0)
        self.assertIn("SearXNG", execution.error_details)
        self.assertNotIn("secret", execution.error_details)

    def test_tls_error_explains_ca_and_hostname_remedies_without_disabling_verification(self):
        def fail(_request):
            raise httpx.ConnectError("certificate verify failed: IP address mismatch")
        client = httpx.Client(transport=httpx.MockTransport(fail))
        with override_settings(SEARXNG_BASE_URL="https://searx.test", SEARXNG_API_KEY="fixture-key", SEARXNG_RETRIES=0):
            with self.assertRaises(WebServiceError) as caught:
                fetch_searxng_page("query", client=client)
        client.close()
        self.assertIn("SEARXNG_CA_BUNDLE", str(caught.exception))
        self.assertIn("hostname that matches", str(caught.exception))

    @override_settings(WEB_SEARCH_ENABLED=True, WEB_CRAWL_MAX_PAGES_PER_DOMAIN=5, WEB_CRAWL_CONCURRENCY=2)
    def test_lane_saves_unique_mobile_contacts_and_stops_at_requested_target(self):
        job = make_job(requested=2, status=SearchJob.Status.RUNNING)
        execution = SourceExecution.objects.create(search_job=job, source_name="web")
        pages = [
            {"markdown": "شماره ۰۹۱۲۳۴۵۶۷۸۹ و +989123456780", "metadata": {"sourceURL": "https://one.ir/contact", "title": "فروشگاه اول", "description": "توضیح کوتاه"}},
            {"markdown": "تکراری 09123456789 و شمارهٔ دیگر 09123456781", "metadata": {"sourceURL": "https://two.ir/contact"}},
        ]
        def fake_crawl(url, request_counter=None):
            request_counter[0] = 2
            return pages[:1] if "one" in url else pages[1:]
        results = [
            {"url": "https://one.ir/", "title": "فروشگاه اول", "content": ""},
            {"url": "https://two.ir/", "title": "فروشگاه دوم", "content": ""},
        ]
        def fake_search(_job, request_counter=None):
            request_counter[0] = 1
            return results
        with patch("leads.web_search.search_domains", side_effect=fake_search), patch("leads.web_search.crawl_domain", side_effect=fake_crawl):
            count = run_web_lane(job, execution)
        self.assertEqual(count, 2)
        self.assertEqual(job.contacts.count(), 2)
        self.assertEqual(execution.status, SourceExecution.Status.COMPLETED)
        self.assertEqual(execution.request_count, 5)
        self.assertEqual(set(job.contacts.values_list("normalized_number", flat=True)), {"09123456789", "09123456780"})
        contact = job.contacts.get(normalized_number="09123456789")
        self.assertEqual(contact.business_name, "فروشگاه اول")
        self.assertEqual(contact.website, "https://one.ir")
        self.assertEqual(contact.description, "توضیح کوتاه")

    def test_regex_extracts_a_mobile_inside_html_tel_link(self):
        candidates = extract_iranian_mobiles('<a href="tel:+989123456789">تماس</a>', path="contact_page")
        self.assertEqual([item.normalized_number for item in candidates], ["+989123456789"])

    def test_firecrawl_timeout_is_partial_and_does_not_discard_existing_results(self):
        job = make_job(requested=5, status=SearchJob.Status.RUNNING)
        SourceExecution.objects.create(search_job=job, source_name="web")
        execution = SourceExecution.objects.get(search_job=job, source_name="web")
        with patch("leads.web_search.search_domains", return_value=[{"url": "https://one.ir", "title": "", "content": ""}, {"url": "https://two.ir", "title": "", "content": ""}]), patch("leads.web_search.crawl_domain", side_effect=[TimeoutError("fixture timeout"), []]):
            run_web_lane(job, execution)
        self.assertEqual(execution.status, SourceExecution.Status.PARTIAL)
        self.assertEqual(execution.error_count, 1)


class ParallelJobTests(TransactionTestCase):
    def test_cancel_job_retries_transient_sqlite_lock(self):
        job = make_job(status=SearchJob.Status.RUNNING)
        SourceExecution.objects.create(search_job=job, source_name="web", status=SourceExecution.Status.RUNNING)
        client = Client()
        client.force_login(job.owner)
        real_atomic = db_transaction.atomic
        with patch("leads.views.transaction.atomic", side_effect=[OperationalError("database is locked"), real_atomic()]):
            response = client.post(reverse("cancel_job", args=[job.pk]))
        job.refresh_from_db()
        execution = SourceExecution.objects.get(search_job=job, source_name="web")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(job.status, SearchJob.Status.CANCELLED)
        self.assertEqual(execution.status, SourceExecution.Status.CANCELLED)

    def test_cancel_job_updates_active_rows_in_one_short_transaction(self):
        job = make_job(status=SearchJob.Status.QUEUED)
        SourceExecution.objects.create(search_job=job, source_name="web")
        client = Client()
        client.force_login(job.owner)
        response = client.post(reverse("cancel_job", args=[job.pk]))
        job.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(job.status, SearchJob.Status.CANCELLED)
        self.assertEqual(job.source_executions.get(source_name="web").status, SourceExecution.Status.CANCELLED)

    def test_cancel_job_returns_retryable_response_if_sqlite_remains_locked(self):
        job = make_job(status=SearchJob.Status.RUNNING)
        client = Client()
        client.force_login(job.owner)
        with patch("leads.views.transaction.atomic", side_effect=[OperationalError("database is locked") for _ in range(4)]):
            response = client.post(reverse("cancel_job", args=[job.pk]))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response["Retry-After"], "2")
        job.refresh_from_db()
        self.assertEqual(job.status, SearchJob.Status.RUNNING)

    def test_all_four_lanes_start_concurrently_and_source_error_is_isolated(self):
        job = make_job(requested=6)
        SourceExecution.objects.bulk_create([SourceExecution(search_job=job, source_name=name) for name in job.selected_sources])
        barrier = threading.Barrier(4)
        seen = []

        def fake_mcp(source, current_job, execution):
            barrier.wait(timeout=4)
            seen.append(source)
            execution.status = SourceExecution.Status.FAILED if source == "balad" else SourceExecution.Status.COMPLETED
            execution.error_count = int(source == "balad")
            execution.error_details = "fixture source failure" if source == "balad" else ""
            execution.save(update_fields=["status", "error_count", "error_details"])

        def fake_web(current_job, execution):
            barrier.wait(timeout=4)
            seen.append("web")
            execution.status = SourceExecution.Status.COMPLETED
            execution.save(update_fields=["status"])
            return 0

        with patch("leads.tasks.execute_source", side_effect=fake_mcp), patch("leads.tasks.run_web_lane", side_effect=fake_web):
            result = run_search_job.run(job.pk)
        job.refresh_from_db()
        self.assertCountEqual(seen, ["neshan", "balad", "emalls", "web"])
        self.assertEqual(job.status, SearchJob.Status.PARTIAL)
        self.assertEqual(result["requested"], 6)

    def test_json_and_excel_include_requested_business_contact_fields(self):
        job = make_job(status=SearchJob.Status.COMPLETED)
        JobContact.objects.create(search_job=job, normalized_number="09123456789", source_name="balad", business_name="فروشگاه نمونه", website="https://shop.example", address="نشانی", description="توضیحات")
        user = job.owner
        client = Client()
        client.force_login(user)
        payload = json.loads(client.get(reverse("export_json", args=[job.pk])).content)
        self.assertEqual(payload["results"], [{"name": "فروشگاه نمونه", "mobile": "09123456789", "source": "بلد", "website": "https://shop.example", "address": "نشانی", "description": "توضیحات"}])
        workbook = client.get(reverse("export_excel", args=[job.pk]))
        self.assertEqual(workbook.status_code, 200)
        sheet = load_workbook(BytesIO(workbook.content), read_only=True).active
        self.assertEqual(next(sheet.iter_rows(values_only=True)), ("نام کسب‌وکار", "شماره موبایل", "منبع", "وب‌سایت", "نشانی", "توضیحات"))
        self.assertEqual(next(sheet.iter_rows(min_row=2, values_only=True)), ("فروشگاه نمونه", "09123456789", "بلد", "https://shop.example", "نشانی", "توضیحات"))

    def test_search_submission_creates_fixed_four_lanes_and_stores_requested_count(self):
        user = get_user_model().objects.create_user(username="search-view")
        client = Client()
        client.force_login(user)
        with patch("leads.views.run_search_job.delay", return_value=SimpleNamespace(id="task-123")):
            response = client.post(reverse("search"), {
                "trade_name": "کافه", "geographic_scope_type": "city", "geographic_scope_name": "اصفهان",
                "requested_phone_count": 25,
            })
        self.assertEqual(response.status_code, 302)
        job = SearchJob.objects.get(owner=user)
        self.assertEqual(job.requested_phone_count, 25)
        self.assertCountEqual(job.source_executions.values_list("source_name", flat=True), ["neshan", "balad", "emalls", "web"])
