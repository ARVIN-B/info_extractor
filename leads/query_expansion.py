"""Bounded, validated query expansion with deterministic Persian fallbacks."""

import hashlib
import json
import logging
import re
from datetime import timedelta

import httpx
from django.conf import settings
from django.utils import timezone

from .models import BusinessLead, QueryExpansionCache
from .normalization import normalize_text

logger = logging.getLogger(__name__)

# Exact aliases intentionally favor precision. Add terms only when they describe
# substantially the same business category in common Iranian usage.
CATEGORY_TAXONOMY = {
    "technology": ["تکنولوژی", "فناوری", "فناوری اطلاعات", "it", "شرکت نرم افزاری", "نرم افزار", "شرکت فناوری"],
    "restaurant": ["رستوران", "غذاخوری", "کبابی", "رستوران ایرانی"],
    "cafe": ["کافه", "کافی شاپ", "قهوه فروشی"],
    "beauty_salon": ["آرایشگاه", "سالن زیبایی", "پیرایشگاه", "مرکز زیبایی"],
    "auto_repair": ["تعمیرگاه خودرو", "مکانیکی", "اتوسرویس", "خدمات خودرو"],
    "mobile_shop": ["موبایل فروشی", "فروشگاه موبایل", "فروشگاه تلفن همراه"],
    "bakery": ["نانوایی", "نان فانتزی", "نان فروشی"],
    "pastry": ["شیرینی فروشی", "قنادی", "شیرینی سرا"],
    "medical_equipment": ["تجهیزات پزشکی", "لوازم پزشکی", "کالای پزشکی"],
    "pharmacy": ["داروخانه", "دارو فروشی"],
    "real_estate": ["مشاور املاک", "املاک", "آژانس املاک"],
    "hotel": ["هتل", "مهمانپذیر", "اقامتگاه"],
    "supermarket": ["سوپرمارکت", "فروشگاه مواد غذایی", "خواربار فروشی"],
    "glass_shop": ["شیشه فروشی", "فروشگاه شیشه", "شیشه بری", "آینه و شیشه"],
}


def category_for_query(query):
    normalized = normalize_text(query)
    for key, aliases in CATEGORY_TAXONOMY.items():
        if normalized in {normalize_text(alias) for alias in aliases}:
            return {"key": key, "label": aliases[0], "aliases": aliases}
    return None


def _stored_category_for_query(query):
    """Also recognize exact source-reported category labels seen in past jobs."""
    normalized = normalize_text(query)
    if not normalized:
        return None
    labels = BusinessLead.objects.exclude(business_category="").values_list("business_category", flat=True).distinct()
    matches = list(dict.fromkeys(label.strip() for label in labels if normalize_text(label) == normalized and label.strip()))
    if not matches:
        return None
    return {"key": "stored_category", "label": matches[0], "aliases": matches}


def _clean_variants(original, values, maximum, minimum_relevance):
    seen = {normalize_text(original)}
    accepted, rejected = [], []
    if maximum <= 0:
        return accepted, rejected
    if not isinstance(values, list):
        return accepted, ["response_not_list"]
    for item in values:
        if isinstance(item, str):
            query, kind, relevance = item, "alternative", 0.7
        elif isinstance(item, dict):
            query = item.get("query")
            kind = item.get("type", "alternative")
            relevance = item.get("relevance", 0.0)
        else:
            rejected.append("invalid_item")
            continue
        if (not isinstance(query, str) or not 2 <= len(query.strip()) <= 100
                or not isinstance(relevance, (float, int)) or isinstance(relevance, bool)
                or not 0 <= relevance <= 1 or relevance < minimum_relevance
                or not re.fullmatch(r"[\w\s\u0600-\u06FF\u200c\-]+", query.strip(), re.UNICODE)):
            rejected.append("invalid_or_low_relevance")
            continue
        key = normalize_text(query)
        if not key or key in seen:
            rejected.append("duplicate_or_original")
            continue
        seen.add(key)
        accepted.append({"query": query.strip(), "type": str(kind)[:24], "relevance": float(relevance)})
        if len(accepted) >= maximum:
            break
    return accepted, rejected


def expand_query(query):
    """Return stable JSON-safe expansion metadata. LLM use is explicitly opt-in."""
    original = " ".join(str(query).split())[:120]
    category = category_for_query(original) or _stored_category_for_query(original)
    deterministic = []
    if category:
        deterministic = [
            {"query": alias, "type": "category_alias", "relevance": 1.0}
            for alias in category["aliases"] if normalize_text(alias) != normalize_text(original)
        ]
    else:
        from .sources import get_trade_variants
        deterministic = [
            {"query": term, "type": "synonym", "relevance": 0.9}
            for term in get_trade_variants(original) if normalize_text(term) != normalize_text(original)
        ]

    payload = {
        "original_query": original,
        "category": category,
        "variants": [],
        "provider": "deterministic",
        "model": "local-taxonomy",
        "success": True,
        "rejected": [],
    }
    max_variants = max(0, int(settings.SEARCH_QUERY_MAX_VARIANTS))
    minimum = float(settings.SEARCH_QUERY_MIN_RELEVANCE)
    cleaned, rejected = _clean_variants(original, deterministic, max_variants, minimum)
    payload["variants"] = cleaned
    payload["rejected"] = rejected

    if not settings.SEARCH_QUERY_LLM_ENABLED or not settings.SEARCH_QUERY_LLM_BASE_URL or not settings.SEARCH_QUERY_LLM_API_KEY:
        return payload

    endpoint = settings.SEARCH_QUERY_LLM_BASE_URL.rstrip("/") + "/chat/completions"
    cache_key = hashlib.sha256("|".join((
        normalize_text(original), endpoint, settings.SEARCH_QUERY_LLM_MODEL,
        str(max_variants), str(minimum), str(settings.SEARCH_QUERY_LLM_MAX_TOKENS),
        str(settings.SEARCH_QUERY_LLM_MAX_RETRIES),
    )).encode()).hexdigest()
    now = timezone.now()
    cached = QueryExpansionCache.objects.filter(cache_key=cache_key, expires_at__gt=now).first()
    if cached:
        return cached.payload
    last_error = None
    for _attempt in range(settings.SEARCH_QUERY_LLM_MAX_RETRIES + 1):
        try:
            response = httpx.post(
                endpoint,
                headers={"Authorization": f"Bearer {settings.SEARCH_QUERY_LLM_API_KEY}"},
                json={
                    "model": settings.SEARCH_QUERY_LLM_MODEL,
                    "temperature": 0,
                    "max_tokens": settings.SEARCH_QUERY_LLM_MAX_TOKENS,
                    "messages": [
                        {"role": "system", "content": "Return only JSON: {\"variants\":[{\"query\":string,\"type\":string,\"relevance\":number}]}. Suggest only close business-search synonyms in Persian or common English names. No MCP arguments."},
                        {"role": "user", "content": original},
                    ],
                },
                timeout=settings.SEARCH_QUERY_LLM_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            decoded = json.loads(content)
            llm_variants, rejected = _clean_variants(original, decoded.get("variants"), max_variants, minimum)
            merged, seen = [], {normalize_text(original)}
            # Local/category terms precede model-generated suggestions.
            for item in [*cleaned, *llm_variants]:
                key = normalize_text(item["query"])
                if key not in seen:
                    merged.append(item)
                    seen.add(key)
                if len(merged) >= max_variants:
                    break
            payload.update(variants=merged, provider="openai_compatible", model=settings.SEARCH_QUERY_LLM_MODEL,
                           success=True, rejected=[*payload["rejected"], *rejected])
            last_error = None
            break
        except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError) as exc:
            last_error = exc
    if last_error:
        logger.info("Query expansion fell back to deterministic terms: %s", type(last_error).__name__)
        payload.update(success=False, error=type(last_error).__name__)
    if settings.SEARCH_QUERY_CACHE_TTL_SECONDS > 0:
        QueryExpansionCache.objects.update_or_create(
            cache_key=cache_key,
            defaults={"payload": payload, "expires_at": now + timedelta(seconds=settings.SEARCH_QUERY_CACHE_TTL_SECONDS)},
        )
    return payload
