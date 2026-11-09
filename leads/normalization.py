import re
import unicodedata
from urllib.parse import urlparse

CHAR_TRANSLATION = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه"})
NUMBER_TRANSLATION = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
PHONE_RE = re.compile(r"(?:\+?98|0098|0)?(?:9\d{9}|[1-8]\d{2,10})$")


def normalize_text(value):
    if not isinstance(value, str):
        return ""
    value = unicodedata.normalize("NFKC", value).translate(CHAR_TRANSLATION).translate(NUMBER_TRANSLATION)
    value = value.replace("\u200c", " ").replace("\u200f", "").replace("\u200e", "")
    value = re.sub(r"[\W_]+", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip().casefold()


def normalize_phone(value):
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


def phone_is_valid(value):
    return bool(normalize_phone(value))


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
