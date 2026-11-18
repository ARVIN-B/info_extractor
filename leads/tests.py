import asyncio
import json
from contextlib import asynccontextmanager
from datetime import timedelta
from email.utils import format_datetime
from io import BytesIO, StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from mcp.types import TextContent
from openpyxl import load_workbook

from .adapters import DigikalaAdapter, IranJobsCompanyAdapter, QueraCompanyAdapter, RasmioAdapter, SnappShopAdapter, TorobShopAdapter, _arguments
from .mcp_client import MCPBudgetExhausted, MCPCallResult, MCPSourceError, MCPToolClient, SOURCE_REGISTRY, decode_result
from .forms import SearchJobForm
from .models import BusinessLead, LeadEvidence, QueryExpansionCache, SearchJob, SourceExecution, SourcePlaceDetailCache, SourceRateLimit, SourceToolCall
from .normalization import has_iranian_mobile, normalize_phone, normalize_text, normalize_website, phone_is_valid
from .query_expansion import category_for_query, expand_query
from .sources import _cached_source_detail, _catalog_page_fingerprint, _find_match, _is_repeated_catalog_page, _store_source_detail, calculate_source_budget, calculate_source_call_allowance, execute_source, get_scope_points, get_source_query_variants, get_trade_variants, is_relevant_trade_record, save_lead
from .tasks import recover_stale_search_jobs, run_search_job


class NormalizationTests(TestCase):
    def test_persian_characters_and_digits(self):
        self.assertEqual(normalize_text("كافه ياس ۱۲"), normalize_text("کافه یاس 12"))

    def test_iranian_phone_formats(self):
        self.assertEqual(normalize_phone("+98 912 345 6789"), "09123456789")
        self.assertEqual(normalize_phone("۰۹۱۲۳۴۵۶۷۸۹"), "09123456789")
        self.assertTrue(has_iranian_mobile(["02112345678", "+98 912 345 6789"]))
        self.assertTrue(has_iranian_mobile(["۰۹۱۲۳۴۵۶۷۸۹"]))
        self.assertFalse(has_iranian_mobile(["02112345678", "12345"]))
        self.assertTrue(has_iranian_mobile(["9123456789"]))
        self.assertTrue(has_iranian_mobile(["989123456789"]))
        self.assertFalse(has_iranian_mobile(["9"]))
        self.assertTrue(phone_is_valid("021-12345678"))
        self.assertFalse(phone_is_valid("12345"))

    def test_website_normalization(self):
        self.assertEqual(normalize_website("http://www.Example.com/")[1], "example.com")
        self.assertEqual(normalize_website("not a domain"), ("", ""))

    def test_result_budget_reserves_an_initial_share_for_each_source(self):
        self.assertEqual(calculate_source_budget(100, 2, 100, 0), 50)
        self.assertEqual(calculate_source_budget(100, 2, 50, 1), 50)
        self.assertEqual(calculate_source_budget(1, 2, 1, 0), 1)

    def test_global_mcp_call_budget_reserves_capacity_for_pending_sources(self):
        self.assertEqual(calculate_source_call_allowance(100, 40, 5, 0, 4), 20)
        self.assertEqual(calculate_source_call_allowance(100, 40, 5, 5, 3), 35)
        self.assertEqual(calculate_source_call_allowance(100, 40, 5, 80, 0), 20)
        self.assertEqual(calculate_source_call_allowance(100, 40, 2, 0, 1), 40)

    def test_repeated_catalog_page_is_detected_without_marking_same_page_resume(self):
        page = [({"_source_id": "shop-1", "name": "فروشگاه نمونه"}, {})]
        fingerprint = _catalog_page_fingerprint(page)
        history = [{"page": 1, "hash": fingerprint}]
        self.assertTrue(_is_repeated_catalog_page(fingerprint, history, current_page=2))
        self.assertFalse(_is_repeated_catalog_page(fingerprint, history, current_page=1))

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

    def test_catalog_sources_get_closest_source_specific_search_variants(self):
        self.assertIn("فروشگاه کافه", get_source_query_variants("کافه", "emalls"))
        self.assertIn("محصولات کافه", get_source_query_variants("کافه", "basalam"))
        self.assertIn("شرکت کافه", get_source_query_variants("کافه", "rasmio"))
        self.assertEqual(get_source_query_variants("کافه", "neshan"), ["کافه"])

    def test_category_name_search_expands_to_the_whole_known_category(self):
        result = expand_query("تکنولوژی")
        self.assertEqual(result["category"]["key"], "technology")
        variants = get_source_query_variants("تکنولوژی", "neshan", result)
        self.assertIn("فناوری اطلاعات", variants)
        self.assertIn("شرکت نرم افزاری", variants)
        self.assertEqual(variants[0], "تکنولوژی")

    def test_category_aliases_respect_persian_normalization(self):
        self.assertEqual(category_for_query("فناوري اطلاعات")["key"], "technology")

    def test_query_expansion_keeps_original_and_uses_deterministic_fallback(self):
        with self.settings(SEARCH_QUERY_LLM_ENABLED=False):
            result = expand_query("شیشه فروشی های")
        self.assertEqual(result["original_query"], "شیشه فروشی های")
        self.assertEqual(result["provider"], "deterministic")
        self.assertLessEqual(len(result["variants"]), settings.SEARCH_QUERY_MAX_VARIANTS)

    def test_llm_expansion_is_validated_and_cached(self):
        response = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"choices": [{"message": {"content": json.dumps({"variants": [
                {"query": "شرکت نرم افزاری", "type": "synonym", "relevance": 0.95},
                {"query": "رستوران", "type": "irrelevant", "relevance": 0.1},
                {"query": "شرکت نرم افزاری", "type": "duplicate", "relevance": 1.0},
            ]})}}]},
        )
        config = {
            "SEARCH_QUERY_LLM_ENABLED": True, "SEARCH_QUERY_LLM_BASE_URL": "https://llm.example/v1",
            "SEARCH_QUERY_LLM_API_KEY": "test-key", "SEARCH_QUERY_LLM_MODEL": "test-model",
            "SEARCH_QUERY_MIN_RELEVANCE": 0.7,
        }
        with self.settings(**config), patch("leads.query_expansion.httpx.post", return_value=response) as post:
            first = expand_query("شرکت‌های فناوری")
            second = expand_query("شرکت‌های فناوری")
        self.assertEqual(first, second)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(len(first["variants"]), 1)
        self.assertEqual(first["variants"][0]["query"], "شرکت نرم افزاری")
        self.assertEqual(QueryExpansionCache.objects.count(), 1)

    def test_llm_failure_falls_back_without_failing_search(self):
        with self.settings(
            SEARCH_QUERY_LLM_ENABLED=True, SEARCH_QUERY_LLM_BASE_URL="https://llm.example/v1",
            SEARCH_QUERY_LLM_API_KEY="test-key", SEARCH_QUERY_LLM_MODEL="test-model",
        ), patch("leads.query_expansion.httpx.post", side_effect=__import__("httpx").TimeoutException("timeout")):
            result = expand_query("شیشه فروشی های")
        self.assertFalse(result["success"])
        self.assertEqual(result["original_query"], "شیشه فروشی های")
        self.assertTrue(any(item["query"] == "شیشه فروشی" for item in result["variants"]))

    def test_form_accepts_5000_and_rejects_values_above_configured_limit(self):
        data = {"trade_name": "تکنولوژی", "geographic_scope_type": "city", "geographic_scope_name": "تهران", "sources": ["neshan"], "max_results": 5000}
        self.assertTrue(SearchJobForm(data=data).is_valid())
        data["max_results"] = 5001
        self.assertFalse(SearchJobForm(data=data).is_valid())

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
        with self.settings(SEARCH_PAGES_PER_BATCH=2):
            result = asyncio.run(run())
        rows = result.records
        self.assertEqual(len(rows), 21)
        self.assertEqual(rows[0][0]["national_id"], "10100360700")
        self.assertEqual(calls[0][0], "rs_search_companies")
        self.assertEqual([call[1]["page"] for call in calls], [1, 2])

    def test_rasmio_adapter_returns_a_page_checkpoint_and_resumes_from_it(self):
        class FakeClient:
            tools = {"rs_search_companies": SimpleNamespace(input_schema={"type": "object", "properties": {"query": {"type": "string"}, "page": {"type": "integer"}, "page_size": {"type": "integer"}}, "required": ["query"]})}
        called_pages = []
        async def invoke(client, name, arguments):
            called_pages.append(arguments["page"])
            rows = [{"company_id": str(index), "name": f"شرکت {index}"} for index in range(20)] if arguments["page"] == 1 else [{"company_id": "last", "name": "شرکت آخر"}]
            return MCPCallResult({"companies": rows}, 1)
        async def run(start_page):
            return await RasmioAdapter().discover(FakeClient(), invoke, "شرکت", "", "", 40, start_page=start_page)
        with self.settings(SEARCH_PAGES_PER_BATCH=1):
            first = asyncio.run(run(1))
            second = asyncio.run(run(first.next_page))
        self.assertEqual(first.next_page, 2)
        self.assertEqual(len(first.records), 20)
        self.assertIsNone(second.next_page)
        self.assertEqual(called_pages, [1, 2])

    def test_new_source_adapters_convert_company_or_seller_records(self):
        class FakeClient:
            tools = {
                "tb_find_shops": SimpleNamespace(input_schema={"type": "object", "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 80}, "city": {"anyOf": [{"type": "string", "minLength": 1, "maxLength": 40}, {"type": "null"}]}, "kind": {"type": "string", "enum": ["all", "online", "offline"]}, "page": {"type": "integer", "minimum": 0, "maximum": 50}, "limit": {"type": "integer", "minimum": 1, "maximum": 30}}, "required": ["query"]}),
                "job_companies": SimpleNamespace(input_schema={"type": "object", "properties": {"name": {"anyOf": [{"type": "string", "maxLength": 60}, {"type": "null"}]}, "site": {"type": "string", "enum": ["all", "irantalent", "jobinja", "jobvision"]}, "page": {"type": "integer", "minimum": 1, "maximum": 500}}}),
                "qr_companies": SimpleNamespace(input_schema={"type": "object", "properties": {"search": {"type": ["string", "null"]}, "city": {"type": ["string", "null"]}, "page": {"type": "integer"}}}),
                "qr_company": SimpleNamespace(input_schema={"type": "object", "properties": {"slug": {"type": "string"}}, "required": ["slug"]}),
                "dk_search": SimpleNamespace(input_schema={"type": "object", "properties": {"query": {"type": "string"}, "page": {"type": "integer"}}, "required": ["query"]}),
                "dk_product": SimpleNamespace(input_schema={"type": "object", "properties": {"product_id": {"type": "integer"}, "max_offers": {"type": "integer"}}, "required": ["product_id"]}),
                "ss_search": SimpleNamespace(input_schema={"type": "object", "properties": {"query": {"type": "string"}, "page": {"type": "integer"}}, "required": ["query"]}),
                "ss_product": SimpleNamespace(input_schema={"type": "object", "properties": {"product": {"type": "string"}}, "required": ["product"]}),
            }

        calls = []

        async def run_adapter(adapter, source):
            async def invoke(client, tool, args):
                calls.append((source, tool, args))
                if source == "torob":
                    return MCPCallResult({"shops": [{"shop_id": 42, "name": "فروشگاه نمونه"}]}, 1)
                if source == "iran_jobs":
                    return MCPCallResult({"companies": [{"company_id": "uuid-1", "name": "شرکت نمونه", "industry": "فناوری"}]}, 1)
                if source == "quera" and tool == "qr_companies":
                    return MCPCallResult({"companies": [{"slug": "sample", "name": "شرکت فنی"}]}, 1)
                if source == "quera":
                    return MCPCallResult({"name": "شرکت فنی", "website": "https://example.com", "contacts": ["public@example.com"]}, 1)
                if tool in {"dk_search", "ss_search"}:
                    product = {"id": "abcdef", "product_id": 123} if source == "snappshop" else {"id": 123}
                    return MCPCallResult({"products": [product]}, 1)
                if source == "snappshop":
                    self.assertEqual(args["product"], "123")
                return MCPCallResult({"product": {"offers": [{"seller_id": "seller-1", "seller_name": "فروشنده نمونه", "website": "https://shop.example"}]}}, 1)
            return await adapter.discover(FakeClient(), invoke, "فروشگاه نمونه", "اصفهان", "اصفهان", 10)

        torob = asyncio.run(run_adapter(TorobShopAdapter(), "torob"))
        jobs = asyncio.run(run_adapter(IranJobsCompanyAdapter(), "iran_jobs"))
        quera = asyncio.run(run_adapter(QueraCompanyAdapter(), "quera"))
        digikala = asyncio.run(run_adapter(DigikalaAdapter(), "digikala"))
        snappshop = asyncio.run(run_adapter(SnappShopAdapter(), "snappshop"))
        self.assertEqual(torob.records[0][0]["_source_id"], "42")
        self.assertEqual(jobs.records[0][0]["_source_id"], "uuid-1")
        self.assertEqual(quera.records[0][0]["_source_id"], "sample")
        self.assertEqual(quera.records[0][0]["website"], "https://example.com")
        self.assertEqual(digikala.records[0][0]["_source_id"], "seller-1")
        self.assertEqual(snappshop.records[0][0]["name"], "فروشنده نمونه")
        torob_args = next(args for source, tool, args in calls if source == "torob" and tool == "tb_find_shops")
        jobs_args = next(args for source, tool, args in calls if source == "iran_jobs" and tool == "job_companies")
        self.assertEqual(torob_args, {"query": "فروشگاه نمونه", "city": "اصفهان", "kind": "all", "page": 0, "limit": 10})
        self.assertEqual(jobs_args, {"name": "فروشگاه نمونه", "site": "all", "page": 1})

    def test_rate_limit_retry_after_supports_seconds_dates_and_day_cooldowns(self):
        with self.assertRaises(MCPSourceError) as seconds:
            decode_result(type("Response", (), {"is_error": True, "content": [TextContent(type="text", text="HTTP 429 Retry-After: 7200")]})())
        self.assertEqual(seconds.exception.retry_after_seconds, 7200)
        retry_date = format_datetime(timezone.now() + timedelta(hours=3), usegmt=True)
        with self.assertRaises(MCPSourceError) as date_result:
            decode_result(type("Response", (), {"is_error": True, "content": [TextContent(type="text", text=f"429 Retry-After: {retry_date}")]})())
        self.assertGreater(date_result.exception.retry_after_seconds, 7000)
        self.assertEqual(MCPSourceError("rate limited; wait 1 day").retry_after_seconds, 86400)
        self.assertEqual(MCPSourceError("daily quota exceeded").error_type, "daily_quota_exceeded")


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
        self.assertEqual(LeadEvidence.objects.filter(business_lead__search_job=self.job, field_name="raw_response").count(), 1)

    def test_mobile_discovery_promotes_existing_candidate_to_one_success(self):
        record = {"id": "b" * 32, "name": "مغازه نمونه", "phone": "02112345678", "address": "تهران"}
        lead, successful = save_lead(self.job, "neshan", record, {}, return_created=True)
        self.assertFalse(successful)
        self.assertFalse(lead.has_mobile_phone)

        record["phone"] = "+98 912 345 6789"
        promoted, successful = save_lead(self.job, "balad", record, {}, return_created=True)
        self.assertEqual(promoted.pk, lead.pk)
        self.assertTrue(successful)
        self.assertTrue(promoted.has_mobile_phone)
        self.assertEqual(promoted.phone_numbers, ["02112345678", "09123456789"])

        _, successful_again = save_lead(self.job, "balad", record, {}, return_created=True)
        self.assertFalse(successful_again)

    def test_dedup_uses_narrow_indexed_name_lookup_for_large_jobs(self):
        BusinessLead.objects.bulk_create([
            BusinessLead(search_job=self.job, normalized_name=f"نام {index}", original_name=f"نام {index}")
            for index in range(300)
        ])
        target = BusinessLead.objects.create(search_job=self.job, normalized_name="فروشگاه هدف", original_name="فروشگاه هدف", city="تهران", phone_numbers=["09123456789"])
        data = {"phones": ["09123456789"], "name": "فروشگاه هدف", "address": "", "national_id": "", "website": "", "city": "تهران"}
        with CaptureQueriesContext(connection) as captured:
            matched = _find_match(self.job, "neshan", "absent-id", data)
        lead_queries = [query for query in captured.captured_queries if "FROM \"leads_businesslead\"" in query["sql"]]
        self.assertEqual(matched.pk, target.pk)
        self.assertEqual(len(lead_queries), 2)
        self.assertIn("normalized_name", lead_queries[-1]["sql"])

    def test_internal_fair_share_exhaustion_is_a_non_error_terminal_source_state(self):
        self.job.selected_sources = ["neshan"]
        self.job.save(update_fields=["selected_sources"])
        SourceExecution.objects.filter(search_job=self.job).exclude(source_name="neshan").delete()
        execution = SourceExecution.objects.create(search_job=self.job, source_name="neshan")
        class BudgetClient:
            request_count = 1
            async def call(self, tool_name, arguments):
                raise MCPBudgetExhausted("reserved capacity")
        @asynccontextmanager
        async def fake_session(source, **kwargs):
            yield BudgetClient()
        with patch("leads.sources.source_session", fake_session), self.settings(MAX_MCP_CALLS_PER_JOB=1, SOURCE_MAX_CALLS_PER_JOB=10):
            self.assertEqual(execute_source("neshan", self.job, execution), 0)
        execution.refresh_from_db()
        self.assertEqual(execution.status, SourceExecution.Status.BUDGET_EXHAUSTED)
        self.assertEqual(execution.error_type, "fair_share_exhausted")
        self.assertEqual(execution.error_count, 0)

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
        self.assertEqual(count, 0)
        self.assertEqual(self.job.leads.count(), 2)
        self.assertEqual(execution.status, SourceExecution.Status.QUEUED)
        self.assertEqual(execution.error_count, 1)
        self.assertIn("detail endpoint unavailable", execution.error_details)
        self.assertEqual(SourceToolCall.objects.filter(source_execution=execution, error_summary__gt="").count(), 1)

    def test_neshan_missing_place_details_uses_search_data_and_caches_the_miss(self):
        self.job.trade_name = "کافه"
        self.job.selected_sources = ["neshan"]
        self.job.max_results = 1
        self.job.save(update_fields=["trade_name", "selected_sources", "max_results"])
        execution = SourceExecution.objects.create(search_job=self.job, source_name="neshan")
        identifier = "e" * 32

        class FakeClient:
            request_count = 0

            async def call(self, tool_name, arguments):
                self.request_count += 1
                if tool_name == "ns_search":
                    return MCPCallResult({"results": [{"id": identifier, "name": "کافه نمونه", "phone": "09123456789", "address": "تهران"}]}, 1)
                raise MCPSourceError("Neshan returned no details for this place. Check the id; get ids from ns_search.")

        @asynccontextmanager
        async def fake_session(source, **kwargs):
            yield FakeClient()

        with patch("leads.sources.source_session", fake_session):
            self.assertEqual(execute_source("neshan", self.job, execution), 1)
        execution.refresh_from_db()
        lead = self.job.leads.get()
        self.assertEqual(lead.phone_numbers, ["09123456789"])
        self.assertEqual(execution.status, SourceExecution.Status.QUEUED)
        self.assertEqual(execution.error_count, 0)
        self.assertIn("جزئیات نشان موجود نبود", execution.error_details)
        self.assertEqual(_cached_source_detail("neshan", identifier), {})

    def test_cached_place_detail_avoids_another_upstream_detail_call(self):
        self.job.trade_name = "کافه"
        self.job.selected_sources = ["neshan"]
        self.job.max_results = 1
        self.job.save(update_fields=["trade_name", "selected_sources", "max_results"])
        execution = SourceExecution.objects.create(search_job=self.job, source_name="neshan")
        identifier = "d" * 32
        _store_source_detail("neshan", identifier, {"name": "کافه نمونه", "phone": "09123456789", "website": "https://business.example.ir"})

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
        self.assertEqual(lead.phone_numbers, ["09123456789"])
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
                        {"id": "a" * 32, "name": "کافه اول", "phone": "09123456781", "address": "تهران ۱"},
                        {"id": "b" * 32, "name": "کافه دوم", "phone": "09123456782", "address": "تهران ۲"},
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
        self.assertEqual(execution.status, SourceExecution.Status.RATE_LIMITED)
        self.assertEqual(execution.error_count, 0)
        self.assertIn("429", execution.error_details)
        self.assertEqual(self.job.leads.count(), 2)
        cooldown = SourceRateLimit.objects.get(source_name="neshan")
        self.assertGreater(cooldown.cooldown_until, timezone.now())

        next_job = SearchJob.objects.create(owner=self.user, trade_name="کافه", geographic_scope_type="city", geographic_scope_name="تهران", selected_sources=["neshan"])
        next_execution = SourceExecution.objects.create(search_job=next_job, source_name="neshan")
        with patch("leads.sources.source_session", side_effect=AssertionError("cooldown must skip startup")):
            self.assertEqual(execute_source("neshan", next_job, next_execution), 0)
        next_execution.refresh_from_db()
        self.assertEqual(next_execution.status, SourceExecution.Status.RATE_LIMITED)

    def test_balad_category_search_uses_nearby_and_saves_place_details(self):
        self.job.trade_name = "شیشه فروشی های"
        self.job.selected_sources = ["balad"]
        self.job.max_results = 2
        self.job.save(update_fields=["trade_name", "selected_sources", "max_results"])
        execution = SourceExecution.objects.create(search_job=self.job, source_name="balad")
        record = {"id": "AbCdEf123456", "name": "شیشه فروشی نمونه", "phone": "09123456783", "address": "اصفهان، خیابان نمونه"}

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
        self.assertEqual(execution.status, SourceExecution.Status.QUEUED)
        self.assertEqual([call[0] for call in client.calls], ["bl_nearby", "bl_place"])
        self.assertEqual(client.calls[0][1]["what"], "شیشه فروشی های")
        self.assertEqual(client.calls[0][1]["radius_km"], 20)
        self.assertEqual(self.job.leads.get().source_record_ids["balad"], record["id"])
        self.assertEqual(execution.query_variants, ["شیشه فروشی های"])
        self.assertEqual(execution.checkpoint["variant_index"], 1)
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
                    "em_shop": {"shop_id": "shop-1", "name": "فروشگاه نمونه", "phone": "09123456784", "email": "info@example.ir", "website": "https://example.ir", "address": "تهران"},
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
        self.assertEqual(execution.status, SourceExecution.Status.QUEUED)
        self.assertEqual([name for name, _ in client.calls], ["em_search", "em_offers", "em_shop"])
        self.assertEqual(lead.original_name, "فروشگاه نمونه")
        self.assertEqual(lead.phone_numbers, ["09123456784"])
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
        self.assertEqual(count, 0)
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
        self.assertEqual(execution.status, SourceExecution.Status.BUDGET_EXHAUSTED)
        self.assertEqual(execution.error_count, 0)
        self.assertTrue(execution.truncated)


class MCPClientTests(TestCase):
    def test_neshan_place_details_are_spaced(self):
        tool = SimpleNamespace(input_schema={"type": "object", "properties": {"place_id": {"type": "string"}}, "required": ["place_id"]})
        session = SimpleNamespace(call_tool=AsyncMock(return_value=SimpleNamespace(isError=False, structuredContent={"id": "place-1"})))
        client = MCPToolClient("neshan", session, {"ns_place": tool})
        with patch("leads.mcp_client.asyncio.sleep", new_callable=AsyncMock) as sleep:
            asyncio.run(client.call("ns_place", {"place_id": "place-1"}))
        sleep.assert_awaited_once_with(6.0)

    def test_balad_place_details_are_spaced(self):
        tool = SimpleNamespace(input_schema={"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]})
        session = SimpleNamespace(call_tool=AsyncMock(return_value=SimpleNamespace(isError=False, structuredContent={"id": "place-1"})))
        client = MCPToolClient("balad", session, {"bl_place": tool})
        with patch("leads.mcp_client.asyncio.sleep", new_callable=AsyncMock) as sleep:
            asyncio.run(client.call("bl_place", {"id": "place-1"}))
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


class CheckMCPCommandTests(TestCase):
    def test_mcp_package_versions_match_registry_and_requirements(self):
        requirements = (Path(settings.BASE_DIR) / "requirements.txt").read_text(encoding="utf-8")
        expected = {
            "torob": "torob-mcp==0.2.2",
            "iran_jobs": "iran-jobs-mcp==0.2.1",
            "digikala": "digikala-mcp==0.6.2",
            "snappshop": "snappshop-mcp==0.2.1",
        }
        for source, package in expected.items():
            with self.subTest(source=source):
                self.assertEqual(SOURCE_REGISTRY[source]["package"], package)
                self.assertIn(package, requirements)
                self.assertEqual(SOURCE_REGISTRY[source]["license"], "PolyForm-Noncommercial-1.0.0")

    def test_torob_health_check_uses_search_adapter_without_detail_tool(self):
        class FakeClient:
            tools = {
                "tb_find_shops": SimpleNamespace(input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "city": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                        "kind": {"type": "string", "enum": ["all", "online", "offline"]},
                        "page": {"type": "integer"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["query"],
                })
            }

            def __init__(self):
                self.calls = []

            async def call(self, tool, arguments):
                self.calls.append((tool, arguments))
                return MCPCallResult({"shops": [{"shop_id": "t-1", "name": "فروشگاه نمونه"}]}, 1)

        client = FakeClient()

        @asynccontextmanager
        async def fake_session(source):
            self.assertEqual(source, "torob")
            yield client

        output = StringIO()
        with patch("leads.management.commands.check_mcp.source_session", fake_session):
            call_command("check_mcp", source="torob", query="فروشگاه نمونه", city="شهر فرضی", stdout=output)
        self.assertIn("torob: connected; tools=tb_find_shops; results=1; details=not available", output.getvalue())
        self.assertEqual(client.calls, [("tb_find_shops", {
            "query": "فروشگاه نمونه", "city": "شهر فرضی", "kind": "all", "page": 0, "limit": 1,
        })])

    def test_iran_jobs_health_check_uses_name_schema_and_reports_no_detail_tool(self):
        class FakeClient:
            tools = {
                "job_companies": SimpleNamespace(input_schema={
                    "type": "object",
                    "properties": {
                        "name": {"anyOf": [{"type": "string", "maxLength": 60}, {"type": "null"}]},
                        "site": {"type": "string", "enum": ["all", "irantalent", "jobinja", "jobvision"]},
                        "page": {"type": "integer", "minimum": 1, "maximum": 500},
                    },
                })
            }

            def __init__(self):
                self.calls = []

            async def call(self, tool, arguments):
                self.calls.append((tool, arguments))
                return MCPCallResult({"companies": [{"company_id": "co-1", "name": "شرکت نمونه"}]}, 1)

        client = FakeClient()

        @asynccontextmanager
        async def fake_session(source):
            self.assertEqual(source, "iran_jobs")
            yield client

        output = StringIO()
        with patch("leads.management.commands.check_mcp.source_session", fake_session):
            call_command("check_mcp", source="iran_jobs", query="شرکت نمونه", city="تهران", stdout=output)
        self.assertIn("iran_jobs: connected; tools=job_companies; results=1; details=not available", output.getvalue())
        self.assertEqual(client.calls, [("job_companies", {"name": "شرکت نمونه", "site": "all", "page": 1})])

    def test_health_check_reports_detail_success_for_a_source_that_has_a_detail_tool(self):
        class FakeClient:
            tools = {
                "em_search": SimpleNamespace(input_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}),
                "em_offers": SimpleNamespace(input_schema={"type": "object", "properties": {"product_id": {"type": "string"}, "city": {"type": "string"}}}),
                "em_shop": SimpleNamespace(input_schema={"type": "object", "properties": {"shop_id": {"type": "string"}}, "required": ["shop_id"]}),
            }

            async def call(self, tool, arguments):
                if tool == "em_search":
                    return MCPCallResult({"products": [{"id": "p-1"}]}, 1)
                if tool == "em_offers":
                    return MCPCallResult({"offers": [{"shop_id": "s-1"}]}, 1)
                return MCPCallResult({"shop": {"name": "فروشگاه نمونه"}}, 1)

        @asynccontextmanager
        async def fake_session(source):
            self.assertEqual(source, "emalls")
            yield FakeClient()

        output = StringIO()
        with patch("leads.management.commands.check_mcp.source_session", fake_session):
            call_command("check_mcp", source="emalls", query="محصول نمونه", city="تهران", stdout=output)
        self.assertIn("emalls: connected;", output.getvalue())
        self.assertIn("details=ok", output.getvalue())

    def test_all_sources_continue_after_one_failure_and_exit_nonzero(self):
        seen = []

        async def fake_probe(command, source, query, city, point):
            seen.append(source)
            if source == "torob":
                raise MCPSourceError("upstream unavailable")
            return ["job_companies"], 1, "not available"

        stdout, stderr = StringIO(), StringIO()
        with self.settings(ENABLED_MCP_SOURCES=["torob", "iran_jobs"]):
            with patch("leads.management.commands.check_mcp.Command._probe", new=fake_probe):
                with self.assertRaises(CommandError) as raised:
                    call_command("check_mcp", source="all", stdout=stdout, stderr=stderr)
        self.assertEqual(seen, ["torob", "iran_jobs"])
        self.assertIn("iran_jobs: connected", stdout.getvalue())
        self.assertIn("torob: live check failed (MCPSourceError: upstream unavailable)", stderr.getvalue())
        self.assertIn("torob", str(raised.exception))


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

    def test_job_totals_count_only_mobile_qualified_businesses(self):
        BusinessLead.objects.create(
            search_job=self.job, normalized_name="شماره ثابت", original_name="شماره ثابت",
            phone_numbers=["02112345678"],
        )
        self.job.total_unique_businesses = 99
        self.job.save(update_fields=["total_unique_businesses"])

        def complete_source(source, job, execution):
            execution.status = SourceExecution.Status.COMPLETED
            execution.save(update_fields=["status"])
            return 0

        with patch("leads.tasks.execute_source", side_effect=complete_source):
            result = run_search_job.apply(args=(self.job.pk,)).get()
        self.job.refresh_from_db()
        self.assertEqual(result["leads"], 1)
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

    def test_rate_limited_source_uses_enabled_relevant_fallback_and_job_completes(self):
        self.job.selected_sources = ["emalls"]
        self.job.save(update_fields=["selected_sources"])
        SourceExecution.objects.filter(search_job=self.job).exclude(source_name="emalls").delete()
        SourceExecution.objects.create(search_job=self.job, source_name="emalls")

        def fake_execute(source, job, execution):
            if source == "emalls":
                execution.status = SourceExecution.Status.RATE_LIMITED
                execution.error_type = "rate_limit"
            else:
                execution.status = SourceExecution.Status.COMPLETED
                execution.result_count = 1
            execution.save(update_fields=["status", "error_type", "result_count"])
            return 0

        with patch("leads.tasks.execute_source", side_effect=fake_execute), self.settings(
            ENABLED_MCP_SOURCES=["emalls", "torob"], SOURCE_FALLBACK_ENABLED=True,
        ):
            result = run_search_job.apply(args=(self.job.pk,)).get()
        self.job.refresh_from_db()
        self.assertEqual(result["status"], SearchJob.Status.COMPLETED)
        torob = self.job.source_executions.get(source_name="torob")
        self.assertEqual(torob.fallback_source, "emalls")
        self.assertEqual(self.job.source_executions.get(source_name="emalls").fallback_source, "torob")

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
            enqueue.return_value.id = "celery-task-123"
            response = self.client.post(reverse("search"), {
                "trade_name": "طلافروشی", "geographic_scope_type": "city", "geographic_scope_name": "تهران",
                "sources": ["neshan", "balad"], "max_results": 20,
            })
        self.assertEqual(response.status_code, 302)
        created = SearchJob.objects.exclude(pk=self.job.pk).get()
        enqueue.assert_called_once_with(created.pk)
        self.assertEqual(created.status, SearchJob.Status.QUEUED)
        self.assertEqual(created.celery_task_id, "celery-task-123")
        self.assertEqual(created.source_executions.count(), 2)

    def test_cancel_job_records_status_and_revokes_its_celery_task(self):
        self.client.force_login(self.user)
        self.job.celery_task_id = "celery-task-to-cancel"
        self.job.save(update_fields=["celery_task_id"])
        self.assertContains(self.client.get(reverse("job_detail", args=[self.job.pk])), "لغو جست‌وجو")
        with patch("config.celery.app.control.revoke") as revoke:
            response = self.client.post(reverse("cancel_job", args=[self.job.pk]))
        self.assertEqual(response.status_code, 302)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, SearchJob.Status.CANCELLED)
        self.assertTrue(self.job.completed_at)
        self.assertEqual(self.job.leads.count(), 1)
        self.assertTrue(all(item.status == SourceExecution.Status.CANCELLED for item in self.job.source_executions.all()))
        revoke.assert_called_once_with("celery-task-to-cancel", terminate=False, signal="SIGTERM")

    def test_cancelled_job_does_not_start_source_work(self):
        self.job.status = SearchJob.Status.CANCELLED
        self.job.save(update_fields=["status"])
        with patch("leads.tasks.execute_source", side_effect=AssertionError("cancelled job must not execute")):
            result = run_search_job.apply(args=(self.job.pk,)).get()
        self.assertEqual(result["status"], SearchJob.Status.CANCELLED)

    def test_cancel_running_job_requests_worker_termination(self):
        self.job.status = SearchJob.Status.RUNNING
        self.job.celery_task_id = "active-celery-task"
        self.job.save(update_fields=["status", "celery_task_id"])
        self.client.force_login(self.user)
        with patch("config.celery.app.control.revoke") as revoke:
            self.client.post(reverse("cancel_job", args=[self.job.pk]))
        revoke.assert_called_once_with("active-celery-task", terminate=True, signal="SIGTERM")

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
            enqueue.return_value.id = "recovered-task"
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

    def test_job_requeues_after_a_source_checkpoint_without_losing_results(self):
        def save_checkpoint(source, job, execution):
            execution.status = SourceExecution.Status.QUEUED
            execution.checkpoint = {"kind": "catalog", "variant_index": 1, "page": 1}
            execution.request_count += 1
            execution.save(update_fields=["status", "checkpoint", "request_count"])
            return 0
        with patch("leads.tasks.execute_source", side_effect=save_checkpoint) as execute, \
             patch("leads.tasks.run_search_job.apply_async", return_value=SimpleNamespace(id="next-batch")) as enqueue:
            result = run_search_job.apply(args=(self.job.pk,)).get()
        self.job.refresh_from_db()
        self.assertEqual(execute.call_count, 2)
        self.assertEqual(result["status"], SearchJob.Status.QUEUED)
        self.assertEqual(self.job.status, SearchJob.Status.QUEUED)
        self.assertTrue(all(item.checkpoint for item in self.job.source_executions.all()))
        enqueue.assert_called_once()

    def test_excel_has_lead_and_evidence_sheets(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("export_excel", args=[self.job.pk]))
        workbook = load_workbook(BytesIO(response.content), read_only=True)
        self.assertEqual(workbook.sheetnames, ["سرنخ‌ها", "شواهد"])
        self.assertEqual(workbook["سرنخ‌ها"]["A1"].value, "نام کسب‌وکار")
        self.assertIn("ایمیل عمومی", [cell.value for cell in workbook["سرنخ‌ها"][1]])
        self.assertEqual(workbook["شواهد"].max_row, 2)

    def test_excel_export_includes_more_than_500_leads(self):
        BusinessLead.objects.bulk_create([
            BusinessLead(
                search_job=self.job, normalized_name=f"کسب و کار آزمایشی {index}",
                original_name=f"کسب و کار آزمایشی {index}", city="تهران",
                phone_numbers=["09123456789"], has_mobile_phone=True,
            )
            for index in range(500)
        ])
        self.client.force_login(self.user)
        response = self.client.get(reverse("export_excel", args=[self.job.pk]))
        workbook = load_workbook(BytesIO(response.content), read_only=True)
        self.assertEqual(workbook["سرنخ‌ها"].max_row, 502)

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

    def test_business_without_mobile_is_not_presented_as_a_successful_result(self):
        without_mobile = BusinessLead.objects.create(
            search_job=self.job, normalized_name="تلفن ثابت", original_name="تلفن ثابت",
            phone_numbers=["02112345678"], source_names=["neshan"],
        )
        self.client.force_login(self.user)
        detail = self.client.get(reverse("job_detail", args=[self.job.pk]))
        self.assertEqual(detail.context["page_obj"].paginator.count, 1)
        self.assertEqual(detail.context["summary"]["with_phone"], 1)
        self.assertEqual(detail.context["summary"]["without_phone"], 1)
        self.assertEqual(self.client.get(reverse("lead_detail", args=[self.job.pk, without_mobile.pk])).status_code, 404)

        payload = json.loads(self.client.get(reverse("export_json", args=[self.job.pk])).content)
        self.assertEqual([item["name"] for item in payload["results"]], [self.lead.original_name])
        workbook = load_workbook(BytesIO(self.client.get(reverse("export_excel", args=[self.job.pk])).content), read_only=True)
        self.assertEqual(workbook["سرنخ‌ها"].max_row, 2)
