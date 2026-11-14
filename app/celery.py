"""Compatibility entry point for hosts configured with ``celery -A app``.

The Django project package is ``config``; keep the canonical Celery instance
there and re-export it here for the Chabokan Supervisor example.
"""

from config.celery import app

__all__ = ("app",)
