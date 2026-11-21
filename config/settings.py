import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def load_local_env():
    env_file = BASE_DIR / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip("\"'")
        os.environ.setdefault(key.strip(), value)


load_local_env()


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in {"1", "true", "yes", "on"}


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-change-me-before-deployment")
DEBUG = env_bool("DJANGO_DEBUG", True)
if not DEBUG and (
    SECRET_KEY == "dev-only-change-me-before-deployment" or len(SECRET_KEY) < 50
):
    raise RuntimeError(
        "Set DJANGO_SECRET_KEY to a long random value when DJANGO_DEBUG=False."
    )
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if host.strip()
]
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "leads.apps.LeadsConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("DATABASE_PATH", str(BASE_DIR / "db.sqlite3")),
        "OPTIONS": {"timeout": max(5, int(os.environ.get("SQLITE_BUSY_TIMEOUT", "60")))},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "fa"
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "search"
LOGOUT_REDIRECT_URL = "login"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)
SECURE_HSTS_SECONDS = int(
    os.environ.get("SECURE_HSTS_SECONDS", "31536000" if not DEBUG else "0")
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", not DEBUG)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", not DEBUG)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

CELERY_BROKER_URL = (
    os.environ.get("CELERY_BROKER_URL")
    or os.environ.get("REDIS_URL")
    # Chabokan's Celery guide uses BROKER_URL for its Redis connection string.
    or os.environ.get("BROKER_URL")
    or "redis://127.0.0.1:6379/0"
)
if CELERY_BROKER_URL.startswith("filesystem://"):
    # Local single-machine queue for development when Redis is not installed.
    CELERY_QUEUE_DIR = BASE_DIR / "var" / "celery-broker"
    CELERY_QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    CELERY_CONTROL_DIR = CELERY_QUEUE_DIR / "control"
    CELERY_CONTROL_DIR.mkdir(parents=True, exist_ok=True)
    CELERY_BROKER_TRANSPORT_OPTIONS = {
        "data_folder_in": str(CELERY_QUEUE_DIR),
        "data_folder_out": str(CELERY_QUEUE_DIR),
        "control_folder": str(CELERY_CONTROL_DIR),
    }
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 900
CELERY_TASK_SOFT_TIME_LIMIT = 840
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BEAT_SCHEDULE = {
    "recover-stale-search-jobs-every-five-minutes": {
        "task": "leads.recover_stale_search_jobs",
        "schedule": 300.0,
    },
    "purge-expired-source-payloads-daily": {
        "task": "leads.purge_expired_source_payloads",
        "schedule": 86400.0,
    },
}

SOURCE_TIMEOUT_SECONDS = int(os.environ.get("SOURCE_TIMEOUT_SECONDS", "45"))
SEARCH_MAX_CONTACTS = max(1, min(10000, int(os.environ.get("SEARCH_MAX_CONTACTS", "1000"))))
SEARXNG_BASE_URL = os.environ.get("SEARXNG_BASE_URL", "").rstrip("/")
SEARXNG_API_KEY = os.environ.get("SEARXNG_API_KEY", "")
SEARXNG_TIMEOUT = max(2, min(120, int(os.environ.get("SEARXNG_TIMEOUT", "30"))))
SEARXNG_LANGUAGE = os.environ.get("SEARXNG_LANGUAGE", "fa").strip() or "fa"
SEARXNG_ENABLED = env_bool("SEARXNG_ENABLED", env_bool("WEB_SEARCH_ENABLED", True))
SEARXNG_MAX_PAGES = max(1, min(20, int(os.environ.get("SEARXNG_MAX_PAGES", "5"))))
SEARXNG_MAX_QUERIES = max(1, min(10, int(os.environ.get("SEARXNG_MAX_QUERIES", "3"))))
SEARXNG_RETRIES = max(0, min(2, int(os.environ.get("SEARXNG_RETRIES", "1"))))
SEARXNG_VERIFY_TLS = env_bool("SEARXNG_VERIFY_TLS", True)
SEARXNG_CA_BUNDLE = os.environ.get("SEARXNG_CA_BUNDLE", "").strip()
FIRECRAWL_BASE_URL = os.environ.get("FIRECRAWL_BASE_URL", "").rstrip("/")
FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")
WEB_SEARCH_ENABLED = SEARXNG_ENABLED
WEB_SEARCH_MAX_RESULTS = max(1, min(100, int(os.environ.get("WEB_SEARCH_MAX_RESULTS", "100"))))
WEB_SEARCH_MAX_DOMAINS = max(1, min(30, int(os.environ.get("WEB_SEARCH_MAX_DOMAINS", "30"))))
WEB_CRAWL_MAX_PAGES_PER_DOMAIN = max(1, min(20, int(os.environ.get("WEB_CRAWL_MAX_PAGES_PER_DOMAIN", "8"))))
WEB_CRAWL_MAX_DEPTH = max(0, min(5, int(os.environ.get("WEB_CRAWL_MAX_DEPTH", "2"))))
WEB_CRAWL_TIMEOUT = max(5, min(300, int(os.environ.get("WEB_CRAWL_TIMEOUT", "60"))))
WEB_SEARCH_TIMEOUT = max(2, min(60, int(os.environ.get("WEB_SEARCH_TIMEOUT", "15"))))
WEB_CRAWL_CONCURRENCY = max(1, min(8, int(os.environ.get("WEB_CRAWL_CONCURRENCY", "1"))))
SOURCE_LOCK_WAIT_SECONDS = int(os.environ.get("SOURCE_LOCK_WAIT_SECONDS", "60"))
SEARCH_MAX_RESULTS = min(32767, max(1, int(os.environ.get("SEARCH_MAX_RESULTS", "5000"))))
SEARCH_MAX_PAGES_PER_SOURCE = max(1, int(os.environ.get("SEARCH_MAX_PAGES_PER_SOURCE", "500")))
SEARCH_PAGES_PER_BATCH = max(1, int(os.environ.get("SEARCH_PAGES_PER_BATCH", "1")))
SOURCE_MAX_CALLS_PER_JOB = int(os.environ.get("SOURCE_MAX_CALLS_PER_JOB", "500"))
SOURCE_MAX_CALLS_PER_BATCH = max(1, int(os.environ.get("SOURCE_MAX_CALLS_PER_BATCH", "500")))
MAX_MCP_CALLS_PER_JOB = int(os.environ.get("MAX_MCP_CALLS_PER_JOB", "4000"))
SEARCH_QUERY_LLM_ENABLED = env_bool("SEARCH_QUERY_LLM_ENABLED", False)
SEARCH_QUERY_LLM_BASE_URL = os.environ.get("SEARCH_QUERY_LLM_BASE_URL", "")
SEARCH_QUERY_LLM_API_KEY = os.environ.get("SEARCH_QUERY_LLM_API_KEY", "")
SEARCH_QUERY_LLM_MODEL = os.environ.get("SEARCH_QUERY_LLM_MODEL", "")
SEARCH_QUERY_LLM_TIMEOUT_SECONDS = min(60.0, max(1.0, float(os.environ.get("SEARCH_QUERY_LLM_TIMEOUT_SECONDS", "8"))))
SEARCH_QUERY_LLM_MAX_TOKENS = min(1024, max(16, int(os.environ.get("SEARCH_QUERY_LLM_MAX_TOKENS", "160"))))
SEARCH_QUERY_LLM_MAX_RETRIES = min(2, max(0, int(os.environ.get("SEARCH_QUERY_LLM_MAX_RETRIES", "0"))))
SEARCH_QUERY_MAX_VARIANTS = min(50, max(0, int(os.environ.get("SEARCH_QUERY_MAX_VARIANTS", "8"))))
SEARCH_QUERY_MIN_RELEVANCE = min(1.0, max(0.0, float(os.environ.get("SEARCH_QUERY_MIN_RELEVANCE", "0.72"))))
SEARCH_QUERY_CACHE_TTL_SECONDS = min(31536000, max(0, int(os.environ.get("SEARCH_QUERY_CACHE_TTL_SECONDS", "604800"))))
PHONE_EXTRACTION_MAX_DEPTH = max(1, min(32, int(os.environ.get("PHONE_EXTRACTION_MAX_DEPTH", "12"))))
PHONE_EXTRACTION_MAX_NODES = max(100, min(100000, int(os.environ.get("PHONE_EXTRACTION_MAX_NODES", "10000"))))
PHONE_EXTRACTION_MAX_STRING_CHARS = max(1000, min(1000000, int(os.environ.get("PHONE_EXTRACTION_MAX_STRING_CHARS", "20000"))))
SOURCE_RAW_RESPONSE_MAX_BYTES = max(1024, min(1048576, int(os.environ.get("SOURCE_RAW_RESPONSE_MAX_BYTES", "65536"))))
SOURCE_RAW_RESPONSE_RETENTION_DAYS = max(0, min(3650, int(os.environ.get("SOURCE_RAW_RESPONSE_RETENTION_DAYS", "90"))))
SOURCE_RATE_LIMIT_COOLDOWN_SECONDS = int(
    os.environ.get("SOURCE_RATE_LIMIT_COOLDOWN_SECONDS", "60")
)
SOURCE_RATE_LIMIT_DEFAULT_COOLDOWN_SECONDS = int(os.environ.get("SOURCE_RATE_LIMIT_DEFAULT_COOLDOWN_SECONDS", SOURCE_RATE_LIMIT_COOLDOWN_SECONDS))
SOURCE_RATE_LIMIT_MAX_INLINE_WAIT_SECONDS = int(os.environ.get("SOURCE_RATE_LIMIT_MAX_INLINE_WAIT_SECONDS", "5"))
SOURCE_RATE_LIMIT_MAX_RETRIES = int(os.environ.get("SOURCE_RATE_LIMIT_MAX_RETRIES", "1"))
SOURCE_RATE_LIMIT_JITTER = float(os.environ.get("SOURCE_RATE_LIMIT_JITTER", "1"))
SOURCE_RATE_LIMIT_LONG_THRESHOLD_SECONDS = int(os.environ.get("SOURCE_RATE_LIMIT_LONG_THRESHOLD_SECONDS", "3600"))
SOURCE_DAILY_QUOTA_COOLDOWN_SECONDS = int(os.environ.get("SOURCE_DAILY_QUOTA_COOLDOWN_SECONDS", "86400"))
SOURCE_MONTHLY_QUOTA_COOLDOWN_SECONDS = int(os.environ.get("SOURCE_MONTHLY_QUOTA_COOLDOWN_SECONDS", "2592000"))
BALAD_DETAIL_MIN_INTERVAL_SECONDS = float(
    os.environ.get("BALAD_DETAIL_MIN_INTERVAL_SECONDS", "6")
)
SOURCE_DETAIL_CACHE_TTL_SECONDS = int(
    os.environ.get("SOURCE_DETAIL_CACHE_TTL_SECONDS", "86400")
)
MCP_DISTRIBUTED_SOURCE_LIMITS = env_bool("MCP_DISTRIBUTED_SOURCE_LIMITS", not DEBUG)
ENABLED_MCP_SOURCES = [
    name.strip().lower()
    for name in os.environ.get("ENABLED_MCP_SOURCES", "neshan,balad,emalls").split(",")
    if name.strip().lower() in {"neshan", "balad", "emalls"}
]
import shutil

MCP_BIN_DIR = BASE_DIR / ".venv" / ("Scripts" if os.name == "nt" else "bin")


def resolve_mcp_executable(source, executable):
    # 1. Explicit path from environment variables
    env_name = f"{source.upper()}_MCP_EXECUTABLE"
    configured_path = os.environ.get(env_name)

    if configured_path:
        return configured_path

    # 2. Prefer project virtual environment
    venv_path = MCP_BIN_DIR / (f"{executable}.exe" if os.name == "nt" else executable)

    if venv_path.is_file():
        return str(venv_path)

    # 3. Fall back to system PATH
    system_path = shutil.which(executable)

    if system_path:
        return system_path

    # 4. Keep expected path for a useful error if not found
    return str(venv_path)


MCP_SERVER_PATHS = {
    source: resolve_mcp_executable(source, executable)
    for source, executable in {
        "neshan": "neshan-mcp",
        "balad": "balad-mcp",
        "emalls": "emalls-ir-mcp",
    }.items()
}
