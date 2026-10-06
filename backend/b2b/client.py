"""
Signed, live calls to a provider software's b2b endpoints.

Nothing is cached and nothing is stored: every call goes to the provider so
the rate list is always its latest. Standard library only (no new dependency).

Failure modes are folded into three exceptions so the views can map them to
clear UI states without ever echoing provider internals back to the browser:
    ProviderNotConfigured  missing/invalid URL or secret, or http:// outside DEBUG
    ProviderRejected       the provider answered 404 (unknown name, wrong secret,
                           bad clock, or provider side switched off) — it
                           deliberately says nothing more
    ProviderUnreachable    timeout, connection error, 5xx, redirect, protocol
                           error, or a reply that is not the shape we expect
"""

import http.client
import json
import logging
import time
from urllib import error, parse
from urllib import request as urlrequest

from django.conf import settings
from django.views.decorators.debug import sensitive_variables

from . import config
from .signing import (
    HEADER_CLIENT, HEADER_SIGNATURE, HEADER_TIMESTAMP, compute_signature,
)

logger = logging.getLogger("b2b.client")

# A conformant page (<= 100 rows of code/name/price) is ~20KB; this leaves
# generous headroom while keeping a misbehaving partner cheap to reject.
MAX_RESPONSE_BYTES = 512_000
READ_CHUNK_BYTES = 16_384
REQUEST_PATH = "/api/b2b/partner/request/"
RATE_LIST_PATH = "/api/b2b/partner/rate-list/"
PRODUCTS_PATH = "/api/b2b/partner/products/"
PURCHASE_REQUESTS_PATH = "/api/b2b/partner/purchase-requests/"
DECISIONS_PATH = "/api/b2b/partner/purchase-requests/decisions/"
KNOWN_STATUSES = {"not_requested", "pending", "approved", "rejected", "revoked"}
REQUEST_STATUSES = {"pending", "accepted", "denied", "cancelled", "not_found"}


class ProviderError(Exception):
    pass


class ProviderNotConfigured(ProviderError):
    pass


class ProviderRejected(ProviderError):
    pass


class ProviderUnreachable(ProviderError):
    pass


class ProviderInvalid(ProviderError):
    """The partner answered 400: it understood us but refuses the request. `errors` is its own message."""

    def __init__(self, errors=None):
        super().__init__("The partner rejected the request.")
        self.errors = errors


class _NoRedirect(urlrequest.HTTPRedirectHandler):
    """Never follow a redirect — signed headers must only ever go to the configured host."""

    def redirect_request(self, *args, **kwargs):
        return None


_opener = urlrequest.build_opener(_NoRedirect)


def _open(req, timeout):
    # Single seam so tests can replace the network call.
    return _opener.open(req, timeout=timeout)


def _now() -> float:
    # Seam so tests can drive the deadline without patching the global clock.
    return time.monotonic()


def _read_capped(resp, timeout: float) -> bytes:
    """
    Reads the reply in chunks against ONE total deadline (urllib's own timeout
    is per socket operation, so a partner trickling bytes could otherwise hold
    a worker far longer than the configured timeout) and a hard size cap.
    """
    deadline = _now() + timeout
    chunks, total = [], 0
    while True:
        chunk = resp.read(READ_CHUNK_BYTES)
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > MAX_RESPONSE_BYTES or _now() > deadline:
            raise ProviderUnreachable() from None
        chunks.append(chunk)


# secret / signature / req must never appear in a traceback or debug page.
@sensitive_variables("secret", "signature", "req")
def _call(provider: str, method: str, path: str, params=None, body=None, statuses=None) -> dict:
    """
    One signed call. `body` is a dict sent as JSON (and signed). `statuses`, when
    given, is the set of values the reply's top-level "status" must be one of;
    when None the reply only has to be a JSON object (paginated lookups).
    """
    base = config.provider_base_urls().get(provider)
    secret = config.provider_secrets().get(provider)
    own_name = getattr(settings, "COMPANY_NAME", None)
    if not (base and secret and own_name):
        logger.error("b2b provider %r is not fully configured (URL, secret or COMPANY_NAME missing).", provider)
        raise ProviderNotConfigured()
    if not (own_name.isascii() and own_name.isprintable()):
        logger.error("b2b: COMPANY_NAME must be plain printable ASCII to be sent as a header.")
        raise ProviderNotConfigured()

    split = parse.urlsplit(base.strip())
    if split.scheme not in ("http", "https") or not split.netloc:
        logger.error("b2b provider %r has an invalid base URL.", provider)
        raise ProviderNotConfigured()
    if split.scheme != "https" and not settings.DEBUG:
        logger.error("b2b provider %r refused: http:// is only allowed when DEBUG is on.", provider)
        raise ProviderNotConfigured()

    query = parse.urlencode(sorted((params or {}).items()))
    full_path = split.path.rstrip("/") + path
    url = parse.urlunsplit((split.scheme, split.netloc, full_path, query, ""))
    if not (url.isascii() and url.isprintable()):
        logger.error("b2b provider %r base URL contains characters that cannot be sent.", provider)
        raise ProviderNotConfigured()

    payload = json.dumps(body, separators=(",", ":")).encode() if body is not None else b""
    timestamp = int(time.time())
    signature = compute_signature(
        secret, timestamp=timestamp, method=method, path=full_path, query=query, body=payload,
    )
    headers = {
        "Accept": "application/json",
        HEADER_CLIENT: own_name,
        HEADER_TIMESTAMP: str(timestamp),
        HEADER_SIGNATURE: signature,
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urlrequest.Request(
        url, data=payload if method == "POST" else None, method=method, headers=headers,
    )
    timeout = config.timeout_seconds()

    try:
        with _open(req, timeout) as resp:
            raw = _read_capped(resp, timeout)
    except ProviderError:
        raise
    except error.HTTPError as exc:
        code = exc.code
        detail = None
        if code == 400:
            try:
                detail = json.loads(_read_capped(exc, timeout))
            except (ValueError, OSError, http.client.HTTPException, ProviderError):
                detail = None
        exc.close()
        if code == 400:
            raise ProviderInvalid(detail) from None
        if code == 404:
            raise ProviderRejected() from None
        logger.warning("b2b provider %r answered HTTP %s", provider, code)
        raise ProviderUnreachable() from None
    except (error.URLError, OSError, TimeoutError, http.client.HTTPException, ValueError) as exc:
        logger.warning("b2b provider %r unreachable: %s", provider, type(exc).__name__)
        raise ProviderUnreachable() from None

    try:
        data = json.loads(raw)
    except ValueError:
        raise ProviderUnreachable() from None
    if not isinstance(data, dict):
        raise ProviderUnreachable()
    if statuses is not None:
        status = data.get("status")
        if not isinstance(status, str) or status not in statuses:
            raise ProviderUnreachable()
    return data


def request_access(provider: str) -> dict:
    """Ask the provider for (or re-ask for) rate-list access. Returns {'status': ...}."""
    return {"status": _call(provider, "POST", REQUEST_PATH, statuses=KNOWN_STATUSES)["status"]}


def fetch_rate_list(provider: str, *, search: str = "", page: int = 1, page_size: int = 25) -> dict:
    """
    One live call: the provider's status for us plus, only when approved, a page
    of rates. The reply is rebuilt field by field (and bounded to the page size
    we asked for) so nothing unexpected the provider might send can reach the
    browser.
    """
    params = {"page": page, "page_size": page_size}
    if search:
        params["search"] = search
    data = _call(provider, "GET", RATE_LIST_PATH, params, statuses=KNOWN_STATUSES)
    status = data["status"]
    try:
        rows = data.get("results", []) if status == "approved" else []
        results = [
            {
                "code": str(row["code"]),
                "name": str(row["name"]),
                "selling_price": str(row["selling_price"]),
            }
            for row in rows[:page_size]
        ]
        return {
            "status": status,
            "count": int(data.get("count", 0)),
            "total_pages": int(data.get("total_pages", 0)),
            "current_page": int(data.get("current_page", 1)),
            "page_size": int(data.get("page_size", page_size)),
            "results": results,
        }
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ProviderUnreachable() from None


# ---------------------------------------------------------------------------
# Purchase requests
# ---------------------------------------------------------------------------

def _clean_rows(rows, fields, limit):
    """Rebuilds each row with ONLY the expected keys, coerced to str, bounded to `limit`."""
    try:
        return [{key: (None if row[key] is None else str(row[key])) for key in fields} for row in rows[:limit]]
    except (KeyError, TypeError):
        raise ProviderUnreachable() from None


def search_products(provider: str, *, search: str = "", page: int = 1, page_size: int = 25) -> dict:
    """The partner's requestable products (priced only; code + name; price only if rates are allowed)."""
    params = {"page": page, "page_size": page_size}
    if search:
        params["search"] = search
    data = _call(provider, "GET", PRODUCTS_PATH, params)
    try:
        return {
            "rates_allowed": bool(data.get("rates_allowed")),
            "count": int(data.get("count", 0)),
            "total_pages": int(data.get("total_pages", 0)),
            "current_page": int(data.get("current_page", 1)),
            "page_size": int(data.get("page_size", page_size)),
            "results": _clean_rows(data.get("results", []), ("code", "name", "selling_price"), page_size),
        }
    except (TypeError, ValueError, OverflowError):
        raise ProviderUnreachable() from None


def submit_request(provider: str, payload: dict) -> str:
    """Sends a purchase request (safe to repeat for the same request_uuid). Returns the partner's status."""
    return _call(provider, "POST", PURCHASE_REQUESTS_PATH, body=payload, statuses=REQUEST_STATUSES)["status"]


def cancel_request(provider: str, request_uuid) -> str:
    """Asks the partner to cancel. Returns its status: 'cancelled', or why not ('accepted' / 'denied' / 'not_found')."""
    path = f"{PURCHASE_REQUESTS_PATH}{request_uuid}/cancel/"
    return _call(provider, "POST", path, statuses=REQUEST_STATUSES)["status"]


def fetch_decisions(provider: str, request_uuids) -> list:
    """
    The partner's current status for the given requests; accepted ones carry
    their lines [{product_code, quantity, unit_price, gst, wht}]. Rebuilt field by
    field so nothing else the partner might send is trusted.
    """
    uuids = [str(u) for u in request_uuids][:100]
    if not uuids:
        return []
    data = _call(provider, "GET", DECISIONS_PATH, {"uuids": ",".join(uuids), "page_size": 100})
    try:
        out = []
        for row in data.get("results", [])[:100]:
            status = row["status"]
            if status not in REQUEST_STATUSES:
                raise ProviderUnreachable()
            items = _clean_rows(
                row.get("items", []) if status == "accepted" else [],
                ("product_code", "quantity", "unit_price", "gst", "wht"), 100,
            )
            out.append({"request_uuid": str(row["request_uuid"]), "status": status, "items": items})
        return out
    except (KeyError, TypeError, AttributeError):
        raise ProviderUnreachable() from None
