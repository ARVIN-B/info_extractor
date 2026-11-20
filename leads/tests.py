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
from openpyxl import load_workbook

from .adapters import _with_phone_filter
from .forms import SearchJobForm
from .mcp_client import MCPSourceError, SOURCE_REGISTRY
from .models import JobContact, SearchJob, SourceExecution, SourceRateLimit
from .normalization import extract_iranian_mobiles, normalize_iranian_mobile, normalize_phone
from .sources import execute_source
from .tasks import run_search_job
from .web_search import _public_http_url, crawl_domain, run_web_lane, search_domains


def make_job(*, requested=3, status=SearchJob.Status.QUEUED):
    user = get_user_model().objects.create_user(username=f"test-{threading.get_ident()}")
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
    def test_search_uses_searx_json_and_deduplicates_domains(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={"results": [
                {"url": "https://www.example.ir/shops"}, {"url": "https://example.ir/contact"},
                {"url": "http://127.0.0.1/private"}, {"url": "https://other.ir/contact"},
            ]})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        job = make_job()
        with override_settings(SEARXNG_BASE_URL="http://searx.test", WEB_SEARCH_ENABLED=True, WEB_SEARCH_MAX_RESULTS=10):
            results = search_domains(job, client=client)
        client.close()
        self.assertEqual(results, ["https://www.example.ir/shops", "https://other.ir/contact"])
        self.assertTrue(all(request.url.params.get("format") == "json" for request in calls))
        self.assertIn("اصفهان", calls[0].url.params["q"])

    def test_crawler_calls_self_hosted_v2_crawl_and_polls_until_complete(self):
        calls = []

        def handler(request):
            calls.append(request)
            self.assertEqual(request.headers.get("Authorization"), "Bearer fixture-key")
            if request.method == "POST":
                self.assertTrue(request.url.path.endswith("/v2/crawl"))
                self.assertEqual(json.loads(request.content)["limit"], 5)
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

    @override_settings(WEB_SEARCH_ENABLED=True, WEB_CRAWL_MAX_PAGES_PER_DOMAIN=5, WEB_CRAWL_CONCURRENCY=2)
    def test_lane_saves_unique_mobile_contacts_and_stops_at_requested_target(self):
        job = make_job(requested=2, status=SearchJob.Status.RUNNING)
        execution = SourceExecution.objects.create(search_job=job, source_name="web")
        pages = [
            {"markdown": "شماره ۰۹۱۲۳۴۵۶۷۸۹ و +989123456780", "metadata": {"sourceURL": "https://one.ir/contact"}},
            {"markdown": "تکراری 09123456789 و شمارهٔ دیگر 09123456781", "metadata": {"sourceURL": "https://two.ir/contact"}},
        ]
        with patch("leads.web_search.search_domains", return_value=["https://one.ir", "https://two.ir"]), patch("leads.web_search.crawl_domain", side_effect=[pages[:1], pages[1:]]):
            count = run_web_lane(job, execution)
        self.assertEqual(count, 2)
        self.assertEqual(job.contacts.count(), 2)
        self.assertEqual(execution.status, SourceExecution.Status.COMPLETED)
        self.assertEqual(set(job.contacts.values_list("normalized_number", flat=True)), {"09123456789", "09123456780"})

    def test_regex_extracts_a_mobile_inside_html_tel_link(self):
        candidates = extract_iranian_mobiles('<a href="tel:+989123456789">تماس</a>', path="contact_page")
        self.assertEqual([item.normalized_number for item in candidates], ["+989123456789"])

    def test_firecrawl_timeout_is_partial_and_does_not_discard_existing_results(self):
        job = make_job(requested=5, status=SearchJob.Status.RUNNING)
        SourceExecution.objects.create(search_job=job, source_name="web")
        execution = SourceExecution.objects.get(search_job=job, source_name="web")
        with patch("leads.web_search.search_domains", return_value=["https://one.ir", "https://two.ir"]), patch("leads.web_search.crawl_domain", side_effect=[TimeoutError("fixture timeout"), []]):
            run_web_lane(job, execution)
        self.assertEqual(execution.status, SourceExecution.Status.PARTIAL)
        self.assertEqual(execution.error_count, 1)


class ParallelJobTests(TransactionTestCase):
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

    def test_json_and_excel_contain_only_mobile_source_and_optional_address(self):
        job = make_job(status=SearchJob.Status.COMPLETED)
        JobContact.objects.create(search_job=job, normalized_number="09123456789", source_name="balad", address="نشانی")
        user = job.owner
        client = Client()
        client.force_login(user)
        payload = json.loads(client.get(reverse("export_json", args=[job.pk])).content)
        self.assertEqual(payload["results"], [{"mobile": "09123456789", "source": "بلد", "address": "نشانی"}])
        self.assertEqual(set(payload["results"][0]), {"mobile", "source", "address"})
        workbook = client.get(reverse("export_excel", args=[job.pk]))
        self.assertEqual(workbook.status_code, 200)
        sheet = load_workbook(BytesIO(workbook.content), read_only=True).active
        self.assertEqual(next(sheet.iter_rows(values_only=True)), ("شماره موبایل", "منبع", "نشانی"))
        self.assertEqual(next(sheet.iter_rows(min_row=2, values_only=True)), ("09123456789", "بلد", "نشانی"))

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
