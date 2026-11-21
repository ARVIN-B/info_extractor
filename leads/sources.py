import asyncio
from difflib import SequenceMatcher
from datetime import timedelta
import hashlib
import json
import logging
import math
import re
from pathlib import Path

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from redis import Redis

from .adapters import SOURCE_ADAPTERS, _records as _adapter_records, _with_phone_filter
from .mcp_client import MCPBudgetExhausted, MCPSourceError, SOURCE_REGISTRY, source_session
from .models import BusinessLead, BusinessPhone, BusinessPhoneEvidence, JobContact, LeadEvidence, SearchJob, SourceExecution, SourcePlaceDetailCache, SourceRateLimit, SourceToolCall, SuppressedPhone
from .normalization import extract_iranian_mobiles, has_iranian_mobile, normalize_iranian_mobile, normalize_phone, normalize_text, normalize_website, phone_is_valid, short_business_description

logger = logging.getLogger(__name__)


class SearchCancelled(Exception):
    """Stop collecting safely after the user cancels a job."""


class SearchTargetReached(Exception):
    """Stop this source cleanly after the requested unique-phone count is met."""

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
    base = " ".join(trade_name.replace("\u200c", " ").split())
    base = re.sub(r"\s+(?:های|ها)$", "", base).strip()
    normalized = normalize_text(base)
    for trade, variants in dictionary.items():
        if normalize_text(trade) == normalized:
            return list(dict.fromkeys(variants))[:3]
    variants = [base]
    if base.endswith(" فروشی"):
        noun = base.removesuffix(" فروشی").strip()
        if noun:
            variants.append(f"فروشگاه {noun}")
            variants.append(f"{noun} سرای")
    elif base.startswith("فروشگاه "):
        variants.append(base.removeprefix("فروشگاه ").strip())
    return list(dict.fromkeys(variant for variant in variants if variant))[:3]


def is_relevant_trade_record(trade_name, variants, record):
    name = normalize_text(str(_first(record, "name", "title", "maintext")))
    category = normalize_text(str(_first(record, "category", "business_category")))
    if not name:
        return False
    for variant in variants:
        phrase = normalize_text(variant)
        if phrase and (phrase in name or phrase in category):
            return True
    trade_tokens = normalize_text(re.sub(r"\s+(?:های|ها)$", "", trade_name)).split()
    return bool(trade_tokens) and all(token in name or token in category for token in trade_tokens)


def canonical_scope_name(name, scope_type):
    choices = CITY_CENTERS if scope_type == SearchJob.ScopeType.CITY else PROVINCE_CAPITALS
    normalized = normalize_text(name)
    for candidate in choices:
        if normalize_text(candidate) == normalized:
            return candidate
    ranked = sorted(
        ((SequenceMatcher(None, normalized, normalize_text(candidate)).ratio(), candidate) for candidate in choices),
        reverse=True,
    )
    threshold = 0.86 if len(normalized) <= 5 else 0.80
    if ranked and ranked[0][0] >= threshold:
        return ranked[0][1]
    return name.strip()


def _known_center(city):
    key = normalize_text(city)
    return next((point for name, point in CITY_CENTERS.items() if normalize_text(name) == key), None)


def get_scope_points(job):
    if job.geographic_scope_type == SearchJob.ScopeType.CITY:
        city = canonical_scope_name(job.geographic_scope_name, SearchJob.ScopeType.CITY)
        point = _known_center(city)
        return [(city, point)]
    if job.geographic_scope_type == SearchJob.ScopeType.PROVINCE:
        province = canonical_scope_name(job.geographic_scope_name, SearchJob.ScopeType.PROVINCE)
        capital = PROVINCE_CAPITALS.get(province)
        return [(capital or job.geographic_scope_name, _known_center(capital or ""))]
    return list(CITY_CENTERS.items())


def calculate_source_budget(max_results, selected_source_count, remaining_results, completed_sources_before):
    eligible = max(1, selected_source_count - completed_sources_before)
    return min(remaining_results, math.ceil(remaining_results / eligible))


def calculate_source_call_allowance(max_total_calls, max_source_calls, selected_source_count, calls_already_used, other_pending_sources):
    """Reserve a fair share for pending sources while reclaiming unused capacity."""
    per_source_reserve = min(
        max_source_calls,
        math.ceil(max_total_calls / max(1, selected_source_count)),
    )
    reserved_for_others = per_source_reserve * max(0, other_pending_sources)
    return min(
        max_source_calls,
        max(0, max_total_calls - calls_already_used - reserved_for_others),
    )


def _catalog_page_fingerprint(candidates):
    identities = sorted(
        str(record.get("_source_id") or _first(record, "id", "place_id", "token", "shop_id", "seller_id", "seller_code", "vendor_id", "company_id", "national_id") or normalize_text(str(record.get("name", ""))))
        for record, _detail in candidates
    )
    return hashlib.sha256("\n".join(identities).encode("utf-8")).hexdigest() if identities else ""


def _is_repeated_catalog_page(fingerprint, history, current_page):
    return bool(fingerprint and any(
        item.get("hash") == fingerprint and item.get("page") != current_page
        for item in history if isinstance(item, dict)
    ))


def _records(data):
    return _adapter_records(data)


def _first(data, *keys):
    for key in keys:
        value = data.get(key)
        if value not in (None, "", [], {}):
            return value
    return ""


def _format_phone_values(value):
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(phone).strip() for phone in value if isinstance(phone, (str, int)) and str(phone).strip()]
    return []


def _field_values(search_record, detail):
    detail_raw = detail
    detail = detail if isinstance(detail, dict) else {}
    search_raw = search_record.get("_source_raw", search_record) if isinstance(search_record, dict) else search_record
    extraction_payload = search_record.get("_phone_extraction_payload") if isinstance(search_record, dict) else None
    extraction_diagnostics = {}
    if extraction_payload is not None:
        mobile_candidates = extract_iranian_mobiles(
            extraction_payload, path="source", max_depth=settings.PHONE_EXTRACTION_MAX_DEPTH,
            max_nodes=settings.PHONE_EXTRACTION_MAX_NODES, max_text_chars=settings.PHONE_EXTRACTION_MAX_STRING_CHARS,
            diagnostics=extraction_diagnostics,
        )
    else:
        mobile_candidates = [
            *extract_iranian_mobiles(
                search_raw, path="search", max_depth=settings.PHONE_EXTRACTION_MAX_DEPTH,
                max_nodes=settings.PHONE_EXTRACTION_MAX_NODES, max_text_chars=settings.PHONE_EXTRACTION_MAX_STRING_CHARS,
                diagnostics=extraction_diagnostics,
            ),
            *extract_iranian_mobiles(
                detail_raw, path="detail", max_depth=settings.PHONE_EXTRACTION_MAX_DEPTH,
                max_nodes=settings.PHONE_EXTRACTION_MAX_NODES, max_text_chars=settings.PHONE_EXTRACTION_MAX_STRING_CHARS,
                diagnostics=extraction_diagnostics,
            ),
        ]
    name = _first(detail, "name", "shop_name", "seller", "seller_name", "vendor_name", "company_name", "title") or _first(search_record, "name", "shop_name", "seller", "seller_name", "vendor_name", "company_name", "title", "maintext")
    address = _first(detail, "address", "formatted_address") or _first(search_record, "address", "subtext1")
    # A generic `url` on map records points to the provider's place page, not
    # necessarily the business website. Keep those URLs as provenance only.
    website = _first(detail, "website", "business_website", "official_website", "web")
    website = website or _first(search_record, "website", "business_website", "official_website", "web")
    detail_links = detail.get("links") if isinstance(detail.get("links"), dict) else {}
    search_links = search_record.get("links") if isinstance(search_record.get("links"), dict) else {}
    website = website or _first(detail_links, "website", "official_website", "web") or _first(search_links, "website", "official_website", "web")
    description = _first(detail, "description", "business_description", "about", "summary", "maintext", "snippet", "bio") or _first(search_record, "description", "business_description", "about", "summary", "maintext", "snippet", "bio")
    phones = list(dict.fromkeys(candidate.raw_value for candidate in mobile_candidates))
    emails = _format_phone_values(_first(detail, "emails", "email", "contact_email"))
    emails += _format_phone_values(_first(search_record, "emails", "email", "contact_email"))
    emails = list(dict.fromkeys(email for email in emails if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)))
    socials = []
    for source_data in (detail, search_record):
        value = _first(source_data, "social_links", "socials", "social", "instagram", "telegram", "linkedin")
        if isinstance(value, dict):
            socials.extend(str(url).strip() for url in value.values() if isinstance(url, str) and url.strip())
        elif isinstance(value, list):
            socials.extend(str(url).strip() for url in value if isinstance(url, str) and url.strip())
        elif isinstance(value, str) and value.strip():
            socials.append(value.strip())
    socials = list(dict.fromkeys(item for item in socials if normalize_website(item)[0]))
    lat = _first(detail, "lat", "latitude") or _first(search_record, "lat", "latitude")
    lng = _first(detail, "lng", "lon", "longitude") or _first(search_record, "lng", "lon", "longitude")
    return {
        "name": str(name or "").strip(),
        "address": str(address or "").strip(),
        "phones": phones,
        "mobile_candidates": mobile_candidates,
        "extraction_diagnostics": extraction_diagnostics,
        "emails": emails,
        "social_urls": socials,
        "website": str(website or "").strip(),
        "description": str(description or "").strip(),
        "national_id": str(_first(detail, "national_id", "national_code", "nationalId", "company_id") or _first(search_record, "national_id", "national_code", "nationalId", "company_id") or "").strip(),
        "business_type": str(_first(detail, "business_type", "company_type", "kind") or _first(search_record, "business_type", "company_type", "kind") or "").strip(),
        "profile_url": normalize_website(_first(detail, "profile_url", "source_url", "url") or _first(search_record, "profile_url", "source_url", "url") or "")[0],
        "category": str(_first(detail, "category", "business_category") or _first(search_record, "category") or "").strip(),
        "city": str(_first(detail, "city") or _first(search_record, "_source_city", "city") or "").strip(),
        "province": str(_first(detail, "province") or _first(search_record, "_source_province", "province") or "").strip(),
        "lat": lat,
        "lng": lng,
    }


def _source_url(source, record_id):
    if source == "neshan":
        return f"https://neshan.org/maps/places/{record_id}"
    if source == "balad":
        return f"https://balad.ir/p/{record_id}"
    return ""


def _add_source_diagnostics(job, source, increments):
    execution = SourceExecution.objects.filter(search_job=job, source_name=source).first()
    if not execution:
        return
    diagnostics = dict(execution.diagnostics or {})
    for name, amount in increments.items():
        diagnostics[name] = int(diagnostics.get(name, 0) or 0) + int(amount or 0)
    execution.diagnostics = diagnostics
    execution.save(update_fields=["diagnostics"])


def _add_variant_yield(job, source, variant, *, businesses=0, mobile_rows=0):
    if not variant:
        return
    execution = SourceExecution.objects.filter(search_job=job, source_name=source).first()
    if not execution:
        return
    diagnostics = dict(execution.diagnostics or {})
    yields = dict(diagnostics.get("query_variant_yield", {}))
    item = dict(yields.get(str(variant)[:200], {}))
    item["unique_businesses_discovered"] = int(item.get("unique_businesses_discovered", 0) or 0) + int(bool(businesses))
    item["mobile_rows_created"] = int(item.get("mobile_rows_created", 0) or 0) + int(mobile_rows or 0)
    yields[str(variant)[:200]] = item
    diagnostics["query_variant_yield"] = yields
    diagnostics["query_variants_measured"] = len(yields)
    diagnostics["variant_businesses_discovered"] = int(diagnostics.get("variant_businesses_discovered", 0) or 0) + int(bool(businesses))
    diagnostics["variant_mobile_rows_created"] = int(diagnostics.get("variant_mobile_rows_created", 0) or 0) + int(mobile_rows or 0)
    execution.diagnostics = diagnostics
    execution.save(update_fields=["diagnostics"])


def _record_tool_diagnostics(execution_id, source, tool_name, data):
    config = SOURCE_REGISTRY[source]
    role = next((name for name, value in config["tools"].items() if value == tool_name), "other")
    rows = _records(data)
    fields = {
        "mcp_responses_received": 1,
        "raw_response_payloads_received": 1,
    }
    if role in {"search", "nearby"}:
        fields.update(search_responses_received=1, search_records_received=len(rows))
    elif role in {"detail", "offers", "shops"}:
        fields.update(detail_responses_received=1, detail_records_received=len(rows))
    else:
        fields.update(other_responses_received=1, other_records_received=len(rows))
    execution = SourceExecution.objects.get(pk=execution_id)
    diagnostics = dict(execution.diagnostics or {})
    for name, amount in fields.items():
        diagnostics[name] = int(diagnostics.get(name, 0) or 0) + amount
    execution.diagnostics = diagnostics
    execution.save(update_fields=["diagnostics"])


def _safe_source_response(value):
    """Retain unknown source fields within configured structural and byte limits."""
    limits = {"nodes": 0}
    private_keys = {"user", "customer", "buyer", "account", "owner", "personal_profile", "user_profile"}
    public_keys = {"public_contact", "business_contact", "contact_info", "public_profile"}

    def convert(item, depth=0, private_context=False):
        limits["nodes"] += 1
        if depth > settings.PHONE_EXTRACTION_MAX_DEPTH or limits["nodes"] > settings.PHONE_EXTRACTION_MAX_NODES:
            return {"__truncated__": True}
        if isinstance(item, dict):
            result = {}
            for key, child in list(item.items())[:1000]:
                key_text = str(key)[:200]
                normalized_key = re.sub(r"[^a-z0-9]+", "_", key_text.casefold()).strip("_")
                child_private = False if normalized_key in public_keys else (private_context or normalized_key in private_keys)
                result[key_text] = convert(child, depth + 1, child_private)
            return result
        if isinstance(item, (list, tuple)):
            return [convert(child, depth + 1, private_context) for child in item[:1000]]
        if isinstance(item, str):
            if private_context:
                return "[redacted private profile value]"
            return item[:settings.PHONE_EXTRACTION_MAX_STRING_CHARS]
        if isinstance(item, (int, float, bool)) or item is None:
            if private_context:
                return "[redacted private profile value]"
            return item
        model_dump = getattr(item, "model_dump", None)
        if callable(model_dump):
            try:
                return convert(model_dump(mode="json"), depth + 1, private_context)
            except Exception:
                pass
        try:
            return convert(vars(item), depth + 1, private_context)
        except (TypeError, AttributeError):
            return str(item)[:settings.PHONE_EXTRACTION_MAX_STRING_CHARS]

    safe = convert(value)
    encoded = json.dumps(safe, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    if len(encoded) <= settings.SOURCE_RAW_RESPONSE_MAX_BYTES:
        return safe
    # Reserve enough room for the wrapper itself so the persisted JSON always
    # respects the configured byte budget, including multibyte UTF-8 payloads.
    limit = settings.SOURCE_RAW_RESPONSE_MAX_BYTES
    wrapper = {"__truncated__": True, "max_bytes": limit, "json_prefix": ""}
    overhead = len(json.dumps(wrapper, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    preview_budget = max(0, limit - overhead)
    preview = encoded[:preview_budget].decode("utf-8", errors="ignore")
    wrapper["json_prefix"] = preview
    while len(json.dumps(wrapper, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > limit and preview:
        preview = preview[:-1]
        wrapper["json_prefix"] = preview
    return wrapper


def _cached_source_detail(source, record_id):
    ttl = settings.SOURCE_DETAIL_CACHE_TTL_SECONDS
    if ttl <= 0:
        return None
    cached = SourcePlaceDetailCache.objects.filter(
        source_name=source, source_record_id=str(record_id), expires_at__gt=timezone.now()
    ).first()
    return cached.detail_data if cached else None


@transaction.atomic
def _store_source_detail(source, record_id, detail, cache_empty=False):
    if not isinstance(detail, dict) or (not detail and not cache_empty):
        return
    safe_detail = _safe_source_response(detail)
    if not safe_detail and not cache_empty:
        return
    ttl = settings.SOURCE_DETAIL_CACHE_TTL_SECONDS
    if ttl <= 0:
        return
    now = timezone.now()
    SourcePlaceDetailCache.objects.update_or_create(
        source_name=source,
        source_record_id=str(record_id),
        defaults={"detail_data": safe_detail, "expires_at": now + timedelta(seconds=ttl)},
    )
    SourcePlaceDetailCache.objects.filter(expires_at__lt=now).delete()


def _find_match(job, source, record_id, data):
    current = BusinessLead.objects.filter(search_job=job)
    existing = current.filter(**{f"source_record_ids__{source}": str(record_id)}).first() if record_id else None
    if existing:
        return existing
    phones = {normalize_phone(phone) for phone in data["phones"] if normalize_phone(phone)}
    name = normalize_text(data["name"])
    address = normalize_text(data["address"])
    if not name:
        return None
    national_id = re.sub(r"\D", "", data.get("national_id", ""))
    if national_id:
        existing = current.filter(national_id=national_id).exclude(national_id="").first()
        if existing:
            return existing
    website, domain = normalize_website(data["website"])
    candidate_rows = current.filter(normalized_name=name)
    for candidate in candidate_rows.iterator(chunk_size=200):
        candidate_phones = {normalize_phone(phone) for phone in candidate.phone_numbers if normalize_phone(phone)}
        same_location = normalize_text(candidate.address) == address
        same_name = candidate.normalized_name == name
        same_phone = bool(candidate_phones & phones)
        _, candidate_domain = normalize_website(candidate.website)
        same_domain = bool(domain and candidate_domain and domain == candidate_domain)
        candidate_city = normalize_text(candidate.city)
        current_city = normalize_text(data.get("city", ""))
        address_conflict = bool(candidate.address and data["address"] and not same_location)
        same_city_or_unknown = not candidate_city or not current_city or candidate_city == current_city
        same_branch_address = bool(candidate.address and data["address"] and same_location and same_city_or_unknown)
        same_contact_identity = bool(same_name and same_city_or_unknown and not address_conflict and (same_phone or same_domain))
        if same_name and (same_branch_address or same_contact_identity):
            return candidate
    return None


@transaction.atomic
def save_lead(job, source, search_record, detail, return_created=False):
    record_id = _first(search_record, "_source_id", "id", "place_id", "token", "shop_id", "seller_id", "seller_code", "vendor_id", "company_id", "national_id") or _first(detail if isinstance(detail, dict) else {}, "id", "place_id", "token", "shop_id", "seller_id", "seller_code", "vendor_id", "company_id", "national_id")
    if not record_id:
        return None
    record_id = str(record_id)
    fields = _field_values(search_record, detail)
    extraction_stats = fields["extraction_diagnostics"]
    if not fields["name"]:
        return None
    website, _ = normalize_website(fields["website"])
    valid_phones = list(dict.fromkeys(
        number for candidate in fields["mobile_candidates"]
        if (number := normalize_iranian_mobile(candidate.raw_value))
    ))
    phone_inputs = []
    for source_data in (detail if isinstance(detail, dict) else {}, search_record):
        if isinstance(source_data, dict):
            phone_inputs.extend(_format_phone_values(_first(source_data, "phone", "phones", "telephone")))
    phone_evidence_values = list(dict.fromkeys([*fields["phones"], *phone_inputs]))
    invalid_phone_values = [str(phone).strip() for phone in phone_inputs if str(phone).strip() and not phone_is_valid(phone)]
    all_phone_values = valid_phones
    lead = _find_match(job, source, record_id, fields)
    is_new_business = lead is None
    was_mobile = bool(lead and (lead.has_mobile_phone or has_iranian_mobile(lead.phone_numbers)))
    source_ids = dict(lead.source_record_ids) if lead else {}
    source_ids[source] = record_id
    sources = list(dict.fromkeys((lead.source_names if lead else []) + [source]))
    address = lead.address if lead and lead.address else fields["address"]
    source_city = fields["city"] or str(search_record.get("_searched_city") or "")
    source_province = fields["province"] or CITY_PROVINCE.get(source_city, job.geographic_scope_name if job.geographic_scope_type == SearchJob.ScopeType.PROVINCE else "")
    phones = list(dict.fromkeys((lead.phone_numbers if lead else []) + all_phone_values))
    has_mobile_phone = has_iranian_mobile(phones)
    emails = list(dict.fromkeys((lead.emails if lead else []) + [email.lower() for email in fields["emails"]]))
    socials = list(dict.fromkeys((lead.social_urls if lead else []) + [normalize_website(url)[0] for url in fields["social_urls"] if normalize_website(url)[0]]))
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
    if len(set(phones)) > 1 and lead and lead.phone_numbers and not set(lead.phone_numbers).intersection(phones):
        phone_status = BusinessLead.PhoneStatus.CONFLICTING
    elif invalid_phone_values and not valid_phones:
        phone_status = BusinessLead.PhoneStatus.INVALID
    elif valid_phones:
        phone_status = BusinessLead.PhoneStatus.FOUND_PUBLIC
    elif "phone" not in SOURCE_REGISTRY[source].get("fields", []) and not phone_inputs:
        phone_status = BusinessLead.PhoneStatus.NOT_PROVIDED
    else:
        phone_status = BusinessLead.PhoneStatus.NOT_FOUND
    if phone_status == BusinessLead.PhoneStatus.CONFLICTING:
        status = BusinessLead.Verification.CONFLICTING
    if lead:
        lead.normalized_name = lead.normalized_name or normalize_text(fields["name"])
        lead.phone_numbers = phones
        lead.has_mobile_phone = has_mobile_phone
        lead.emails = emails
        lead.social_urls = socials
        lead.address = address
        lead.city = lead.city or source_city
        lead.province = lead.province or source_province
        lead.website = lead.website or website
        lead.national_id = lead.national_id or re.sub(r"\D", "", fields["national_id"])
        lead.business_type = lead.business_type or fields["business_type"] or SOURCE_REGISTRY[source].get("kind", "")
        lead.phone_status = phone_status if phone_status != BusinessLead.PhoneStatus.NOT_FOUND or lead.phone_status == BusinessLead.PhoneStatus.NOT_CHECKED else lead.phone_status
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
            phone_numbers=phones, address=address, city=source_city,
            has_mobile_phone=has_mobile_phone,
            province=source_province,
            website=website, business_category=fields["category"], latitude=_float_or_none(fields["lat"]),
            longitude=_float_or_none(fields["lng"]), source_names=sources, source_record_ids=source_ids,
            verification_status=status, emails=emails, social_urls=socials,
            national_id=re.sub(r"\D", "", fields["national_id"]), business_type=fields["business_type"] or SOURCE_REGISTRY[source].get("kind", ""), phone_status=phone_status,
        )
    lead.confidence_score = calculate_confidence(lead)
    lead.save(update_fields=["confidence_score"])
    retention_days = settings.SOURCE_RAW_RESPONSE_RETENTION_DAYS
    raw = _safe_source_response({"search_record": search_record, "detail_response": detail}) if retention_days else {}
    raw_expires_at = timezone.now() + timedelta(days=retention_days) if retention_days else None
    source_url = fields["profile_url"] or _source_url(source, record_id)
    newly_persisted = 0
    already_persisted = 0
    suppressed_count = 0
    for candidate in fields["mobile_candidates"]:
        normalized = normalize_iranian_mobile(candidate.raw_value)
        if not normalized:
            continue
        contact_job = SearchJob.objects.select_for_update().get(pk=job.pk)
        if contact_job.contacts.count() < contact_job.requested_phone_count:
            JobContact.objects.get_or_create(
                search_job=contact_job,
                normalized_number="0" + normalized[3:],
                defaults={
                    "source_name": source, "business_name": fields["name"][:255],
                    "website": website, "address": fields["address"],
                    "description": short_business_description(fields["description"]), "evidence_url": source_url,
                },
            )
        permission = (
            BusinessPhone.PermissionStatus.PUBLIC_BUSINESS_CONTACT if candidate.contact_context
            else BusinessPhone.PermissionStatus.UNKNOWN
        )
        phone, _ = BusinessPhone.objects.get_or_create(
            business_lead=lead, normalized_number=normalized,
            defaults={"permission_status": permission},
        )
        if _:
            newly_persisted += 1
        else:
            already_persisted += 1
        if phone.last_seen_at < timezone.now():
            phone.last_seen_at = timezone.now()
            phone.save(update_fields=["last_seen_at"])
        if SuppressedPhone.objects.filter(normalized_number=normalized).exists():
            suppressed_count += 1
            phone.permission_status = BusinessPhone.PermissionStatus.SUPPRESSED
            phone.save(update_fields=["permission_status"])
        elif candidate.contact_context and phone.permission_status == BusinessPhone.PermissionStatus.UNKNOWN:
            phone.permission_status = BusinessPhone.PermissionStatus.PUBLIC_BUSINESS_CONTACT
            phone.save(update_fields=["permission_status"])
        match_status = (
            BusinessPhoneEvidence.MatchStatus.SOURCE_CONTACT_FIELD if candidate.contact_context
            else BusinessPhoneEvidence.MatchStatus.SOURCE_RECORD
        )
        confidence = 0.9 if candidate.field_path.startswith("detail") else 0.7
        if candidate.contact_context:
            confidence = min(0.99, confidence + 0.08)
        BusinessPhoneEvidence.objects.get_or_create(
            business_phone=phone, source_name=source, source_record_id=record_id,
            field_path=candidate.field_path[:512], raw_value=candidate.raw_value[:160],
            defaults={
                "source_url": source_url, "confidence_score": confidence,
                "business_match_status": match_status,
            },
        )
    _add_source_diagnostics(job, source, {
        "business_records_inspected": 1,
        "extractor_nodes_traversed": extraction_stats.get("nodes_traversed", 0),
        "strings_inspected": extraction_stats.get("strings_inspected", 0),
        "phone_like_candidates": extraction_stats.get("phone_like_patterns", 0),
        "identifier_filtered_candidates": extraction_stats.get("identifier_filtered_candidates", 0),
        "private_account_candidates_filtered": extraction_stats.get("private_account_candidates_filtered", 0),
        "normalization_rejected_candidates": extraction_stats.get("normalization_rejected", 0),
        "valid_mobile_candidates": len(fields["mobile_candidates"]),
        "persisted_mobile_rows_created": newly_persisted,
        "mobile_rows_already_present": already_persisted,
        "suppressed_mobile_candidates": suppressed_count,
        "records_without_valid_mobile": int(not valid_phones),
        "raw_response_truncated_records": int(bool(raw.get("__truncated__"))) if isinstance(raw, dict) else 0,
    })
    _add_variant_yield(
        job, source, search_record.get("_query_variant"),
        businesses=is_new_business, mobile_rows=newly_persisted,
    )
    source_execution = SourceExecution.objects.filter(search_job=job, source_name=source).first()
    if source_execution:
        diagnostics = dict(source_execution.diagnostics or {})
        diagnostics["unique_normalized_mobiles"] = BusinessPhoneEvidence.objects.filter(
            source_name=source, business_phone__business_lead__search_job=job,
        ).values("business_phone__normalized_number").distinct().count()
        diagnostics["businesses_with_mobile"] = BusinessPhoneEvidence.objects.filter(
            source_name=source, business_phone__business_lead__search_job=job,
        ).values("business_phone__business_lead_id").distinct().count()
        source_execution.diagnostics = diagnostics
        source_execution.save(update_fields=["diagnostics"])
    values = {
        "name": fields["name"], "address": fields["address"], "phone_numbers": phone_evidence_values,
        "website": fields["website"], "category": fields["category"], "latitude": fields["lat"], "longitude": fields["lng"],
        "emails": fields["emails"], "social_urls": fields["social_urls"], "national_id": fields["national_id"],
        "business_type": fields["business_type"],
        "city": fields["city"], "province": fields["province"],
    }
    for field_name, value in values.items():
        if value in (None, "", [], {}):
            continue
        normalized_value = _normalized_evidence_value(field_name, value)
        if field_name == "phone_numbers":
            if all(normalize_iranian_mobile(phone) for phone in value):
                validation_status = "format_valid_unverified"
            elif all(phone_is_valid(phone) for phone in value):
                validation_status = "non_mobile_excluded"
            else:
                validation_status = "contains_invalid_format"
        elif field_name == "emails":
            validation_status = "syntax_valid_unverified"
        elif field_name == "website":
            validation_status = "syntax_valid_unverified" if normalize_website(value)[0] else "invalid_format"
        else:
            validation_status = "source_reported"
        LeadEvidence.objects.get_or_create(
            business_lead=lead, source_name=source, source_record_id=record_id, field_name=field_name,
            field_value=json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value),
            defaults={
            "source_url": source_url, "raw_response": raw,
                "raw_response_expires_at": raw_expires_at,
                "normalized_value": json.dumps(normalized_value, ensure_ascii=False) if isinstance(normalized_value, (list, dict)) else str(normalized_value),
                "confidence_score": 0.8 if source in {"neshan", "balad", "emalls"} else 0.6,
                "validation_status": validation_status,
                "data_type": "public_business_contact" if field_name in {"phone_numbers", "emails", "website"} else "public_business_data",
            },
        )
    LeadEvidence.objects.get_or_create(
        business_lead=lead, source_name=source, source_record_id=record_id,
        field_name="raw_response", field_value="Original search and detail response",
        defaults={"source_url": source_url, "raw_response": raw, "raw_response_expires_at": raw_expires_at},
    )
    return (lead, has_mobile_phone and not was_mobile) if return_created else lead


def _normalized_evidence_value(field_name, value):
    if field_name == "phone_numbers":
        return [normalize_iranian_mobile(phone) or str(phone).strip() for phone in value]
    if field_name == "emails":
        return [str(email).strip().lower() for email in value]
    if field_name == "website":
        return normalize_website(value)[0]
    if field_name == "social_urls":
        return [normalize_website(url)[0] for url in value]
    if field_name == "national_id":
        return re.sub(r"\D", "", str(value))
    if isinstance(value, (list, dict)):
        return value
    return str(value).strip()


def calculate_confidence(lead):
    """Transparent deterministic score: independent sources and public fields add fixed points."""
    score = 0.35 + min(0.25, max(0, len(set(lead.source_names)) - 1) * 0.15)
    score += 0.15 if lead.phone_numbers else 0
    score += 0.10 if lead.website else 0
    score += 0.05 if lead.emails else 0
    score += 0.10 if lead.national_id else 0
    if lead.verification_status == BusinessLead.Verification.CONFLICTING:
        score -= 0.20
    return round(max(0.0, min(1.0, score)), 2)


def _float_or_none(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _active_source_cooldown(source):
    state = SourceRateLimit.objects.filter(source_name=source).first()
    now = timezone.now()
    if state and state.cooldown_until > now:
        return state
    if settings.MCP_DISTRIBUTED_SOURCE_LIMITS:
        client = Redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=2, socket_timeout=2)
        try:
            ttl = client.ttl(f"info-extractor:mcp-cooldown:{source}")
            if ttl and ttl > 0:
                return type("SharedCooldown", (), {"cooldown_until": now + timedelta(seconds=ttl)})()
        except Exception:
            logger.warning("Could not read shared MCP cooldown for %s; using database state", source)
        finally:
            client.close()
    return None


def _remember_source_rate_limit(source, error):
    now = timezone.now()
    if error.retry_after_seconds:
        fallback_seconds = error.retry_after_seconds
    elif error.error_type == "monthly_quota_exceeded":
        fallback_seconds = settings.SOURCE_MONTHLY_QUOTA_COOLDOWN_SECONDS
    elif error.error_type == "daily_quota_exceeded":
        fallback_seconds = settings.SOURCE_DAILY_QUOTA_COOLDOWN_SECONDS
    else:
        fallback_seconds = settings.SOURCE_RATE_LIMIT_DEFAULT_COOLDOWN_SECONDS
    seconds = max(1, fallback_seconds)
    cooldown_until = now + timedelta(seconds=seconds)
    state, _ = SourceRateLimit.objects.get_or_create(
        source_name=source,
        defaults={"cooldown_until": cooldown_until, "reason": "HTTP 429 rate limit"},
    )
    if state.cooldown_until < cooldown_until:
        state.cooldown_until = cooldown_until
    state.reason = str(error)[:160] or "HTTP 429 rate limit"
    state.updated_at = now
    state.save(update_fields=["cooldown_until", "reason", "updated_at"])
    if settings.MCP_DISTRIBUTED_SOURCE_LIMITS:
        client = Redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=2, socket_timeout=2)
        try:
            client.set(f"info-extractor:mcp-cooldown:{source}", "1", ex=max(1, int((state.cooldown_until - now).total_seconds())))
        except Exception:
            logger.warning("Could not publish shared MCP cooldown for %s; database state remains persisted", source)
        finally:
            client.close()
    return state.cooldown_until


def get_source_query_variants(trade_name, source, expansion=None):
    """Add source-specific nearby searches instead of excluding a catalog source."""
    query = normalize_text(trade_name)
    online = any(term in query for term in ("فروشگاه اینترنتی", "فروشگاه آنلاین", "آنلاین", "اینترنتی", "مارکت پلیس"))
    expanded = expansion or {}
    variants = [trade_name]
    category = expanded.get("category")
    if category:
        variants.extend(category.get("aliases", []))
    variants.extend(get_trade_variants(trade_name))
    if source == "emalls" and not online:
        variants.extend(f"فروشگاه {item}" for item in variants[:2])
    variants.extend(item.get("query", "") for item in expanded.get("variants", []) if isinstance(item, dict))
    maximum = max(1, settings.SEARCH_QUERY_MAX_VARIANTS + 1)
    return list(dict.fromkeys(item.strip() for item in variants if item.strip()))[:maximum]


async def _search_catalog_source(source, job, execution, adapter, client, invoke, source_budget, variants):
    city = job.geographic_scope_name if job.geographic_scope_type == SearchJob.ScopeType.CITY else ""
    province = job.geographic_scope_name if job.geographic_scope_type == SearchJob.ScopeType.PROVINCE else ""
    saved, errors, was_rate_limited = 0, [], False
    processed_ids = set()
    checkpoint = dict(execution.checkpoint or {})
    variant_index = max(0, int(checkpoint.get("variant_index", 0)))
    start_page = int(checkpoint.get("page", 1))
    record_offset = max(0, int(checkpoint.get("record_offset", 0)))
    for index in range(variant_index, len(variants)):
        variant = variants[index]
        discovery = None
        if variant not in execution.query_variants:
            execution.query_variants = [*execution.query_variants, variant]
        area = city or province or "ایران"
        if area not in execution.areas_checked:
            execution.areas_checked = [*execution.areas_checked, area]
        await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["query_variants", "areas_checked"])
        try:
            discovery = await adapter.discover(
                client=client, invoke=invoke, query=variant, city=city, province=province,
                limit=job.requested_phone_count,
                start_page=start_page if index == variant_index else 1,
            )
            candidates = discovery.records
            execution.truncated = execution.truncated or (discovery.truncated and discovery.next_page is None)
        except MCPSourceError as exc:
            candidates = getattr(exc, "partial_records", [])
            execution.truncated = execution.truncated or getattr(exc, "truncated", False)
            if exc.rate_limited:
                was_rate_limited = True
                cooldown_until = await sync_to_async(_remember_source_rate_limit, thread_sensitive=True)(source, exc)
                execution.error_type = exc.error_type if exc.error_type.endswith("quota_exceeded") else "long_cooldown" if exc.retry_after_seconds and exc.retry_after_seconds >= settings.SOURCE_RATE_LIMIT_LONG_THRESHOLD_SECONDS else "rate_limit"
                execution.cooldown_until = cooldown_until
                execution.retry_count += getattr(exc, "retry_count", 0)
                execution.error_details = str(exc)[:2000]
            else:
                errors.append(str(exc))
        current_page = start_page if index == variant_index else 1
        page_fingerprint = _catalog_page_fingerprint(candidates)
        prior_fingerprints = checkpoint.get("page_fingerprints", []) if index == variant_index else []
        repeated_page = _is_repeated_catalog_page(page_fingerprint, prior_fingerprints, current_page)
        if repeated_page:
            candidates_to_save = []
            execution.truncated = True
        else:
            candidates_to_save = candidates
        resume_offset = None
        for record_index, (record, detail) in enumerate(candidates_to_save):
            if await sync_to_async(lambda: job.contacts.count() >= job.requested_phone_count, thread_sensitive=True)():
                break
            if index == variant_index and record_index < record_offset:
                continue
            if saved >= source_budget:
                resume_offset = record_index
                break
            record = dict(record)
            record["_query_variant"] = variant
            stable_id = str(record.get("_source_id") or _first(record, "id", "place_id", "token", "shop_id", "seller_id", "seller_code", "vendor_id", "company_id", "national_id") or "")
            if stable_id and stable_id in processed_ids:
                continue
            if stable_id:
                processed_ids.add(stable_id)
            actual_city = str(record.get("_source_city") or "").strip()
            actual_province = str(record.get("_source_province") or "").strip()
            record["_searched_city"] = actual_city or city or province
            if record.get("_source_id"):
                record.setdefault("id", record["_source_id"])
            lead, newly_qualified = await sync_to_async(save_lead, thread_sensitive=True)(job, source, record, detail, return_created=True)
            await sync_to_async(execution.refresh_from_db, thread_sensitive=True)(fields=["diagnostics"])
            if lead and newly_qualified:
                saved += 1
        execution.result_count += len(candidates)
        await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["result_count"])
        if resume_offset is not None:
            execution.checkpoint = {"kind": "catalog", "variant_index": index, "page": current_page, "record_offset": resume_offset, "page_fingerprints": prior_fingerprints}
            execution.status = SourceExecution.Status.QUEUED
            execution.completed_at = None
            await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["checkpoint", "status", "completed_at"])
            return saved
        if was_rate_limited:
            execution.checkpoint = {
                "kind": "catalog", "variant_index": index,
                "page": current_page,
                "record_offset": len(candidates),
                "page_fingerprints": prior_fingerprints,
            }
            execution.status = SourceExecution.Status.LONG_COOLDOWN if execution.error_type == "long_cooldown" else SourceExecution.Status.RATE_LIMITED
            execution.completed_at = timezone.now()
            await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["checkpoint", "status", "completed_at", "cooldown_until", "error_type", "error_details"])
            return saved
        next_page = None if repeated_page else getattr(discovery, "next_page", None)
        if next_page is not None:
            fingerprints = [item for item in prior_fingerprints if isinstance(item, dict)]
            if page_fingerprint:
                fingerprints = [*fingerprints, {"page": current_page, "hash": page_fingerprint}]
            execution.checkpoint = {"kind": "catalog", "variant_index": index, "page": next_page, "record_offset": 0, "page_fingerprints": fingerprints[-settings.SEARCH_MAX_PAGES_PER_SOURCE:]}
            execution.status = SourceExecution.Status.QUEUED
            execution.completed_at = None
            await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["checkpoint", "status", "completed_at"])
            return saved
        execution.checkpoint = {"kind": "catalog", "variant_index": index + 1, "page": 1, "record_offset": 0}
        await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["checkpoint"])
        if errors or saved >= source_budget:
            if saved >= source_budget:
                if index + 1 < len(variants):
                    execution.status = SourceExecution.Status.QUEUED
                    execution.completed_at = None
                    await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["status", "completed_at"])
                    return saved
            break
        # One query variant per Celery invocation keeps MCP work and task duration bounded.
        if index + 1 < len(variants):
            execution.status = SourceExecution.Status.QUEUED
            execution.completed_at = None
            await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["status", "completed_at"])
            return saved
    if errors:
        execution.status = SourceExecution.Status.PARTIAL if execution.result_count else SourceExecution.Status.FAILED
        execution.error_count += len(errors)
        execution.error_details = "\n".join(errors)[-2000:]
        execution.error_type = "source_error"
    elif was_rate_limited:
        execution.status = SourceExecution.Status.LONG_COOLDOWN if execution.error_type == "long_cooldown" else SourceExecution.Status.RATE_LIMITED
    else:
        execution.status = SourceExecution.Status.COMPLETED
    execution.completed_at = timezone.now()
    await sync_to_async(execution.save, thread_sensitive=True)()
    return saved


async def _search_source(source, job, execution):
    initial_request_count = execution.request_count
    config = SOURCE_REGISTRY[source]
    geocode_tool = config["tools"]["search"]
    search_tool = config["tools"].get("nearby", geocode_tool)
    detail_tool = config["tools"].get("detail")
    
    variants = get_source_query_variants(job.trade_name, source, getattr(job, "query_expansion", {}))
    scope_points = get_scope_points(job)
    remaining = max(0, job.requested_phone_count - await sync_to_async(
        lambda: job.contacts.count(), thread_sensitive=True
    )())
    if remaining == 0:
        execution.status = SourceExecution.Status.COMPLETED
        execution.completed_at = timezone.now()
        await sync_to_async(execution.save, thread_sensitive=True)()
        return 0
    selected_sources = list(dict.fromkeys(job.selected_sources))
    relevant_source_count = max(1, len(selected_sources))
    prior_executions = await sync_to_async(
        lambda: job.source_executions.filter(
            source_name__in=selected_sources, status=SourceExecution.Status.COMPLETED
        ).exclude(source_name=source).count(), thread_sensitive=True
    )()
    source_budget = calculate_source_budget(job.max_results, relevant_source_count, remaining, prior_executions)
    processed_ids = set()
    saved = 0
    detail_errors = []
    detail_warnings = []
    detail_rate_limited = False

    cooldown = await sync_to_async(_active_source_cooldown, thread_sensitive=True)(source)
    if cooldown:
        remaining_cooldown = int((cooldown.cooldown_until - timezone.now()).total_seconds())
        execution.status = SourceExecution.Status.LONG_COOLDOWN if remaining_cooldown >= settings.SOURCE_RATE_LIMIT_LONG_THRESHOLD_SECONDS else SourceExecution.Status.RATE_LIMITED
        execution.error_type = "long_cooldown" if execution.status == SourceExecution.Status.LONG_COOLDOWN else "rate_limit"
        execution.cooldown_until = cooldown.cooldown_until
        execution.error_details = f"منبع تا {timezone.localtime(cooldown.cooldown_until).strftime('%H:%M:%S')} به‌دلیل محدودیت نرخ موقتاً متوقف است؛ نتیجهٔ خالی محسوب نمی‌شود."
        execution.completed_at = timezone.now()
        await sync_to_async(execution.save, thread_sensitive=True)()
        return 0

    async def invoke(client, tool_name, arguments):
        cancelled = await sync_to_async(
            lambda: SearchJob.objects.filter(pk=job.pk, status=SearchJob.Status.CANCELLED).exists(),
            thread_sensitive=True,
        )()
        if cancelled:
            raise SearchCancelled
        target_reached = await sync_to_async(
            lambda: job.contacts.count() >= job.requested_phone_count,
            thread_sensitive=True,
        )()
        if target_reached:
            raise SearchTargetReached
        job_calls = await sync_to_async(
            lambda: sum(job.source_executions.values_list("request_count", flat=True)), thread_sensitive=True
        )()
        other_pending_sources = await sync_to_async(
            lambda: job.source_executions.filter(
                status__in=[SourceExecution.Status.QUEUED, SourceExecution.Status.RUNNING]
            ).exclude(pk=execution.pk).count(),
            thread_sensitive=True,
        )()
        source_call_allowance = calculate_source_call_allowance(
            settings.MAX_MCP_CALLS_PER_JOB,
            settings.SOURCE_MAX_CALLS_PER_JOB,
            len(job.selected_sources),
            job_calls,
            other_pending_sources,
        )
        if job_calls >= settings.MAX_MCP_CALLS_PER_JOB:
            execution.truncated = True
            await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["truncated"])
            raise MCPBudgetExhausted("Global MCP call budget exhausted.", global_budget=True)
        if source_call_allowance <= 0:
            execution.truncated = True
            await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["truncated"])
            raise MCPBudgetExhausted(f"{source} reached its fair share; remaining calls are reserved for other selected sources.")
        if execution.request_count + client.request_count >= settings.SOURCE_MAX_CALLS_PER_JOB:
            execution.truncated = True
            await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["truncated"])
            raise MCPBudgetExhausted(f"{source} reached its per-source call budget.")
        batch_remaining = settings.SOURCE_MAX_CALLS_PER_BATCH - client.request_count
        lifetime_remaining = settings.SOURCE_MAX_CALLS_PER_JOB - execution.request_count
        client.request_allowance = min(source_call_allowance, batch_remaining, lifetime_remaining)
        try:
            result = await client.call(tool_name, arguments)
        except MCPBudgetExhausted as exc:
            execution.request_count = initial_request_count + client.request_count
            execution.truncated = True
            await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["request_count", "truncated"])
            await sync_to_async(SourceToolCall.objects.create, thread_sensitive=True)(
                source_execution=execution, tool_name=tool_name, error_type=exc.error_type,
                error_summary=str(exc)[:500],
            )
            raise
        except MCPSourceError as exc:
            if exc.rate_limited:
                await sync_to_async(_remember_source_rate_limit, thread_sensitive=True)(source, exc)
            execution.request_count = initial_request_count + client.request_count
            await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["request_count"])
            await sync_to_async(SourceToolCall.objects.create, thread_sensitive=True)(
                source_execution=execution, tool_name=tool_name, duration_ms=exc.duration_ms,
                error_summary=str(exc)[:500], error_type=exc.error_type, retry_count=exc.retry_count,
            )
            execution.retry_count += exc.retry_count
            await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["retry_count"])
            raise
        execution.request_count = initial_request_count + client.request_count
        await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["request_count"])
        await sync_to_async(SourceToolCall.objects.create, thread_sensitive=True)(
            source_execution=execution, tool_name=tool_name, duration_ms=result.duration_ms,
            result_count=len(_records(result.data)),
        )
        await sync_to_async(_record_tool_diagnostics, thread_sensitive=True)(execution.pk, source, tool_name, result.data)
        await sync_to_async(execution.refresh_from_db, thread_sensitive=True)(fields=["diagnostics"])
        cancelled = await sync_to_async(
            lambda: SearchJob.objects.filter(pk=job.pk, status=SearchJob.Status.CANCELLED).exists(),
            thread_sensitive=True,
        )()
        if cancelled:
            raise SearchCancelled
        return result

    async with source_session(source, enforce_rate_limit=True) as client:
        if source in SOURCE_ADAPTERS:
            return await _search_catalog_source(
                source, job, execution, SOURCE_ADAPTERS[source],
                client, invoke,
                source_budget, variants,
            )
        # Resolve a city/province location using the source's geocoding search when no local center exists.
        if source in {"balad", "neshan"} and scope_points and scope_points[0][1] is None:
            resolve_args = {"query": scope_points[0][0], "limit": 10}
            if source == "neshan":
                resolve_args["near"] = "Tehran"
            resolved = await invoke(client, geocode_tool, resolve_args)
            execution.request_count = initial_request_count + client.request_count
            await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["request_count"])
            wanted = normalize_text(scope_points[0][0])
            candidates = [r for r in _records(resolved.data) if _float_or_none(r.get("lat")) is not None and _float_or_none(r.get("lng")) is not None]
            location = next((r for r in candidates if normalize_text(str(r.get("name", ""))) == wanted), None)
            if not location:
                raise MCPSourceError(f"Could not resolve the {job.geographic_scope_type} location in {source}")
            scope_points = [(scope_points[0][0], (float(location["lat"]), float(location["lng"]))) ]
        per_location_budget = max(1, source_budget // max(1, len(scope_points)))
        map_checkpoint = dict(execution.checkpoint or {})
        first_area = max(0, int(map_checkpoint.get("area_index", 0)))
        first_variant = max(0, int(map_checkpoint.get("variant_index", 0)))
        record_offset = max(0, int(map_checkpoint.get("record_offset", 0)))
        for area_index in range(first_area, len(scope_points)):
            place_name, point = scope_points[area_index]
            if place_name not in execution.areas_checked:
                execution.areas_checked = [*execution.areas_checked, place_name]
                await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["areas_checked"])
            location_saved = 0
            variant_start = first_variant if area_index == first_area else 0
            for variant_index in range(variant_start, len(variants)):
                variant = variants[variant_index]
                if saved >= source_budget or location_saved >= per_location_budget:
                    break
                if source == "neshan":
                    near = place_name if _known_center(place_name) and job.geographic_scope_type != SearchJob.ScopeType.IRAN else f"{point[0]},{point[1]}"
                    args = {"query": variant, "near": near, "limit": min(30, max(1, per_location_budget - location_saved))}
                else:
                    args = {
                        "what": variant,
                        "lat": point[0],
                        "lng": point[1],
                        "radius_km": 20,
                        "limit": min(40, max(1, per_location_budget - location_saved)),
                    }
                args = _with_phone_filter(client, search_tool, args)
                if variant not in execution.query_variants:
                    execution.query_variants = [*execution.query_variants, variant]
                    await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["query_variants"])
                result = await invoke(client, search_tool, args)
                execution.request_count = initial_request_count + client.request_count
                execution.result_count += len(_records(result.data))
                await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["request_count", "result_count"])
                records = _records(result.data)
                resume_offset = None
                for record_index, record in enumerate(records):
                    if area_index == first_area and variant_index == first_variant and record_index < record_offset:
                        continue
                    if saved >= source_budget or location_saved >= per_location_budget:
                        resume_offset = record_index
                        break
                    identifier = _first(record, "id", "place_id", "token")
                    if not identifier or str(identifier) in processed_ids:
                        continue
                    processed_ids.add(str(identifier))
                    if not is_relevant_trade_record(job.trade_name, variants, record):
                        continue
                    detail_arg = "place_id" if source == "neshan" else "id"
                    if detail_rate_limited:
                        detail_data = {}
                    else:
                        try:
                            detail_data = await sync_to_async(_cached_source_detail, thread_sensitive=True)(source, identifier)
                            if detail_data is None:
                                detail = await invoke(client, detail_tool, {detail_arg: str(identifier)})
                                detail_data = detail.data
                                await sync_to_async(_store_source_detail, thread_sensitive=True)(source, identifier, detail_data)
                        except MCPSourceError as exc:
                            detail_data = {}
                            if source == "neshan" and re.search(r"returned no details|no details for this place", str(exc), re.IGNORECASE):
                                detail_warnings.append(f"{identifier}: جزئیات نشان موجود نبود؛ اطلاعات نتیجهٔ جست‌وجو استفاده شد.")
                                await sync_to_async(_store_source_detail, thread_sensitive=True)(source, identifier, {}, cache_empty=True)
                            elif exc.rate_limited:
                                detail_rate_limited = True
                                cooldown_until = await sync_to_async(_remember_source_rate_limit, thread_sensitive=True)(source, exc)
                                execution.error_type = exc.error_type if exc.error_type.endswith("quota_exceeded") else "long_cooldown" if exc.retry_after_seconds and exc.retry_after_seconds >= settings.SOURCE_RATE_LIMIT_LONG_THRESHOLD_SECONDS else "rate_limit"
                                execution.cooldown_until = cooldown_until
                                detail_warnings.append(f"{identifier}: {exc}")
                            else:
                                detail_errors.append(f"{identifier}: {exc}")
                                execution.error_count += 1
                            execution.error_details = "\n".join([*detail_errors, *detail_warnings])[-2000:]
                            await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["request_count", "error_count", "error_details"])
                    execution.request_count = initial_request_count + client.request_count
                    await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["request_count"])
                    raw_search_record = dict(record)
                    record["_source_raw"] = {
                        "search_response": result.data, "search_record": raw_search_record,
                        "detail_response": detail_data,
                    }
                    record["_phone_extraction_payload"] = {"search_record": raw_search_record, "detail": detail_data}
                    record["_searched_city"] = place_name
                    record["_query_variant"] = variant
                    lead, newly_qualified = await sync_to_async(save_lead, thread_sensitive=True)(job, source, record, detail_data, return_created=True)
                    await sync_to_async(execution.refresh_from_db, thread_sensitive=True)(fields=["diagnostics"])
                    if lead and newly_qualified:
                        saved += 1
                        location_saved += 1
                if resume_offset is not None:
                    execution.checkpoint = {"kind": "map", "area_index": area_index, "variant_index": variant_index, "record_offset": resume_offset}
                    execution.status = SourceExecution.Status.QUEUED
                    execution.completed_at = None
                    await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["checkpoint", "status", "completed_at"])
                    return saved
                if detail_rate_limited:
                    execution.checkpoint = {"kind": "map", "area_index": area_index, "variant_index": variant_index, "record_offset": len(records)}
                    break
                next_area, next_variant = area_index, variant_index + 1
                if next_variant >= len(variants):
                    next_area, next_variant = area_index + 1, 0
                execution.checkpoint = {"kind": "map", "area_index": next_area, "variant_index": next_variant, "record_offset": 0}
                await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["checkpoint"])
                if detail_rate_limited:
                    break
                if next_area < len(scope_points) or next_variant < len(variants):
                    execution.status = SourceExecution.Status.QUEUED
                    execution.completed_at = None
                    await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["status", "completed_at"])
                    return saved
                if detail_rate_limited:
                    break
            if saved >= source_budget:
                break
            if detail_rate_limited:
                break
    execution.status = SourceExecution.Status.PARTIAL if detail_errors else (
        SourceExecution.Status.LONG_COOLDOWN if execution.error_type == "long_cooldown" else
        SourceExecution.Status.RATE_LIMITED if detail_rate_limited else SourceExecution.Status.COMPLETED
    )
    execution.completed_at = timezone.now()
    await sync_to_async(execution.save, thread_sensitive=True)()
    return saved


def execute_source(source, job, execution):
    execution.status = SourceExecution.Status.RUNNING
    execution.started_at = timezone.now()
    execution.last_attempt_at = execution.started_at
    execution.save(update_fields=["status", "started_at", "last_attempt_at"])
    try:
        return asyncio.run(_search_source(source, job, execution))
    except SearchTargetReached:
        execution.status = SourceExecution.Status.COMPLETED
        execution.completed_at = timezone.now()
        execution.save(update_fields=["status", "completed_at"])
        return 0
    except SearchCancelled:
        execution.status = SourceExecution.Status.CANCELLED
        execution.completed_at = timezone.now()
        execution.error_details = "جست‌وجو به درخواست کاربر لغو شد؛ نتایج جمع‌آوری‌شده حفظ شدند."
        execution.save(update_fields=["status", "completed_at", "error_details", "request_count"])
        return 0
    except MCPBudgetExhausted as exc:
        execution.status = SourceExecution.Status.BUDGET_EXHAUSTED
        execution.error_type = exc.error_type
        execution.truncated = True
        execution.completed_at = timezone.now()
        execution.error_details = str(exc)
        execution.save(update_fields=["status", "error_type", "truncated", "completed_at", "error_details"])
        return 0
    except Exception as exc:
        logger.exception("Search source %s failed for job %s", source, job.pk)
        if isinstance(exc, MCPSourceError) and exc.rate_limited:
            cooldown_until = _remember_source_rate_limit(source, exc)
            execution.cooldown_until = cooldown_until
            execution.error_type = exc.error_type if exc.error_type.endswith("quota_exceeded") else "long_cooldown" if exc.retry_after_seconds and exc.retry_after_seconds >= settings.SOURCE_RATE_LIMIT_LONG_THRESHOLD_SECONDS else "rate_limit"
            execution.retry_count += exc.retry_count
            execution.status = SourceExecution.Status.LONG_COOLDOWN if execution.error_type == "long_cooldown" else SourceExecution.Status.RATE_LIMITED
        else:
            execution.error_type = getattr(exc, "error_type", "internal_error")
            execution.status = SourceExecution.Status.PARTIAL if execution.result_count else SourceExecution.Status.FAILED
        execution.completed_at = timezone.now()
        if execution.status in {SourceExecution.Status.PARTIAL, SourceExecution.Status.FAILED}:
            execution.error_count = max(1, execution.error_count)
        execution.error_details = str(exc)[:2000] if isinstance(exc, MCPSourceError) else f"Unexpected {type(exc).__name__}; see server logs."
        execution.save(update_fields=["status", "completed_at", "error_count", "error_details", "request_count", "error_type", "retry_count", "cooldown_until"])
        return 0
