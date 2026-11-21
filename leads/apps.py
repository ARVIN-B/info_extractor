from django.apps import AppConfig
import logging


logger = logging.getLogger(__name__)


class LeadsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "leads"
    verbose_name = "سرنخ‌های کسب‌وکار"

    def ready(self):
        from django.db.backends.signals import connection_created

        connection_created.connect(configure_sqlite_connection, dispatch_uid="leads.configure_sqlite")


def configure_sqlite_connection(sender, connection, **kwargs):
    """Configure lock waiting and WAL for each SQLite connection."""
    if connection.vendor != "sqlite":
        return
    try:
        options = connection.settings_dict.get("OPTIONS", {})
        timeout_ms = max(1000, int(float(options.get("timeout", 60)) * 1000))
        from django.conf import settings

        mode = str(getattr(settings, "SQLITE_JOURNAL_MODE", "WAL")).upper()
        with connection.cursor() as cursor:
            cursor.execute(f"PRAGMA busy_timeout = {timeout_ms}")
            if mode in {"WAL", "DELETE", "TRUNCATE", "PERSIST", "MEMORY", "OFF"}:
                cursor.execute(f"PRAGMA journal_mode = {mode}")
                cursor.fetchone()
            cursor.execute("PRAGMA synchronous = NORMAL")
    except Exception:
        # Startup must remain available if the host filesystem does not support WAL.
        logger.warning("Could not apply optional SQLite concurrency pragmas", exc_info=True)
