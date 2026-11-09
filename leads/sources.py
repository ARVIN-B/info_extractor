import asyncio
import json
import logging
import math
import re
from pathlib import Path

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .mcp_client import MCPSourceError, SOURCE_REGISTRY, source_session
from .models import BusinessLead, LeadEvidence, SearchJob, SourceExecution, SourceToolCall
from .normalization import normalize_phone, normalize_text, normalize_website, phone_is_valid

logger = logging.getLogger(__name__)

# Neshan documents these 23 city centers as valid `near` points.
CITY_CENTERS = {
    "تهران": (35.6892, 51.3890), "مشهد": (36.2972, 59.6067), "اصفهان": (32.6546, 51.6680),
    "شیراز": (29.6100, 52.5311), "تبریز": (38.0800, 46.2919), "کرج": (35.8327, 50.9915),
    "قم": (34.6399, 50.8759), "اهواز": (31.3183, 48.6706), "کرمانشاه": (34.3142, 47.0650),
    "رشت": (37.2808, 49.5832), "یزد": (31.8974, 54.3569), "کرمان": (30.2839, 57.0834),
    "ارومیه": (37.5527, 45.0761), "همدان": (34.7983, 48.5148), "اراک": (34.0954, 49.7013),
    "اردبیل": (38.2498, 48.2933), "بندرعباس": (27.1832, 56.2666), "قزوین": (36.2797, 50.0049),
    "زنجان": (36.6736, 48.4787), "ساری": (36.5633, 53.0601), "گرگان": (36.8427, 54.4353),
    "زاهدان": (29.4963, 60.8629), "کیش": (26.5326, 53.9800),
}
CITY_PROVINCE = {
    "تهران": "تهران", "مشهد": "خراسان رضوی", "اصفهان": "اصفهان", "شیراز": "فارس", "تبریز": "آذربایجان شرقی",
    "کرج": "البرز", "قم": "قم", "اهواز": "خوزستان", "کرمانشاه": "کرمانشاه", "رشت": "گیلان", "یزد": "یزد",
    "کرمان": "کرمان", "ارومیه": "آذربایجان غربی", "همدان": "همدان", "اراک": "مرکزی", "اردبیل": "اردبیل",
    "بندرعباس": "هرمزگان", "قزوین": "قزوین", "زنجان": "زنجان", "ساری": "مازندران", "گرگان": "گلستان",
    "زاهدان": "سیستان و بلوچستان",
}

PROVINCE_CAPITALS = {
    "آذربایجان شرقی": "تبریز", "آذربایجان غربی": "ارومیه", "اردبیل": "اردبیل", "اصفهان": "اصفهان",
    "البرز": "کرج", "ایلام": "ایلام", "بوشهر": "بوشهر", "تهران": "تهران", "چهارمحال و بختیاری": "شهرکرد",
    "خراسان جنوبی": "بیرجند", "خراسان رضوی": "مشهد", "خراسان شمالی": "بجنورد", "خوزستان": "اهواز",
    "زنجان": "زنجان", "سمنان": "سمنان", "سیستان و بلوچستان": "زاهدان", "فارس": "شیراز", "قزوین": "قزوین",
    "قم": "قم", "کردستان": "سنندج", "کرمان": "کرمان", "کرمانشاه": "کرمانشاه", "کهگیلویه و بویراحمد": "یاسوج",
    "گلستان": "گرگان", "گیلان": "رشت", "لرستان": "خرم‌آباد", "مازندران": "ساری", "مرکزی": "اراک",
    "هرمزگان": "بندرعباس", "همدان": "همدان", "یزد": "یزد",
}


def get_trade_variants(trade_name):
    path = Path(__file__).parent / "data" / "trade_synonyms.json"
    dictionary = json.loads(path.read_text(encoding="utf-8"))
    normalized = normalize_text(trade_name)
    for trade, variants in dictionary.items():
        if normalize_text(trade) == normalized:
            return list(dict.fromkeys(variants))[:3]
    return [trade_name.strip()]


def _known_center(city):
    key = normalize_text(city)
    return next((point for name, point in CITY_CENTERS.items() if normalize_text(name) == key), None)


def get_scope_points(job):
    if job.geographic_scope_type == SearchJob.ScopeType.CITY:
        point = _known_center(job.geographic_scope_name)
        return [(job.geographic_scope_name, point)]
    if job.geographic_scope_type == SearchJob.ScopeType.PROVINCE:
        capital = PROVINCE_CAPITALS.get(job.geographic_scope_name)
        return [(capital or job.geographic_scope_name, _known_center(capital or ""))]
    return list(CITY_CENTERS.items())


def calculate_source_budget(max_results, selected_source_count, remaining_results, completed_sources_before):
    fair_share = math.ceil(max_results / max(1, selected_source_count))
    return min(remaining_results, fair_share if completed_sources_before == 0 else remaining_results)


def _records(data):
    if isinstance(data, dict):
        for key in ("results", "places", "businesses", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [data] if any(key in data for key in ("id", "place_id", "name", "title")) else []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def _first(data, *keys):
    for key in keys:
        value = data.get(key)
        if value not in (None, "", [], {}):
            return value
    return ""


def _format_phone_values(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(phone) for phone in value if isinstance(phone, (str, int))]
    return []


def _field_values(search_record, detail):
    detail = detail if isinstance(detail, dict) else {}
    name = _first(detail, "name", "title") or _first(search_record, "name", "title", "maintext")
    address = _first(detail, "address", "formatted_address") or _first(search_record, "address", "subtext1")
    website = _first(detail, "website", "web", "url")
    links = detail.get("links") if isinstance(detail.get("links"), dict) else {}
    website = website or links.get("web", "")
    phones = _format_phone_values(_first(detail, "phones", "phone", "telephone"))
    phones += _format_phone_values(_first(search_record, "phones", "phone", "telephone"))
    phones = list(dict.fromkeys(phones))
    lat = _first(detail, "lat", "latitude") or _first(search_record, "lat", "latitude")
    lng = _first(detail, "lng", "lon", "longitude") or _first(search_record, "lng", "lon", "longitude")
    return {
        "name": str(name or "").strip(),
        "address": str(address or "").strip(),
        "phones": phones,
        "website": str(website or "").strip(),
        "category": str(_first(detail, "category", "business_category") or _first(search_record, "category") or "").strip(),
        "lat": lat,
        "lng": lng,
    }


def _source_url(source, record_id):
    if source == "neshan":
        return f"https://neshan.org/maps/places/{record_id}"
    if source == "balad":
        return f"https://balad.ir/p/{record_id}"
    return ""


def _find_match(job, source, record_id, data):
    current = BusinessLead.objects.filter(search_job=job)
    existing = next((lead for lead in current if lead.source_record_ids.get(source) == str(record_id)), None)
    if existing:
        return existing
    phones = {normalize_phone(phone) for phone in data["phones"] if normalize_phone(phone)}
    name = normalize_text(data["name"])
    address = normalize_text(data["address"])
    if not phones or not name or not address:
        return None
    website, domain = normalize_website(data["website"])
    for candidate in current.prefetch_related("evidence"):
        candidate_phones = {normalize_phone(phone) for phone in candidate.phone_numbers if normalize_phone(phone)}
        same_location = normalize_text(candidate.address) == address
        same_name = candidate.normalized_name == name
        same_phone = bool(candidate_phones & phones)
        _, candidate_domain = normalize_website(candidate.website)
        same_domain = bool(domain and candidate_domain and domain == candidate_domain)
        if same_location and same_name and (same_phone or same_domain):
            return candidate
    return None


@transaction.atomic
def save_lead(job, source, search_record, detail):
    record_id = _first(search_record, "id", "place_id", "token") or _first(detail if isinstance(detail, dict) else {}, "id", "place_id", "token")
    if not record_id:
        return None
    record_id = str(record_id)
    fields = _field_values(search_record, detail)
    if not fields["name"]:
        return None
    website, _ = normalize_website(fields["website"])
    valid_phones = [normalize_phone(phone) for phone in fields["phones"] if phone_is_valid(phone)]
    invalid_phone_values = [str(phone) for phone in fields["phones"] if not phone_is_valid(phone)]
    all_phone_values = list(dict.fromkeys(valid_phones + invalid_phone_values))
    lead = _find_match(job, source, record_id, fields)
    source_ids = dict(lead.source_record_ids) if lead else {}
    source_ids[source] = record_id
    sources = list(dict.fromkeys((lead.source_names if lead else []) + [source]))
    address = lead.address if lead and lead.address else fields["address"]
    phones = list(dict.fromkeys((lead.phone_numbers if lead else []) + all_phone_values))
    if invalid_phone_values and not valid_phones:
        status = BusinessLead.Verification.INVALID
    elif len(sources) > 1:
        status = BusinessLead.Verification.CROSS_SOURCE
    elif valid_phones:
        status = BusinessLead.Verification.SOURCE_CONFIRMED
    else:
        status = BusinessLead.Verification.UNVERIFIED
    if lead and lead.website and website and normalize_website(lead.website)[1] != normalize_website(website)[1]:
        status = BusinessLead.Verification.CONFLICTING
    if lead:
        lead.normalized_name = lead.normalized_name or normalize_text(fields["name"])
        lead.phone_numbers = phones
        lead.address = address
        lead.city = lead.city or str(search_record.get("_searched_city") or "")
        lead.province = lead.province or CITY_PROVINCE.get(lead.city, "")
        lead.website = lead.website or website
        lead.business_category = lead.business_category or fields["category"]
        lead.latitude = lead.latitude if lead.latitude is not None else _float_or_none(fields["lat"])
        lead.longitude = lead.longitude if lead.longitude is not None else _float_or_none(fields["lng"])
        lead.source_names = sources
        lead.source_record_ids = source_ids
        lead.verification_status = status
        lead.last_seen_at = timezone.now()
        lead.save()
    else:
        lead = BusinessLead.objects.create(
            search_job=job, normalized_name=normalize_text(fields["name"]), original_name=fields["name"],
            phone_numbers=phones, address=address, city=str(search_record.get("_searched_city") or ""),
            province=CITY_PROVINCE.get(str(search_record.get("_searched_city") or ""), job.geographic_scope_name if job.geographic_scope_type == "province" else ""),
            website=website, business_category=fields["category"], latitude=_float_or_none(fields["lat"]),
            longitude=_float_or_none(fields["lng"]), source_names=sources, source_record_ids=source_ids,
            verification_status=status,
        )
    raw = {"search": search_record, "details": detail}
    values = {
        "name": fields["name"], "address": fields["address"], "phone_numbers": fields["phones"],
        "website": fields["website"], "category": fields["category"], "latitude": fields["lat"], "longitude": fields["lng"],
    }
    for field_name, value in values.items():
        if value in (None, "", [], {}):
            continue
        LeadEvidence.objects.get_or_create(
            business_lead=lead, source_name=source, source_record_id=record_id, field_name=field_name,
            field_value=json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value),
            defaults={"source_url": _source_url(source, record_id), "raw_response": raw},
        )
    LeadEvidence.objects.create(
        business_lead=lead,
        source_name=source,
        source_record_id=record_id,
        field_name="raw_response",
        field_value="Original search and detail response",
        source_url=_source_url(source, record_id),
        raw_response=raw,
    )
    return lead


def _float_or_none(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


async def _search_source(source, job, execution):
    config = SOURCE_REGISTRY[source]
    search_tool, detail_tool = config["tools"]["search"], config["tools"]["detail"]
    variants = get_trade_variants(job.trade_name)
    scope_points = get_scope_points(job)
    remaining = max(0, job.max_results - await sync_to_async(job.leads.count, thread_sensitive=True)())
    if remaining == 0:
        execution.status = SourceExecution.Status.COMPLETED
        execution.completed_at = timezone.now()
        await sync_to_async(execution.save, thread_sensitive=True)()
        return 0
    prior_executions = await sync_to_async(
        lambda: job.source_executions.filter(
            source_name__lt=source, status=SourceExecution.Status.COMPLETED
        ).count(), thread_sensitive=True
    )()
    source_budget = calculate_source_budget(job.max_results, len(job.selected_sources), remaining, prior_executions)
    processed_ids = set()
    saved = 0
    detail_errors = []

    async def invoke(client, tool_name, arguments):
        try:
            result = await client.call(tool_name, arguments)
        except MCPSourceError as exc:
            execution.request_count = client.request_count
            await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["request_count"])
            await sync_to_async(SourceToolCall.objects.create, thread_sensitive=True)(
                source_execution=execution, tool_name=tool_name, duration_ms=exc.duration_ms,
                error_summary=str(exc)[:500]
            )
            raise
        await sync_to_async(SourceToolCall.objects.create, thread_sensitive=True)(
            source_execution=execution, tool_name=tool_name, duration_ms=result.duration_ms,
            result_count=len(_records(result.data)),
        )
        return result

    async with source_session(source, enforce_rate_limit=True) as client:
        # Resolve a city/province location using Balad's documented geocoding search when no local center exists.
        if source in {"balad", "neshan"} and scope_points and scope_points[0][1] is None:
            resolve_args = {"query": scope_points[0][0], "limit": 10}
            if source == "neshan":
                resolve_args["near"] = "Tehran"
            resolved = await invoke(client, search_tool, resolve_args)
            execution.request_count = client.request_count
            await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["request_count"])
            wanted = normalize_text(scope_points[0][0])
            candidates = [r for r in _records(resolved.data) if _float_or_none(r.get("lat")) is not None and _float_or_none(r.get("lng")) is not None]
            location = next((r for r in candidates if normalize_text(str(r.get("name", ""))) == wanted), None)
            if not location:
                raise MCPSourceError(f"Could not resolve the {job.geographic_scope_type} location in {source}")
            scope_points = [(scope_points[0][0], (float(location["lat"]), float(location["lng"]))) ]
        per_location_budget = max(1, source_budget // max(1, len(scope_points)))
        for place_name, point in scope_points:
            location_saved = 0
            for variant in variants:
                if saved >= source_budget or location_saved >= per_location_budget:
                    break
                query = variant if job.geographic_scope_type == SearchJob.ScopeType.IRAN else f"{variant} {place_name}"
                if source == "neshan":
                    near = place_name if _known_center(place_name) and job.geographic_scope_type != SearchJob.ScopeType.IRAN else f"{point[0]},{point[1]}"
                    args = {"query": query, "near": near, "limit": min(30, max(1, per_location_budget - location_saved))}
                else:
                    args = {"query": query, "limit": min(20, max(1, per_location_budget - location_saved))}
                    if point:
                        args.update({"lat": point[0], "lng": point[1]})
                result = await invoke(client, search_tool, args)
                execution.request_count = client.request_count
                execution.result_count += len(_records(result.data))
                await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["request_count", "result_count"])
                for record in _records(result.data):
                    identifier = _first(record, "id", "place_id", "token")
                    if not identifier or str(identifier) in processed_ids:
                        continue
                    processed_ids.add(str(identifier))
                    detail_arg = "place_id" if source == "neshan" else "id"
                    try:
                        detail = await invoke(client, detail_tool, {detail_arg: str(identifier)})
                        detail_data = detail.data
                    except MCPSourceError as exc:
                        detail_data = {}
                        detail_errors.append(f"{identifier}: {exc}")
                        execution.error_count += 1
                        execution.error_details = "\n".join(detail_errors)[-2000:]
                        await sync_to_async(execution.save, thread_sensitive=True)(
                            update_fields=["request_count", "error_count", "error_details"]
                        )
                    execution.request_count = client.request_count
                    await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["request_count"])
                    record["_searched_city"] = place_name
                    lead = await sync_to_async(save_lead, thread_sensitive=True)(job, source, record, detail_data)
                    if lead:
                        saved += 1
                        location_saved += 1
                    if saved >= source_budget or location_saved >= per_location_budget:
                        break
            if saved >= source_budget:
                break
    execution.status = SourceExecution.Status.FAILED if detail_errors else SourceExecution.Status.COMPLETED
    execution.completed_at = timezone.now()
    await sync_to_async(execution.save, thread_sensitive=True)()
    return saved


def execute_source(source, job, execution):
    execution.status = SourceExecution.Status.RUNNING
    execution.started_at = timezone.now()
    execution.save(update_fields=["status", "started_at"])
    try:
        return asyncio.run(_search_source(source, job, execution))
    except Exception as exc:
        logger.exception("Search source %s failed for job %s", source, job.pk)
        execution.status = SourceExecution.Status.FAILED
        execution.completed_at = timezone.now()
        execution.error_count = max(1, execution.error_count)
        execution.error_details = str(exc)[:2000] if isinstance(exc, MCPSourceError) else f"Unexpected {type(exc).__name__}; see server logs."
        execution.save(update_fields=["status", "completed_at", "error_count", "error_details", "request_count"])
        return 0
