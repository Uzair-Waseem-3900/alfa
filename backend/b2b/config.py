"""
Reads the B2B_* settings lazily (so tests can override them) and parses the
JSON-map env values defensively: a malformed value means "no providers", it
never crashes the process or leaks the value into a log line.
"""

import json
import logging
from functools import lru_cache
from types import MappingProxyType

from django.conf import settings

logger = logging.getLogger("b2b.config")


@lru_cache(maxsize=16)
def _parse_json_map(raw: str, label: str):
    if not raw or not raw.strip():
        return MappingProxyType({})
    try:
        data = json.loads(raw)
    except ValueError:
        logger.error("%s is not valid JSON; it is being ignored.", label)
        return MappingProxyType({})
    if not isinstance(data, dict):
        logger.error("%s must be a JSON object; it is being ignored.", label)
        return MappingProxyType({})
    return MappingProxyType({
        str(k): str(v) for k, v in data.items() if str(k).strip() and str(v).strip()
    })


def consumer_enabled() -> bool:
    return bool(getattr(settings, "B2B_CONSUMER_ENABLED", False))


def provider_base_urls():
    """{provider name: backend root URL} — read-only mapping."""
    return _parse_json_map(getattr(settings, "B2B_PARTNER_BASE_URLS", "") or "", "B2B_PARTNER_BASE_URLS")


def provider_secrets():
    """{provider name: shared secret} — read-only mapping."""
    return _parse_json_map(getattr(settings, "B2B_PARTNER_SECRETS", "") or "", "B2B_PARTNER_SECRETS")


def provider_names():
    """Providers that have BOTH a URL and a secret configured, in env order."""
    secrets = provider_secrets()
    return [name for name in provider_base_urls() if name in secrets]


def timeout_seconds() -> float:
    """Total time budget for one partner call, clamped to 0.5s..10s (a worker is pinned meanwhile)."""
    try:
        return min(10.0, max(0.5, float(getattr(settings, "B2B_PARTNER_TIMEOUT_SECONDS", 3))))
    except (TypeError, ValueError):
        return 3.0


# ---------------------------------------------------------------------------
# Purchase requests / doorbell
# ---------------------------------------------------------------------------

_UNITS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
MAX_REQUEST_ITEMS = 100
SYNC_MIN_INTERVAL_SECONDS = 60


def signature_max_age_seconds() -> int:
    try:
        return max(1, int(getattr(settings, "B2B_SIGNATURE_MAX_AGE_SECONDS", 60)))
    except (TypeError, ValueError):
        return 60


def failed_auth_limit():
    """Parses '10/hour' -> (10, 3600). Falls back to 10/hour when malformed."""
    raw = str(getattr(settings, "B2B_FAILED_AUTH_LIMIT", "10/hour"))
    try:
        count, unit = raw.split("/", 1)
        return max(1, int(count)), _UNITS[unit.strip().lower()]
    except (ValueError, KeyError):
        return 10, 3600


def supplier_code_for(provider: str) -> str:
    """The supplier record that stands for this provider on purchase orders ('' when not set)."""
    codes = getattr(settings, "B2B_PARTNER_SUPPLIER_CODES", {}) or {}
    return (codes.get(provider) or "").strip()
