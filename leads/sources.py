import asyncio
from difflib import SequenceMatcher
from datetime import timedelta
import json
import logging
import math
import re
from pathlib import Path

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .adapters import SOURCE_ADAPTERS
from .mcp_client import MCPSourceError, SOURCE_REGISTRY, source_session
from .models import BusinessLead, LeadEvidence, SearchJob, SourceExecution, SourcePlaceDetailCache, SourceRateLimit, SourceToolCall
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
    fair_share = math.ceil(max_results / max(1, selected_source_count))
    if completed_sources_before < selected_source_count - 1:
        return min(remaining_results, fair_share)
    return remaining_results


def _records(data):
    if isinstance(data, dict):
        for key in ("results", "places", "businesses", "items", "shops", "vendors", "companies", "offers", "products"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [data] if any(key in data for key in ("id", "place_id", "shop_id", "company_id", "name", "title")) else []
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
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(phone).strip() for phone in value if isinstance(phone, (str, int)) and str(phone).strip()]
    return []


def _field_values(search_record, detail):
    detail = detail if isinstance(detail, dict) else {}
    name = _first(detail, "name", "shop_name", "vendor_name", "company_name", "title") or _first(search_record, "name", "shop_name", "vendor_name", "company_name", "title", "maintext")
    address = _first(detail, "address", "formatted_address") or _first(search_record, "address", "subtext1")
    # A generic `url` on map records points to the provider's place page, not
    # necessarily the business website. Keep those URLs as provenance only.
    website = _first(detail, "website", "business_website", "official_website", "web")
    website = website or _first(search_record, "website", "business_website", "official_website", "web")
    detail_links = detail.get("links") if isinstance(detail.get("links"), dict) else {}
    search_links = search_record.get("links") if isinstance(search_record.get("links"), dict) else {}
    website = website or _first(detail_links, "website", "official_website", "web") or _first(search_links, "website", "official_website", "web")
    phones = _format_phone_values(_first(detail, "phones", "phone", "telephone"))
    phones += _format_phone_values(_first(search_record, "phones", "phone", "telephone"))
    phones = list(dict.fromkeys(phones))
    emails = _format_phone_values(_first(detail, "emails", "email", "contact_email"))
    emails += _format_phone_values(_first(search_record, "emails", "email", "contact_email"))
    emails = list(dict.fromkeys(email for email in emails if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)))
    socials = []
    for source_data in (detail, search_record):
        value = _first(source_data, "social_links", "socials", "instagram", "telegram", "linkedin")
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
        "emails": emails,
        "social_urls": socials,
        "website": str(website or "").strip(),
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


_SAFE_SOURCE_FIELDS = {
    "id", "place_id", "token", "shop_id", "vendor_id", "company_id", "national_id", "national_code",
    "name", "title", "maintext", "shop_name", "vendor_name", "company_name", "category", "business_category",
    "activity", "business_type", "company_type", "kind", "address", "formatted_address", "city", "province",
    "phone", "phones", "telephone", "email", "emails", "contact_email", "website", "web", "url", "profile_url",
    "source_url", "social_links", "socials", "instagram", "telegram", "linkedin", "lat", "latitude", "lng", "lon", "longitude",
}


def _safe_source_response(value):
    """Keep only business identity/contact/location fields; discard unrelated personal and listing data."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key not in _SAFE_SOURCE_FIELDS and key != "links":
                continue
            if key == "links" and isinstance(item, dict):
                item = {link_key: link for link_key, link in item.items() if link_key in {"web", "website", "instagram", "telegram", "linkedin"}}
            result[key] = _safe_source_response(item)
        return result
    if isinstance(value, list):
        return [_safe_source_response(item) for item in value[:20]]
    if isinstance(value, str):
        return value[:2000]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:2000]


def _cached_source_detail(source, record_id):
    ttl = settings.SOURCE_DETAIL_CACHE_TTL_SECONDS
    if ttl <= 0:
        return None
    cached = SourcePlaceDetailCache.objects.filter(
        source_name=source, source_record_id=str(record_id), expires_at__gt=timezone.now()
    ).first()
    return cached.detail_data if cached else None


@transaction.atomic
def _store_source_detail(source, record_id, detail):
    if not isinstance(detail, dict) or not detail:
        return
    safe_detail = _safe_source_response(detail)
    if not safe_detail:
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
    existing = next((lead for lead in current if lead.source_record_ids.get(source) == str(record_id)), None)
    if existing:
        return existing
    phones = {normalize_phone(phone) for phone in data["phones"] if normalize_phone(phone)}
    name = normalize_text(data["name"])
    address = normalize_text(data["address"])
    if not name:
        return None
    national_id = re.sub(r"\D", "", data.get("national_id", ""))
    website, domain = normalize_website(data["website"])
    for candidate in current.prefetch_related("evidence"):
        if national_id and candidate.national_id == national_id:
            return candidate
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
    record_id = _first(search_record, "_source_id", "id", "place_id", "token", "shop_id", "vendor_id", "company_id", "national_id") or _first(detail if isinstance(detail, dict) else {}, "id", "place_id", "token", "shop_id", "vendor_id", "company_id", "national_id")
    if not record_id:
        return None
    record_id = str(record_id)
    fields = _field_values(search_record, detail)
    if not fields["name"]:
        return None
    website, _ = normalize_website(fields["website"])
    valid_phones = [normalize_phone(phone) for phone in fields["phones"] if phone_is_valid(phone)]
    invalid_phone_values = [str(phone).strip() for phone in fields["phones"] if str(phone).strip() and not phone_is_valid(phone)]
    all_phone_values = list(dict.fromkeys(valid_phones))
    lead = _find_match(job, source, record_id, fields)
    source_ids = dict(lead.source_record_ids) if lead else {}
    source_ids[source] = record_id
    sources = list(dict.fromkeys((lead.source_names if lead else []) + [source]))
    address = lead.address if lead and lead.address else fields["address"]
    source_city = fields["city"] or str(search_record.get("_searched_city") or "")
    source_province = fields["province"] or CITY_PROVINCE.get(source_city, job.geographic_scope_name if job.geographic_scope_type == SearchJob.ScopeType.PROVINCE else "")
    phones = list(dict.fromkeys((lead.phone_numbers if lead else []) + all_phone_values))
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
    elif "phone" not in SOURCE_REGISTRY[source].get("fields", []):
        phone_status = BusinessLead.PhoneStatus.NOT_PROVIDED
    else:
        phone_status = BusinessLead.PhoneStatus.NOT_FOUND
    if phone_status == BusinessLead.PhoneStatus.CONFLICTING:
        status = BusinessLead.Verification.CONFLICTING
    if lead:
        lead.normalized_name = lead.normalized_name or normalize_text(fields["name"])
        lead.phone_numbers = phones
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
            province=source_province,
            website=website, business_category=fields["category"], latitude=_float_or_none(fields["lat"]),
            longitude=_float_or_none(fields["lng"]), source_names=sources, source_record_ids=source_ids,
            verification_status=status, emails=emails, social_urls=socials,
            national_id=re.sub(r"\D", "", fields["national_id"]), business_type=fields["business_type"] or SOURCE_REGISTRY[source].get("kind", ""), phone_status=phone_status,
        )
    lead.confidence_score = calculate_confidence(lead)
    lead.save(update_fields=["confidence_score"])
    raw = {"search": _safe_source_response(search_record), "details": _safe_source_response(detail)}
    values = {
        "name": fields["name"], "address": fields["address"], "phone_numbers": fields["phones"],
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
            validation_status = "format_valid_unverified" if all(phone_is_valid(phone) for phone in value) else "contains_invalid_format"
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
                "source_url": fields["profile_url"] or _source_url(source, record_id), "raw_response": raw,
                "normalized_value": json.dumps(normalized_value, ensure_ascii=False) if isinstance(normalized_value, (list, dict)) else str(normalized_value),
                "confidence_score": 0.8 if source in {"neshan", "balad", "emalls", "rasmio"} else 0.6,
                "validation_status": validation_status,
                "data_type": "public_business_contact" if field_name in {"phone_numbers", "emails", "website"} else ("company_registry" if source == "rasmio" else "public_business_data"),
            },
        )
    LeadEvidence.objects.create(
        business_lead=lead,
        source_name=source,
        source_record_id=record_id,
        field_name="raw_response",
        field_value="Original search and detail response",
        source_url=fields["profile_url"] or _source_url(source, record_id),
        raw_response=raw,
    )
    return lead


def _normalized_evidence_value(field_name, value):
    if field_name == "phone_numbers":
        return [normalize_phone(phone) or str(phone).strip() for phone in value]
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
    return state if state and state.cooldown_until > timezone.now() else None


def _remember_source_rate_limit(source, error):
    now = timezone.now()
    seconds = max(1, min(3600, error.retry_after_seconds or settings.SOURCE_RATE_LIMIT_COOLDOWN_SECONDS))
    cooldown_until = now + timedelta(seconds=seconds)
    state, _ = SourceRateLimit.objects.get_or_create(
        source_name=source,
        defaults={"cooldown_until": cooldown_until, "reason": "HTTP 429 rate limit"},
    )
    if state.cooldown_until < cooldown_until:
        state.cooldown_until = cooldown_until
    state.reason = "HTTP 429 rate limit"
    state.updated_at = now
    state.save(update_fields=["cooldown_until", "reason", "updated_at"])
    return state.cooldown_until


def source_skip_reason(trade_name, source):
    """Use source capabilities to avoid irrelevant catalog calls and expose why they were skipped."""
    query = normalize_text(trade_name)
    if source in {"neshan", "balad"}:
        return ""
    online = any(term in query for term in ("فروشگاه اینترنتی", "فروشگاه آنلاین", "آنلاین", "اینترنتی", "مارکت پلیس"))
    small_market = any(term in query for term in ("باسلام", "صنایع دستی", "خانگی", "دست ساز", "محصولات محلی"))
    company = any(term in query for term in ("شرکت", "سهامی", "حقوقی", "ثبت شده", "نرم افزار", "فناوری", "صنعتی", "تولیدی", "کارخانه"))
    if source == "emalls" and not online:
        return "این منبع برای فروشگاه‌های آنلاین/فروشگاهی مناسب است؛ در این جست‌وجو انتخاب نشد."
    if source == "basalam" and not (online or small_market):
        return "این منبع فروشندگان بازارگاه را پوشش می‌دهد و برای صنف واردشده تناسب کافی ندارد."
    if source == "rasmio" and not company:
        return "این منبع فقط برای کشف و تکمیل هویت شرکت‌های ثبت‌شده به‌کار می‌رود."
    return ""


async def _search_catalog_source(source, job, execution, adapter, client, invoke, source_budget, variants):
    city = job.geographic_scope_name if job.geographic_scope_type == SearchJob.ScopeType.CITY else ""
    province = job.geographic_scope_name if job.geographic_scope_type == SearchJob.ScopeType.PROVINCE else ""
    saved, errors = 0, []
    for variant in variants:
        if variant not in execution.query_variants:
            execution.query_variants = [*execution.query_variants, variant]
        area = city or province or "ایران"
        if area not in execution.areas_checked:
            execution.areas_checked = [*execution.areas_checked, area]
        await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["query_variants", "areas_checked"])
        try:
            discovery = await adapter.discover(
                client=client, invoke=invoke, query=variant, city=city, province=province,
                limit=source_budget - saved,
            )
            candidates = discovery.records
            execution.truncated = execution.truncated or discovery.truncated
        except MCPSourceError as exc:
            candidates = getattr(exc, "partial_records", [])
            execution.truncated = execution.truncated or getattr(exc, "truncated", False)
            errors.append(str(exc))
        for record, detail in candidates:
            if saved >= source_budget:
                break
            record = dict(record)
            actual_city = str(record.get("_source_city") or "").strip()
            actual_province = str(record.get("_source_province") or "").strip()
            if source == "basalam" and city and normalize_text(actual_city) != normalize_text(city):
                continue
            if source == "basalam" and province:
                found_province = actual_province or CITY_PROVINCE.get(actual_city, "")
                if normalize_text(found_province) != normalize_text(province):
                    continue
            record["_searched_city"] = actual_city or city or province
            if record.get("_source_id"):
                record.setdefault("id", record["_source_id"])
            lead = await sync_to_async(save_lead, thread_sensitive=True)(job, source, record, detail)
            if lead:
                saved += 1
        execution.result_count += len(candidates)
        await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["result_count"])
        if errors or saved >= source_budget:
            if saved >= source_budget:
                execution.truncated = True
            break
    if errors:
        execution.status = SourceExecution.Status.PARTIAL if execution.result_count else SourceExecution.Status.FAILED
        execution.error_count += len(errors)
        execution.error_details = "\n".join(errors)[-2000:]
    else:
        execution.status = SourceExecution.Status.COMPLETED
    execution.completed_at = timezone.now()
    await sync_to_async(execution.save, thread_sensitive=True)()
    return saved


async def _search_source(source, job, execution):
    config = SOURCE_REGISTRY[source]
    geocode_tool = config["tools"]["search"]
    search_tool = config["tools"].get("nearby", geocode_tool)
    detail_tool = config["tools"]["detail"]
    variants = get_trade_variants(job.trade_name)
    scope_points = get_scope_points(job)
    remaining = max(0, job.max_results - await sync_to_async(job.leads.count, thread_sensitive=True)())
    if remaining == 0:
        execution.status = SourceExecution.Status.COMPLETED
        execution.completed_at = timezone.now()
        await sync_to_async(execution.save, thread_sensitive=True)()
        return 0
    relevant_sources = [name for name in job.selected_sources if not source_skip_reason(job.trade_name, name)]
    relevant_source_count = max(1, len(relevant_sources))
    prior_executions = await sync_to_async(
        lambda: job.source_executions.filter(
            source_name__in=relevant_sources, status=SourceExecution.Status.COMPLETED
        ).exclude(source_name=source).count(), thread_sensitive=True
    )()
    source_budget = calculate_source_budget(job.max_results, relevant_source_count, remaining, prior_executions)
    processed_ids = set()
    saved = 0
    detail_errors = []
    detail_rate_limited = False

    cooldown = await sync_to_async(_active_source_cooldown, thread_sensitive=True)(source)
    if cooldown:
        execution.status = SourceExecution.Status.SKIPPED
        execution.error_count = max(1, execution.error_count)
        execution.error_details = f"منبع تا {timezone.localtime(cooldown.cooldown_until).strftime('%H:%M:%S')} به‌دلیل محدودیت نرخ موقتاً متوقف است؛ نتیجهٔ خالی محسوب نمی‌شود."
        execution.completed_at = timezone.now()
        await sync_to_async(execution.save, thread_sensitive=True)()
        return 0

    async def invoke(client, tool_name, arguments):
        job_calls = await sync_to_async(
            lambda: sum(job.source_executions.values_list("request_count", flat=True)), thread_sensitive=True
        )()
        if job_calls >= settings.MAX_MCP_CALLS_PER_JOB:
            execution.truncated = True
            await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["truncated"])
            raise MCPSourceError("Job reached its configured total MCP call budget; remaining coverage is truncated.")
        if client.request_count >= settings.SOURCE_MAX_CALLS_PER_JOB:
            execution.truncated = True
            await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["truncated"])
            raise MCPSourceError(f"{source} به سقف تعداد فراخوانی این Job رسید؛ ادامهٔ منبع truncation محسوب می‌شود.")
        try:
            result = await client.call(tool_name, arguments)
        except MCPSourceError as exc:
            if exc.rate_limited:
                await sync_to_async(_remember_source_rate_limit, thread_sensitive=True)(source, exc)
            execution.request_count = client.request_count
            await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["request_count"])
            await sync_to_async(SourceToolCall.objects.create, thread_sensitive=True)(
                source_execution=execution, tool_name=tool_name, duration_ms=exc.duration_ms,
                error_summary=str(exc)[:500]
            )
            raise
        execution.request_count = client.request_count
        await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["request_count"])
        await sync_to_async(SourceToolCall.objects.create, thread_sensitive=True)(
            source_execution=execution, tool_name=tool_name, duration_ms=result.duration_ms,
            result_count=len(_records(result.data)),
        )
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
            if place_name not in execution.areas_checked:
                execution.areas_checked = [*execution.areas_checked, place_name]
                await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["areas_checked"])
            location_saved = 0
            for variant in variants:
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
                if variant not in execution.query_variants:
                    execution.query_variants = [*execution.query_variants, variant]
                    await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["query_variants"])
                result = await invoke(client, search_tool, args)
                execution.request_count = client.request_count
                execution.result_count += len(_records(result.data))
                await sync_to_async(execution.save, thread_sensitive=True)(update_fields=["request_count", "result_count"])
                for record in _records(result.data):
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
                            detail_errors.append(f"{identifier}: {exc}")
                            if exc.rate_limited:
                                detail_rate_limited = True
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
                        execution.truncated = True
                        break
                if detail_rate_limited:
                    break
            if saved >= source_budget:
                execution.truncated = True
                break
            if detail_rate_limited:
                break
    execution.status = SourceExecution.Status.PARTIAL if detail_errors else SourceExecution.Status.COMPLETED
    execution.completed_at = timezone.now()
    await sync_to_async(execution.save, thread_sensitive=True)()
    return saved


def execute_source(source, job, execution):
    reason = source_skip_reason(job.trade_name, source)
    if reason:
        execution.status = SourceExecution.Status.SKIPPED
        execution.completed_at = timezone.now()
        execution.error_details = reason
        execution.save(update_fields=["status", "completed_at", "error_details"])
        return 0
    execution.status = SourceExecution.Status.RUNNING
    execution.started_at = timezone.now()
    execution.save(update_fields=["status", "started_at"])
    try:
        return asyncio.run(_search_source(source, job, execution))
    except Exception as exc:
        logger.exception("Search source %s failed for job %s", source, job.pk)
        if isinstance(exc, MCPSourceError) and exc.rate_limited:
            _remember_source_rate_limit(source, exc)
        execution.status = SourceExecution.Status.PARTIAL if execution.result_count else SourceExecution.Status.FAILED
        execution.completed_at = timezone.now()
        execution.error_count = max(1, execution.error_count)
        execution.error_details = str(exc)[:2000] if isinstance(exc, MCPSourceError) else f"Unexpected {type(exc).__name__}; see server logs."
        execution.save(update_fields=["status", "completed_at", "error_count", "error_details", "request_count"])
        return 0
