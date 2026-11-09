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
if not DEBUG and (SECRET_KEY == "dev-only-change-me-before-deployment" or len(SECRET_KEY) < 50):
    raise RuntimeError("Set DJANGO_SECRET_KEY to a long random value when DJANGO_DEBUG=False.")
ALLOWED_HOSTS = [host.strip() for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if host.strip()]
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if origin.strip()]

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
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {"default": {
    "ENGINE": "django.db.backends.sqlite3",
    "NAME": os.environ.get("DATABASE_PATH", str(BASE_DIR / "db.sqlite3")),
    "OPTIONS": {"timeout": 20},
}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
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
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "31536000" if not DEBUG else "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", not DEBUG)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", not DEBUG)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
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
}

SOURCE_TIMEOUT_SECONDS = int(os.environ.get("SOURCE_TIMEOUT_SECONDS", "45"))
SOURCE_LOCK_WAIT_SECONDS = int(os.environ.get("SOURCE_LOCK_WAIT_SECONDS", "60"))
MCP_DISTRIBUTED_SOURCE_LIMITS = env_bool("MCP_DISTRIBUTED_SOURCE_LIMITS", not DEBUG)
ENABLED_MCP_SOURCES = [
    name.strip().lower()
    for name in os.environ.get("ENABLED_MCP_SOURCES", "neshan,balad").split(",")
    if name.strip().lower() in {"neshan", "balad"}
]
MCP_BIN_DIR = BASE_DIR / ".venv" / ("Scripts" if os.name == "nt" else "bin")
MCP_SERVER_PATHS = {
    "neshan": str(MCP_BIN_DIR / ("neshan-mcp.exe" if os.name == "nt" else "neshan-mcp")),
    "balad": str(MCP_BIN_DIR / ("balad-mcp.exe" if os.name == "nt" else "balad-mcp")),
}
