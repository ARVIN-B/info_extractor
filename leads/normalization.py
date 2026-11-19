import json
import re
import unicodedata
from dataclasses import dataclass
from collections.abc import Mapping
from urllib.parse import urlparse

CHAR_TRANSLATION = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه"})
NUMBER_TRANSLATION = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
PHONE_RE = re.compile(r"(?:\+?98|0098|0)?(?:9\d{9}|[1-8]\d{2,10})$")
_PHONE_SEPARATOR = r"[\s().\-/–—]*"
_MOBILE_PATTERN = re.compile(
    rf"(?<![\w])(?P<number>(?:\+?98|0098){_PHONE_SEPARATOR}9(?:{_PHONE_SEPARATOR}\d){{9}}|0?9(?:{_PHONE_SEPARATOR}\d){{9}})(?![\w])"
)


@dataclass(frozen=True)
class MobileCandidate:
    raw_value: str
    normalized_number: str
    field_path: str
    contact_context: bool


def normalize_text(value):
    if not isinstance(value, str):
        return ""
    value = unicodedata.normalize("NFKC", value).translate(CHAR_TRANSLATION).translate(NUMBER_TRANSLATION)
    value = value.replace("\u200c", " ").replace("\u200f", "").replace("\u200e", "")
    value = re.sub(r"[\W_]+", " ", value, flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value).strip().casefold()
    value = re.sub(r"^(?:شرکت|موسسه|مؤسسه)\s+", "", value)
    value = re.sub(r"\s+(?:سهامی خاص|سهامی عام|با مسئولیت محدود|مسئولیت محدود|تعاونی|غیرتجاری)$", "", value)
    return value.strip()


def normalize_phone(value):
    """Normalize a complete Iranian telephone number to its national form."""
    original = str(value or "").translate(NUMBER_TRANSLATION)
    digits = re.sub(r"\D", "", original)
    if digits.startswith("0098"):
        digits = digits[4:]
    elif digits.startswith("98") and len(digits) in (12, 13):
        digits = digits[2:]
    if len(digits) == 10 and digits.startswith("9"):
        digits = "0" + digits
    if len(digits) == 11 and digits.startswith("0") and PHONE_RE.fullmatch(digits):
        return digits
    return ""


def normalize_iranian_mobile(value):
    """Return a valid Iranian mobile in canonical E.164 form or an empty string."""
    national = normalize_phone(value)
    return f"+98{national[1:]}" if national.startswith("09") else ""


def phone_is_valid(value):
    return bool(normalize_phone(value))


def _is_identifier_key(key):
    key = re.sub(r"[^a-z0-9]", "", str(key).casefold())
    return any(term in key for term in (
        "id", "identifier", "postal", "postcode", "zipcode", "tracking", "ordercode",
        "productcode", "nationalcode", "nationalid", "latitude", "longitude",
    ))


def _has_contact_context(path):
    return bool(re.search(r"phone|mobile|tel|contact|تماس|تلفن|موبایل|همراه", path, re.IGNORECASE))


def extract_iranian_mobiles(value, *, path="", max_depth=12, max_nodes=10000, max_text_chars=20000):
    """Recursively extract bounded, deduplicated Iranian mobile candidates from source data."""
    candidates = []
    seen_objects = set()
    visited_nodes = 0
    seen_values = set()

    def visit(item, current_path, depth, parent_key=""):
        nonlocal visited_nodes
        if depth > max_depth or visited_nodes >= max_nodes:
            return
        visited_nodes += 1
        if _is_identifier_key(parent_key):
            return
        if isinstance(item, str):
            text = item[:max_text_chars].translate(NUMBER_TRANSLATION)
            stripped = text.lstrip()
            if stripped.startswith(("{", "[")) and len(text) <= max_text_chars:
                try:
                    parsed = json.loads(text)
                except (TypeError, ValueError, json.JSONDecodeError):
                    parsed = None
                if isinstance(parsed, (dict, list)):
                    visit(parsed, current_path, depth + 1)
                    return
            for match in _MOBILE_PATTERN.finditer(text):
                raw = match.group("number")
                normalized = normalize_iranian_mobile(raw)
                key = (normalized, current_path, raw)
                if normalized and key not in seen_values:
                    seen_values.add(key)
                    candidates.append(MobileCandidate(raw, normalized, current_path or "$", _has_contact_context(current_path)))
            return
        if item is None or isinstance(item, (bool, float)):
            return
        if isinstance(item, int):
            visit(str(item), current_path, depth + 1, parent_key)
            return
        if isinstance(item, Mapping):
            object_id = id(item)
            if object_id in seen_objects:
                return
            seen_objects.add(object_id)
            for key, child in item.items():
                key = str(key)
                child_path = f"{current_path}.{key}" if current_path else key
                visit(child, child_path, depth + 1, key)
            return
        if isinstance(item, (list, tuple)):
            object_id = id(item)
            if object_id in seen_objects:
                return
            seen_objects.add(object_id)
            for index, child in enumerate(item):
                visit(child, f"{current_path}[{index}]", depth + 1, parent_key)
            return
        model_dump = getattr(item, "model_dump", None)
        if callable(model_dump):
            try:
                visit(model_dump(mode="json"), current_path, depth + 1, parent_key)
                return
            except Exception:
                pass
        try:
            attributes = vars(item)
        except (TypeError, AttributeError):
            return
        visit(attributes, current_path, depth + 1, parent_key)

    visit(value, path, 0)
    return candidates


def has_iranian_mobile(phones):
    """Return whether any phone is an Iranian mobile in any supported input form."""
    return any(normalize_iranian_mobile(phone) for phone in (phones or []))


def normalize_website(value):
    raw = str(value or "").strip()
    if not raw:
        return "", ""
    candidate = raw if "://" in raw else f"https://{raw}"
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or "." not in parsed.hostname:
        return "", ""
    domain = parsed.hostname.lower().removeprefix("www.")
    clean = f"https://{domain}"
    if parsed.path and parsed.path != "/":
        clean += parsed.path.rstrip("/")
    return clean, domain
