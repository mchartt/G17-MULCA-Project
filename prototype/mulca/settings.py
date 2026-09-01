"""Minimal Django settings. Django's job in this prototype is exactly one
thing: SQLite-backed episodic memory persistence (BLUEPRINT.md §4.2) via the
ORM. It is not serving HTTP views."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "prototype-only-not-for-production"
DEBUG = True
ALLOWED_HOSTS: list = []

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "mulca.bot",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
