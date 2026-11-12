import asyncio
import json
from contextlib import asynccontextmanager
from datetime import timedelta
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from mcp.types import TextContent
from openpyxl import load_workbook

from .adapters import RasmioAdapter, _arguments
from .mcp_client import MCPCallResult, MCPSourceError, MCPToolClient, decode_result
from .forms import SearchJobForm
from .models import BusinessLead, LeadEvidence, SearchJob, SourceExecution, SourcePlaceDetailCache, SourceRateLimit, SourceToolCall
from .normalization import normalize_phone, normalize_text, normalize_website, phone_is_valid
from .sources import _cached_source_detail, _store_source_detail, calculate_source_budget, execute_source, get_scope_points, get_trade_variants, is_relevant_trade_record, save_lead, source_skip_reason
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

    def test_generic_trade_variants_normalize_persian_plural_and_shop_wording(self):
        self.assertEqual(get_trade_variants("شیشه فروشی های"), ["شیشه فروشی", "فروشگاه شیشه", "شیشه سرای"])
        self.assertEqual(get_trade_variants("رستوران ها"), ["رستوران", "غذاخوری"])
        self.assertEqual(get_trade_variants("آتلیه های"), ["آتلیه"])
        self.assertEqual(get_trade_variants("کافه"), ["کافه"])

    def test_trade_relevance_keeps_matching_shop_categories_and_drops_unrelated_names(self):
        variants = get_trade_variants("شیشه فروشی های")
        self.assertTrue(is_relevant_trade_record("شیشه فروشی های", variants, {"name": "آینه فروشی", "category": "فروشگاه شیشه و آینه"}))
        self.assertTrue(is_relevant_trade_record("شیشه فروشی های", variants, {"name": "شیشه سرای فدک", "category": "فروشگاه"}))
        self.assertFalse(is_relevant_trade_record("شیشه فروشی های", variants, {"name": "ترمیم ترک شیشه خودرو", "category": "تعمیرات خودرو"}))

    def test_city_scope_accepts_a_small_typo_and_uses_the_canonical_center(self):
        job = SimpleNamespace(geographic_scope_type=SearchJob.ScopeType.CITY, geographic_scope_name="اصفها")
        points = get_scope_points(job)
        self.assertEqual(points[0][0], "اصفهان")
        self.assertIsNotNone(points[0][1])

    def test_search_form_canonicalizes_a_small_city_typo(self):
        form = SearchJobForm(data={
            "trade_name": "شیشه فروشی های", "geographic_scope_type": "city", "geographic_scope_name": "اصفها",
            "sources": ["neshan", "balad"], "max_results": 100,
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["geographic_scope_name"], "اصفهان")

    def test_source_planner_keeps_maps_and_explains_incompatible_catalog_sources(self):
        self.assertEqual(source_skip_reason("کافه", "neshan"), "")
        self.assertIn("فروشگاه", source_skip_reason("کافه", "emalls"))
        self.assertIn("شرکت", source_skip_reason("کافه", "rasmio"))
        self.assertEqual(source_skip_reason("فروشگاه اینترنتی لوازم خانگی", "emalls"), "")

    def test_incompatible_source_is_marked_skipped_without_starting_mcp(self):
        user = get_user_model().objects.create_user(username="planner", password="pass12345")
        job = SearchJob.objects.create(owner=user, trade_name="کافه", geographic_scope_type="city", geographic_scope_name="تهران", selected_sources=["emalls"])
        execution = SourceExecution.objects.create(search_job=job, source_name="emalls")
        with patch("leads.sources.source_session", side_effect=AssertionError("irrelevant source must not start")):
            self.assertEqual(execute_source("emalls", job, execution), 0)
        execution.refresh_from_db()
        self.assertEqual(execution.status, SourceExecution.Status.SKIPPED)
        self.assertIn("فروشگاه", execution.error_details)

    def test_adapter_maps_only_schema_supported_search_arguments(self):
        tool = SimpleNamespace(input_schema={"type": "object", "properties": {"query": {"type": "string"}, "city": {"type": "string"}, "page_size": {"type": "integer"}}, "required": ["query"]})
        client = SimpleNamespace(tools={"rs_search_companies": tool})
        self.assertEqual(_arguments(client, "rs_search_companies", {"query": "شرکت نرم‌افزاری", "city": "اصفهان", "province": "اصفهان", "page": 1, "limit": 10}), {"query": "شرکت نرم‌افزاری", "city": "اصفهان", "page_size": 10})
        id_tool = SimpleNamespace(input_schema={"type": "object", "properties": {"shop_id": {"type": "integer"}}, "required": ["shop_id"]})
        vendor_tool = SimpleNamespace(input_schema={"type": "object", "properties": {"vendor": {"type": "string"}}, "required": ["vendor"]})
        typed_client = SimpleNamespace(tools={"em_shop": id_tool, "bs_vendor": vendor_tool})
        self.assertEqual(_arguments(typed_client, "em_shop", {"shop_id": "12"}), {"shop_id": 12})
        self.assertEqual(_arguments(typed_client, "bs_vendor", {"shop_id": "shop-12"}), {"vendor": "shop-12"})

    def test_rasmio_adapter_uses_public_company_search_without_consuming_profile_quota(self):
        class FakeClient:
            tools = {"rs_search_companies": SimpleNamespace(input_schema={"type": "object", "properties": {"query": {"type": "string"}, "city": {"type": "string"}, "page": {"type": "integer"}, "page_size": {"type": "integer"}}, "required": ["query"]})}

        calls = []
        async def invoke(client, name, arguments):
            calls.append((name, arguments))
            rows = [{"company_id": f"101003607{i:02d}", "name": f"شرکت نمونه {i}", "activity": "نرم‌افزار"} for i in range(20)] if arguments.get("page") == 1 else [{"company_id": "10100360800", "name": "شرکت آخر"}]
            return MCPCallResult({"companies": rows}, 1)
        async def run():
            return await RasmioAdapter().discover(FakeClient(), invoke, "شرکت نرم‌افزاری", "اصفهان", "", 40)
        result = asyncio.run(run())
        rows = result.records
        self.assertEqual(len(rows), 21)
        self.assertEqual(rows[0][0]["national_id"], "10100360700")
        self.assertEqual(calls[0][0], "rs_search_companies")
        self.assertEqual([call[1]["page"] for call in calls], [1, 2])


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

    def test_map_place_url_is_provenance_not_the_business_website(self):
        search = {"id": "a" * 32, "name": "کافه آفتاب", "website": "", "address": "تهران"}
        map_url = f"https://neshan.org/maps/places/{search['id']}"
        lead = save_lead(self.job, "neshan", search, {"url": map_url})
        self.assertEqual(lead.website, "")
        self.assertEqual(lead.evidence.get(field_name="raw_response").source_url, map_url)

        lead = save_lead(self.job, "neshan", search, {"url": map_url, "website": "https://business.example.ir"})
        lead.refresh_from_db()
        self.assertEqual(lead.website, "https://business.example.ir")

    def test_map_details_use_sanitized_expiring_cache(self):
        detail = {"name": "کافه نمونه", "website": "https://business.example.ir", "url": "https://neshan.org/maps/places/abc", "ceo": "شخص حقیقی"}
        _store_source_detail("neshan", "abc", detail)
        cached = _cached_source_detail("neshan", "abc")
        self.assertEqual(cached["website"], "https://business.example.ir")
        self.assertNotIn("ceo", cached)
        cache_row = SourcePlaceDetailCache.objects.get(source_name="neshan", source_record_id="abc")
        cache_row.expires_at = timezone.now() - timedelta(seconds=1)
        cache_row.save(update_fields=["expires_at"])
        self.assertIsNone(_cached_source_detail("neshan", "abc"))

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
        self.job.trade_name = "کافه"
        self.job.selected_sources = ["neshan"]
        self.job.max_results = 2
        self.job.save(update_fields=["trade_name", "selected_sources", "max_results"])
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
        self.assertEqual(execution.status, SourceExecution.Status.PARTIAL)
        self.assertEqual(execution.error_count, 1)
        self.assertIn("detail endpoint unavailable", execution.error_details)
        self.assertEqual(SourceToolCall.objects.filter(source_execution=execution, error_summary__gt="").count(), 1)

    def test_cached_place_detail_avoids_another_upstream_detail_call(self):
        self.job.trade_name = "کافه"
        self.job.selected_sources = ["neshan"]
        self.job.max_results = 1
        self.job.save(update_fields=["trade_name", "selected_sources", "max_results"])
        execution = SourceExecution.objects.create(search_job=self.job, source_name="neshan")
        identifier = "d" * 32
        _store_source_detail("neshan", identifier, {"name": "کافه نمونه", "phone": "02112345678", "website": "https://business.example.ir"})

        class FakeClient:
            request_count = 0
            async def call(self, tool_name, arguments):
                self.request_count += 1
                if tool_name == "ns_search":
                    return MCPCallResult({"results": [{"id": identifier, "name": "کافه نمونه"}]}, 1)
                raise AssertionError("valid cached detail must avoid ns_place")

        @asynccontextmanager
        async def fake_session(source, **kwargs):
            yield FakeClient()
        with patch("leads.sources.source_session", fake_session):
            self.assertEqual(execute_source("neshan", self.job, execution), 1)
        lead = self.job.leads.get()
        self.assertEqual(lead.phone_numbers, ["02112345678"])
        self.assertEqual(lead.website, "https://business.example.ir")
        self.assertEqual(execution.request_count, 1)

    def test_detail_rate_limit_is_reported_and_further_detail_calls_stop(self):
        self.job.trade_name = "کافه"
        self.job.selected_sources = ["neshan"]
        self.job.max_results = 2
        self.job.save(update_fields=["trade_name", "selected_sources", "max_results"])
        execution = SourceExecution.objects.create(search_job=self.job, source_name="neshan")

        class FakeClient:
            request_count = 0
            calls = []

            async def call(self, tool_name, arguments):
                self.request_count += 1
                self.calls.append(tool_name)
                if tool_name == "ns_search":
                    return MCPCallResult({"results": [
                        {"id": "a" * 32, "name": "کافه اول", "phone": "02112345678", "address": "تهران ۱"},
                        {"id": "b" * 32, "name": "کافه دوم", "phone": "02112345679", "address": "تهران ۲"},
                    ]}, 1)
                raise MCPSourceError("neshan rate limiting requests (HTTP 429)")

        client = FakeClient()

        @asynccontextmanager
        async def fake_session(source, **kwargs):
            yield client

        with patch("leads.sources.source_session", fake_session):
            count = execute_source("neshan", self.job, execution)
        execution.refresh_from_db()
        self.assertEqual(count, 2)
        self.assertEqual(client.calls, ["ns_search", "ns_place"])
        self.assertEqual(execution.status, SourceExecution.Status.PARTIAL)
        self.assertEqual(execution.error_count, 1)
        self.assertIn("429", execution.error_details)
        self.assertEqual(self.job.leads.count(), 2)
        cooldown = SourceRateLimit.objects.get(source_name="neshan")
        self.assertGreater(cooldown.cooldown_until, timezone.now())

        next_job = SearchJob.objects.create(owner=self.user, trade_name="کافه", geographic_scope_type="city", geographic_scope_name="تهران", selected_sources=["neshan"])
        next_execution = SourceExecution.objects.create(search_job=next_job, source_name="neshan")
        with patch("leads.sources.source_session", side_effect=AssertionError("cooldown must skip startup")):
            self.assertEqual(execute_source("neshan", next_job, next_execution), 0)
        next_execution.refresh_from_db()
        self.assertEqual(next_execution.status, SourceExecution.Status.SKIPPED)

    def test_balad_category_search_uses_nearby_and_saves_place_details(self):
        self.job.trade_name = "شیشه فروشی های"
        self.job.selected_sources = ["balad"]
        self.job.max_results = 2
        self.job.save(update_fields=["trade_name", "selected_sources", "max_results"])
        execution = SourceExecution.objects.create(search_job=self.job, source_name="balad")
        record = {"id": "AbCdEf123456", "name": "شیشه فروشی نمونه", "phone": "03112345678", "address": "اصفهان، خیابان نمونه"}

        class FakeClient:
            request_count = 0
            calls = []

            async def call(self, tool_name, arguments):
                self.request_count += 1
                self.calls.append((tool_name, arguments))
                if tool_name == "bl_nearby":
                    return MCPCallResult({"places": [record]}, 1)
                return MCPCallResult({**record, "phones": [record["phone"]]}, 1)

        client = FakeClient()

        @asynccontextmanager
        async def fake_session(source, **kwargs):
            yield client

        with patch("leads.sources.source_session", fake_session):
            count = execute_source("balad", self.job, execution)
        execution.refresh_from_db()
        self.assertEqual(count, 1)
        self.assertEqual(execution.status, SourceExecution.Status.COMPLETED)
        self.assertEqual([call[0] for call in client.calls], ["bl_nearby", "bl_place", "bl_nearby", "bl_nearby"])
        self.assertEqual(client.calls[0][1]["what"], "شیشه فروشی")
        self.assertEqual(client.calls[0][1]["radius_km"], 20)
        self.assertEqual(client.calls[2][1]["what"], "فروشگاه شیشه")
        self.assertEqual(self.job.leads.get().source_record_ids["balad"], record["id"])
        self.assertIn("شیشه فروشی", execution.query_variants)
        self.assertEqual(execution.areas_checked, ["تهران"])

    def test_emalls_product_offers_pipeline_saves_public_shop_profile_with_evidence(self):
        self.job.trade_name = "فروشگاه اینترنتی لوازم خانگی"
        self.job.selected_sources = ["emalls"]
        self.job.max_results = 1
        self.job.save(update_fields=["trade_name", "selected_sources", "max_results"])
        execution = SourceExecution.objects.create(search_job=self.job, source_name="emalls")

        def tool(properties, required):
            return SimpleNamespace(input_schema={"type": "object", "properties": {key: {} for key in properties}, "required": required})

        class FakeClient:
            request_count = 0
            tools = {
                "em_search": tool(["query", "page", "page_size"], ["query"]),
                "em_offers": tool(["product_id", "city"], ["product_id"]),
                "em_shops": tool(["query"], ["query"]),
                "em_shop": tool(["shop_id"], ["shop_id"]),
            }
            calls = []

            async def call(self, name, arguments):
                self.request_count += 1
                self.calls.append((name, arguments))
                data = {
                    "em_search": {"products": [{"id": "product-1", "name": "یخچال نمونه"}]},
                    "em_offers": {"offers": [{"shop_id": "shop-1", "shop_name": "فروشگاه نمونه"}]},
                    "em_shop": {"shop_id": "shop-1", "name": "فروشگاه نمونه", "phone": "02112345678", "email": "info@example.ir", "website": "https://example.ir", "address": "تهران"},
                }[name]
                return MCPCallResult(data, 1)

        client = FakeClient()
        @asynccontextmanager
        async def fake_session(source, **kwargs):
            yield client

        with patch("leads.sources.source_session", fake_session):
            count = execute_source("emalls", self.job, execution)
        execution.refresh_from_db()
        lead = self.job.leads.get()
        self.assertEqual(count, 1)
        self.assertEqual(execution.status, SourceExecution.Status.COMPLETED)
        self.assertEqual([name for name, _ in client.calls], ["em_search", "em_offers", "em_shop"])
        self.assertEqual(lead.original_name, "فروشگاه نمونه")
        self.assertEqual(lead.phone_numbers, ["02112345678"])
        self.assertEqual(lead.emails, ["info@example.ir"])
        self.assertTrue(lead.evidence.filter(field_name="emails", source_name="emalls").exists())

    def test_basalam_product_is_saved_as_its_public_vendor_not_as_a_product(self):
        self.job.trade_name = "فروشگاه اینترنتی عسل"
        self.job.selected_sources = ["basalam"]
        self.job.max_results = 1
        self.job.save(update_fields=["trade_name", "selected_sources", "max_results"])
        execution = SourceExecution.objects.create(search_job=self.job, source_name="basalam")

        class FakeClient:
            request_count = 0
            tools = {
                "bs_search": SimpleNamespace(input_schema={"type": "object", "properties": {"query": {"type": "string"}, "page": {"type": "integer"}, "limit": {"type": "integer"}}, "required": ["query"]}),
                "bs_vendor": SimpleNamespace(input_schema={"type": "object", "properties": {"vendor": {"type": "string"}}, "required": ["vendor"]}),
            }
            calls = []

            async def call(self, name, arguments):
                self.request_count += 1
                self.calls.append((name, arguments))
                if name == "bs_search":
                    return MCPCallResult({"products": [{"id": "product-1", "shop_id": "shop-1", "name": "عسل طبیعی"}]}, 1)
                return MCPCallResult({"vendor": "shop-1", "name": "غرفه عسل نمونه", "city": "تهران", "activity": "عسل"}, 1)

        client = FakeClient()
        @asynccontextmanager
        async def fake_session(source, **kwargs):
            yield client
        with patch("leads.sources.source_session", fake_session):
            count = execute_source("basalam", self.job, execution)
        lead = self.job.leads.get()
        self.assertEqual(count, 1)
        self.assertEqual(lead.original_name, "غرفه عسل نمونه")
        self.assertEqual(lead.city, "تهران")
        self.assertEqual(lead.business_type, "marketplace_seller")
        self.assertEqual(lead.phone_numbers, [])
        self.assertEqual(lead.phone_status, BusinessLead.PhoneStatus.NOT_PROVIDED)
        self.assertEqual([name for name, _ in client.calls], ["bs_search", "bs_vendor"])

    def test_conflicting_source_values_are_preserved_as_evidence(self):
        search = {"id": "a" * 32, "name": "کافه آفتاب", "phone": "09123456789", "address": "خیابان ولیعصر، پلاک ۱"}
        lead = save_lead(self.job, "neshan", search, {"name": search["name"], "phones": [search["phone"]], "address": search["address"], "website": "https://first.example"})
        save_lead(self.job, "neshan", search, {"name": search["name"], "phones": ["02112345678"], "address": search["address"], "website": "https://second.example"})
        lead.refresh_from_db()
        self.assertEqual(lead.website, "https://first.example")
        self.assertEqual(lead.verification_status, BusinessLead.Verification.CONFLICTING)
        self.assertGreaterEqual(lead.evidence.filter(field_name="website").count(), 2)

    def test_blank_phone_values_are_not_saved_as_contact_numbers(self):
        record = {"id": "a" * 32, "name": "کافه نمونه", "phone": "", "address": "تهران"}
        lead = save_lead(self.job, "neshan", record, {"phones": ["", "  ", "02112345678"]})
        self.assertEqual(lead.phone_numbers, ["02112345678"])
        phone_evidence = lead.evidence.get(field_name="phone_numbers")
        self.assertEqual(json.loads(phone_evidence.normalized_value), ["02112345678"])
        self.assertEqual(phone_evidence.validation_status, "format_valid_unverified")

    def test_invalid_phone_is_not_promoted_to_public_contact(self):
        record = {"id": "c" * 32, "name": "کسب‌وکار نمونه", "phone": "12345"}
        lead = save_lead(self.job, "neshan", record, {})
        evidence = lead.evidence.get(field_name="phone_numbers")
        self.assertEqual(lead.phone_numbers, [])
        self.assertEqual(lead.phone_status, BusinessLead.PhoneStatus.INVALID)
        self.assertEqual(evidence.validation_status, "contains_invalid_format")

    def test_registry_lead_keeps_company_id_without_personal_fields_or_guessed_phone(self):
        row = {"company_id": "10100360794", "name": "شرکت نمونه", "activity": "نرم‌افزار", "ceo": "شخص حقیقی"}
        lead = save_lead(self.job, "rasmio", row, {})
        self.assertEqual(lead.national_id, "10100360794")
        self.assertEqual(lead.business_type, "registered_company")
        self.assertEqual(lead.phone_status, BusinessLead.PhoneStatus.NOT_PROVIDED)
        self.assertEqual(lead.phone_numbers, [])
        raw = lead.evidence.get(field_name="raw_response").raw_response
        self.assertNotIn("ceo", json.dumps(raw, ensure_ascii=False))

    def test_source_call_budget_marks_incomplete_coverage_as_truncated(self):
        self.job.trade_name = "کافه"
        self.job.selected_sources = ["neshan"]
        self.job.max_results = 2
        self.job.save(update_fields=["trade_name", "selected_sources", "max_results"])
        execution = SourceExecution.objects.create(search_job=self.job, source_name="neshan")

        class FakeClient:
            request_count = 0
            async def call(self, tool_name, arguments):
                self.request_count += 1
                if tool_name == "ns_search":
                    return MCPCallResult({"results": [{"id": "a" * 32, "name": "کافه الف", "phone": "02112345678", "address": "تهران"}]}, 1)
                return MCPCallResult({"id": arguments["place_id"], "name": "کافه الف", "phone": "02112345678", "address": "تهران"}, 1)

        @asynccontextmanager
        async def fake_session(source, **kwargs):
            yield FakeClient()
        with patch("leads.sources.source_session", fake_session), patch("leads.sources.settings.MAX_MCP_CALLS_PER_JOB", 1):
            execute_source("neshan", self.job, execution)
        execution.refresh_from_db()
        self.assertEqual(execution.status, SourceExecution.Status.PARTIAL)
        self.assertTrue(execution.truncated)


class MCPClientTests(TestCase):
    def test_neshan_place_details_are_spaced(self):
        tool = SimpleNamespace(input_schema={"type": "object", "properties": {"place_id": {"type": "string"}}, "required": ["place_id"]})
        session = SimpleNamespace(call_tool=AsyncMock(return_value=SimpleNamespace(isError=False, structuredContent={"id": "place-1"})))
        client = MCPToolClient("neshan", session, {"ns_place": tool})
        with patch("leads.mcp_client.asyncio.sleep", new_callable=AsyncMock) as sleep:
            asyncio.run(client.call("ns_place", {"place_id": "place-1"}))
        sleep.assert_awaited_once_with(6.0)

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
        snake_case_response = type("Response", (), {"is_error": True, "structured_content": None, "content": [TextContent(type="text", text="rate limited")]})()
        with self.assertRaisesRegex(MCPSourceError, "rate limited"):
            decode_result(snake_case_response)
        with self.assertRaises(MCPSourceError) as caught:
            decode_result(type("Response", (), {"is_error": True, "structured_content": None, "content": [TextContent(type="text", text="neshan.org rate limiting requests (HTTP 429). Wait a minute before retrying.")]})())
        self.assertTrue(caught.exception.rate_limited)
        self.assertEqual(caught.exception.retry_after_seconds, 60)
        with self.assertRaises(MCPSourceError) as caught_retry:
            decode_result(type("Response", (), {"is_error": True, "structured_content": None, "content": [TextContent(type="text", text="HTTP 429 Retry-After: 120")]})())
        self.assertEqual(caught_retry.exception.retry_after_seconds, 120)

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
        self.lead = BusinessLead.objects.create(search_job=self.job, normalized_name="کلینیک نمونه", original_name="کلینیک نمونه", phone_numbers=["09123456789"], emails=["public@example.ir"], phone_status=BusinessLead.PhoneStatus.FOUND_PUBLIC, confidence_score=0.8, address="تهران", city="تهران", website="https://example.com", source_names=["neshan"], source_record_ids={"neshan": "a" * 32})
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

    def test_sources_run_in_user_selected_order(self):
        self.job.selected_sources = ["balad", "neshan"]
        self.job.save(update_fields=["selected_sources"])
        seen = []
        def fake_execute(source, job, execution):
            seen.append(source)
            execution.status = SourceExecution.Status.COMPLETED
            execution.save(update_fields=["status"])
            return 0
        with patch("leads.tasks.execute_source", side_effect=fake_execute):
            run_search_job.apply(args=(self.job.pk,)).get()
        self.assertEqual(seen, ["balad", "neshan"])

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

    def test_old_queued_job_explains_that_a_celery_worker_is_required(self):
        self.client.force_login(self.user)
        self.job.created_at = timezone.now() - timedelta(minutes=2)
        self.job.save(update_fields=["created_at"])
        response = self.client.get(reverse("job_detail", args=[self.job.pk]))
        self.assertContains(response, "Celery worker")

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
        self.assertIn("ایمیل عمومی", [cell.value for cell in workbook["سرنخ‌ها"][1]])
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
        self.assertEqual(payload["results"][0]["emails"], ["public@example.ir"])
        self.assertEqual(payload["results"][0]["confidence_score"], 0.8)
        self.assertEqual(payload["results"][0]["evidence"][0]["source"], "neshan")
