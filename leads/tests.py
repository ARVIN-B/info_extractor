import asyncio
import json
from contextlib import asynccontextmanager
from datetime import timedelta
from io import BytesIO
from unittest.mock import AsyncMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from mcp.types import TextContent
from openpyxl import load_workbook

from .mcp_client import MCPCallResult, MCPSourceError, MCPToolClient, decode_result
from .models import BusinessLead, LeadEvidence, SearchJob, SourceExecution, SourceToolCall
from .normalization import normalize_phone, normalize_text, normalize_website, phone_is_valid
from .sources import calculate_source_budget, execute_source, save_lead
from .tasks import recover_stale_search_jobs, run_search_job


class NormalizationTests(TestCase):
    def test_persian_characters_and_digits(self):
        self.assertEqual(normalize_text("كافه ياس ۱۲"), normalize_text("کافه یاس 12"))

    def test_iranian_phone_formats(self):
        self.assertEqual(normalize_phone("+98 912 345 6789"), "09123456789")
        self.assertEqual(normalize_phone("۰۹۱۲۳۴۵۶۷۸۹"), "09123456789")
        self.assertTrue(phone_is_valid("021-12345678"))
        self.assertFalse(phone_is_valid("12345"))

    def test_website_normalization(self):
        self.assertEqual(normalize_website("http://www.Example.com/")[1], "example.com")
        self.assertEqual(normalize_website("not a domain"), ("", ""))

    def test_result_budget_reserves_an_initial_share_for_each_source(self):
        self.assertEqual(calculate_source_budget(100, 2, 100, 0), 50)
        self.assertEqual(calculate_source_budget(100, 2, 50, 1), 50)
        self.assertEqual(calculate_source_budget(1, 2, 1, 0), 1)


class LeadPersistenceTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="tester", password="pass1234")
        self.job = SearchJob.objects.create(owner=self.user, trade_name="رستوران", geographic_scope_type="city", geographic_scope_name="تهران", selected_sources=["neshan", "balad"])

    def test_same_source_identifier_updates_one_record_and_keeps_evidence(self):
        search = {"id": "a" * 32, "name": "کافه آفتاب", "phone": "09123456789", "address": "خیابان ولیعصر، پلاک ۱"}
        save_lead(self.job, "neshan", search, {"id": search["id"], "name": search["name"], "phones": [search["phone"]], "address": search["address"], "website": "https://example.com"})
        save_lead(self.job, "neshan", search, {"id": search["id"], "name": search["name"], "phones": [search["phone"]], "address": search["address"], "website": "https://example.com"})
        self.assertEqual(self.job.leads.count(), 1)
        self.assertEqual(self.job.leads.get().source_record_ids["neshan"], search["id"])
        self.assertEqual(LeadEvidence.objects.filter(business_lead__search_job=self.job, field_name="raw_response").count(), 2)

    def test_cross_source_match_keeps_both_evidence_and_distinct_branches(self):
        first = {"id": "a" * 32, "name": "کافه آفتاب", "phone": "09123456789", "address": "خیابان ولیعصر، پلاک ۱"}
        second = {"id": "AbCdEf123456", "name": "کافه آفتاب", "phone": "۰۹۱۲۳۴۵۶۷۸۹", "address": "خیابان ولیعصر، پلاک ۱"}
        save_lead(self.job, "neshan", first, {"id": first["id"], "name": first["name"], "phones": [first["phone"]], "address": first["address"]})
        merged = save_lead(self.job, "balad", second, {"id": second["id"], "name": second["name"], "phones": [second["phone"]], "address": second["address"]})
        self.assertEqual(self.job.leads.count(), 1)
        self.assertCountEqual(merged.source_names, ["neshan", "balad"])
        self.assertEqual(merged.verification_status, BusinessLead.Verification.CROSS_SOURCE)
        branch = {**second, "id": "ZzYyXx789012", "address": "خیابان ولیعصر، پلاک ۲۰"}
        save_lead(self.job, "balad", branch, {"id": branch["id"], "name": branch["name"], "phones": [branch["phone"]], "address": branch["address"]})
        self.assertEqual(self.job.leads.count(), 2)

    def test_failed_place_detail_keeps_search_record_and_continues_source(self):
        self.job.selected_sources = ["neshan"]
        self.job.max_results = 2
        self.job.save(update_fields=["selected_sources", "max_results"])
        execution = SourceExecution.objects.create(search_job=self.job, source_name="neshan")

        class FakeClient:
            request_count = 0

            async def call(self, tool_name, arguments):
                self.request_count += 1
                if tool_name == "ns_search":
                    rows = [
                        {"id": "a" * 32, "name": "کافه اول", "phone": "02112345678", "address": "تهران، نشانی اول"},
                        {"id": "b" * 32, "name": "کافه دوم", "phone": "02112345679", "address": "تهران، نشانی دوم"},
                    ]
                    return MCPCallResult({"results": rows}, 1)
                if arguments["place_id"] == "a" * 32:
                    raise MCPSourceError("detail endpoint unavailable")
                return MCPCallResult({"id": arguments["place_id"], "name": "کافه دوم", "phones": ["02112345679"], "address": "تهران، نشانی دوم"}, 1)

        @asynccontextmanager
        async def fake_session(source, **kwargs):
            yield FakeClient()

        with patch("leads.sources.source_session", fake_session):
            count = execute_source("neshan", self.job, execution)
        execution.refresh_from_db()
        self.assertEqual(count, 2)
        self.assertEqual(self.job.leads.count(), 2)
        self.assertEqual(execution.status, SourceExecution.Status.FAILED)
        self.assertEqual(execution.error_count, 1)
        self.assertIn("detail endpoint unavailable", execution.error_details)
        self.assertEqual(SourceToolCall.objects.filter(source_execution=execution, error_summary__gt="").count(), 1)

    def test_conflicting_source_values_are_preserved_as_evidence(self):
        search = {"id": "a" * 32, "name": "کافه آفتاب", "phone": "09123456789", "address": "خیابان ولیعصر، پلاک ۱"}
        lead = save_lead(self.job, "neshan", search, {"name": search["name"], "phones": [search["phone"]], "address": search["address"], "website": "https://first.example"})
        save_lead(self.job, "neshan", search, {"name": search["name"], "phones": ["02112345678"], "address": search["address"], "website": "https://second.example"})
        lead.refresh_from_db()
        self.assertEqual(lead.website, "https://first.example")
        self.assertEqual(lead.verification_status, BusinessLead.Verification.CONFLICTING)
        self.assertGreaterEqual(lead.evidence.filter(field_name="website").count(), 2)


class MCPClientTests(TestCase):
    def test_schema_validation_and_allowed_tools(self):
        tool = type("Tool", (), {"input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}})()
        session = type("Session", (), {"call_tool": AsyncMock(return_value=type("Response", (), {"isError": False, "structuredContent": {"results": []}, "content": []})())})()
        client = MCPToolClient("neshan", session, {"ns_search": tool})
        output = asyncio.run(client.call("ns_search", {"query": "طلافروشی"}))
        self.assertEqual(output.data, {"results": []})
        with self.assertRaises(MCPSourceError):
            asyncio.run(client.call("ns_search", {"bad": "arg"}))
        with self.assertRaises(MCPSourceError):
            asyncio.run(client.call("ns_nearby", {"place_id": "x"}))

    def test_real_stdio_client_uses_mock_server_tool_list_and_call(self):
        class FakeSession:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return None
            async def initialize(self): return None
            async def list_tools(self):
                schema = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
                return type("Listed", (), {"tools": [type("Tool", (), {"name": name, "input_schema": schema})() for name in ("ns_search", "ns_place")]})()
            async def call_tool(self, name, args):
                return type("Response", (), {"isError": False, "structuredContent": {"results": [{"id": "1"}]}, "content": []})()
        class FakeStdio:
            async def __aenter__(self): return (object(), object())
            async def __aexit__(self, *args): return None
        with patch("leads.mcp_client.stdio_client", return_value=FakeStdio()), patch("leads.mcp_client.ClientSession", return_value=FakeSession()):
            async def exercise():
                from .mcp_client import source_session
                async with source_session("neshan") as client:
                    return await client.call("ns_search", {"query": "کافه"})
            output = asyncio.run(exercise())
        self.assertEqual(output.data["results"][0]["id"], "1")

    def test_tool_error_response(self):
        response = type("Response", (), {"isError": True, "structuredContent": None, "content": [TextContent(type="text", text="unavailable")]})()
        with self.assertRaises(MCPSourceError):
            decode_result(response)

    def test_transient_connection_error_retries_once(self):
        response = type("Response", (), {"isError": False, "structuredContent": {"results": []}, "content": []})()
        session = type("Session", (), {"call_tool": AsyncMock(side_effect=[OSError("temporary"), response])})()
        tool = type("Tool", (), {"input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}})()
        client = MCPToolClient("neshan", session, {"ns_search": tool})
        with patch("leads.mcp_client.asyncio.sleep", new=AsyncMock()):
            output = asyncio.run(client.call("ns_search", {"query": "کافه"}))
        self.assertEqual(output.data, {"results": []})
        self.assertEqual(client.request_count, 2)
        self.assertEqual(session.call_tool.await_count, 2)

    def test_distributed_source_limit_releases_redis_lock(self):
        response = type("Response", (), {"isError": False, "structuredContent": {"results": []}, "content": []})()
        session = type("Session", (), {"call_tool": AsyncMock(return_value=response)})()
        tool = type("Tool", (), {"input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}})()

        class FakeLock:
            acquired = False
            released = False
            options = None

            def acquire(self, blocking=True):
                self.acquired = True
                return True

            def release(self):
                self.released = True

        class FakeRedis:
            closed = False
            lock_instance = FakeLock()

            def lock(self, name, **options):
                self.lock_instance.options = (name, options)
                return self.lock_instance

            def close(self):
                self.closed = True

        fake_redis = FakeRedis()
        client = MCPToolClient("neshan", session, {"ns_search": tool}, distributed_limit=True)
        with patch("leads.mcp_client.Redis.from_url", return_value=fake_redis):
            result = asyncio.run(client.call("ns_search", {"query": "کافه"}))
        self.assertEqual(result.data, {"results": []})
        self.assertTrue(fake_redis.lock_instance.acquired)
        self.assertTrue(fake_redis.lock_instance.released)
        self.assertTrue(fake_redis.closed)
        self.assertEqual(fake_redis.lock_instance.options[0], "info-extractor:mcp-source:neshan")


class JobAndExportTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="staff", password="pass12345")
        self.other = get_user_model().objects.create_user(username="other", password="pass12345")
        self.job = SearchJob.objects.create(owner=self.user, trade_name="کلینیک", geographic_scope_type="city", geographic_scope_name="تهران", selected_sources=["neshan", "balad"])
        self.executions = [SourceExecution.objects.create(search_job=self.job, source_name=name) for name in self.job.selected_sources]
        self.lead = BusinessLead.objects.create(search_job=self.job, normalized_name="کلینیک نمونه", original_name="کلینیک نمونه", phone_numbers=["09123456789"], address="تهران", city="تهران", website="https://example.com", source_names=["neshan"], source_record_ids={"neshan": "a" * 32})
        LeadEvidence.objects.create(business_lead=self.lead, source_name="neshan", source_record_id="a" * 32, source_url="https://neshan.org/maps/places/" + "a" * 32, field_name="phone", field_value="09123456789", raw_response={"phone": "09123456789"})

    def test_job_partial_success_transition(self):
        def fake_execute(source, job, execution):
            execution.status = SourceExecution.Status.COMPLETED if source == "balad" else SourceExecution.Status.FAILED
            execution.result_count = 1 if source == "balad" else 0
            execution.save(update_fields=["status", "result_count"])
            return 1 if source == "balad" else 0
        with patch("leads.tasks.execute_source", side_effect=fake_execute) as execute:
            result = run_search_job.apply(args=(self.job.pk,)).get()
        self.job.refresh_from_db()
        self.assertEqual(execute.call_count, 2)
        self.assertEqual(result["status"], SearchJob.Status.PARTIAL)
        self.assertEqual(self.job.total_unique_businesses, 1)

    def test_failed_source_with_partial_records_keeps_partial_job_state(self):
        def failed_after_results(source, job, execution):
            execution.status = SourceExecution.Status.FAILED
            execution.error_count = 1
            execution.error_details = "temporary upstream error"
            execution.save(update_fields=["status", "error_count", "error_details"])
            return 0
        with patch("leads.tasks.execute_source", side_effect=failed_after_results):
            result = run_search_job.apply(args=(self.job.pk,)).get()
        self.assertEqual(result["status"], SearchJob.Status.PARTIAL)

    def test_new_search_enqueues_job_without_running_work_in_request(self):
        self.client.force_login(self.user)
        with patch("leads.views.run_search_job.delay") as enqueue:
            response = self.client.post(reverse("search"), {
                "trade_name": "طلافروشی", "geographic_scope_type": "city", "geographic_scope_name": "تهران",
                "sources": ["neshan", "balad"], "max_results": 20,
            })
        self.assertEqual(response.status_code, 302)
        created = SearchJob.objects.exclude(pk=self.job.pk).get()
        enqueue.assert_called_once_with(created.pk)
        self.assertEqual(created.status, SearchJob.Status.QUEUED)
        self.assertEqual(created.source_executions.count(), 2)

    def test_filters_work_with_sqlite_json_fields(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("job_detail", args=[self.job.pk]), {"source": "neshan", "has_phone": "1", "has_website": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].paginator.count, 1)

    def test_stale_worker_job_is_requeued_and_completed_sources_are_kept(self):
        self.job.status = SearchJob.Status.RUNNING
        self.job.started_at = timezone.now() - timedelta(minutes=25)
        self.job.save(update_fields=["status", "started_at"])
        self.executions[0].status = SourceExecution.Status.COMPLETED
        self.executions[0].save(update_fields=["status"])
        with patch("leads.tasks.run_search_job.delay") as enqueue:
            result = recover_stale_search_jobs.apply().get()
        self.assertEqual(result["requeued"], 1)
        enqueue.assert_called_once_with(self.job.pk)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, SearchJob.Status.QUEUED)
        self.executions[0].refresh_from_db()
        self.executions[1].refresh_from_db()
        self.assertEqual(self.executions[0].status, SourceExecution.Status.COMPLETED)
        self.assertEqual(self.executions[1].status, SourceExecution.Status.QUEUED)

    def test_zero_results_from_healthy_sources_completes_job(self):
        def fake_empty(source, job, execution):
            execution.status = SourceExecution.Status.COMPLETED
            execution.save(update_fields=["status"])
            return 0
        with patch("leads.tasks.execute_source", side_effect=fake_empty):
            result = run_search_job.apply(args=(self.job.pk,)).get()
        self.assertEqual(result["status"], SearchJob.Status.COMPLETED)

    def test_excel_has_lead_and_evidence_sheets(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("export_excel", args=[self.job.pk]))
        workbook = load_workbook(BytesIO(response.content), read_only=True)
        self.assertEqual(workbook.sheetnames, ["سرنخ‌ها", "شواهد"])
        self.assertEqual(workbook["سرنخ‌ها"]["A1"].value, "نام کسب‌وکار")
        self.assertEqual(workbook["شواهد"].max_row, 2)

    def test_search_and_exports_require_owner(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("job_detail", args=[self.job.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("export_json", args=[self.job.pk])).status_code, 200)
        excel = self.client.get(reverse("export_excel", args=[self.job.pk]))
        self.assertEqual(excel.status_code, 200)
        self.assertTrue(excel.content.startswith(b"PK"))
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("job_detail", args=[self.job.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("export_json", args=[self.job.pk])).status_code, 404)

    def test_json_export_uses_database_and_contains_provenance(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("export_json", args=[self.job.pk]))
        payload = json.loads(response.content)
        self.assertEqual(payload["results"][0]["name"], self.lead.original_name)
        self.assertEqual(payload["results"][0]["evidence"][0]["source"], "neshan")
