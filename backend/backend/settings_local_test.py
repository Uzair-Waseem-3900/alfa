# TEMPORARY local-only override — never point commands at a real database.
# Deleted right after use.
from .settings import *  # noqa

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
