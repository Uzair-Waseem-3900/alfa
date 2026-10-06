"""
Authentication for the endpoint a partner software calls on THIS software (the
"doorbell"): a signed request from a known provider, never a user login.

Design goals (see the b2b plan):
  * Cheap for strangers. The signature check is pure CPU — an unknown or
    forged caller never touches the database.
  * Silent. Every failure is the same bare 404, so the endpoints give nothing
    away, and the caller's IP is logged (never the secret or signature).
  * Self-protecting. After too many failures from one IP, further requests
    from it are dropped before any HMAC work is done.
"""

import logging
import time

from django.core.cache import cache
from django.core.exceptions import SuspiciousOperation
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import NotFound
from rest_framework.throttling import BaseThrottle

from . import config
from .signing import (
    HEADER_CLIENT, HEADER_SIGNATURE, HEADER_TIMESTAMP,
    compute_signature, signatures_match,
)

logger = logging.getLogger("b2b.security")

# Used so a request naming an unknown partner costs the same HMAC work as a
# request naming a real one (no timing difference reveals which names exist).
_DUMMY_SECRET = "b2b-unknown-partner-placeholder"


class PartnerPrincipal:
    """Stands in for request.user on partner endpoints."""
    is_authenticated = True
    is_b2b_partner = True

    def __init__(self, partner_name: str):
        self.partner_name = partner_name
        # DRF's UserRateThrottle keys on user.pk — one bucket per partner.
        self.pk = f"b2b:{partner_name}"

    def __str__(self):
        return self.partner_name


def _failure_key(ip: str) -> str:
    return f"b2b:authfail:{ip}"


def _is_blocked(ip: str) -> bool:
    limit, _window = config.failed_auth_limit()
    return cache.get(_failure_key(ip), 0) >= limit


def _record_failure(ip: str) -> None:
    _limit, window = config.failed_auth_limit()
    key = _failure_key(ip)
    if cache.add(key, 1, window):
        return
    try:
        cache.incr(key)
    except ValueError:  # key expired between add() and incr()
        cache.set(key, 1, window)


class SignedPartnerAuthentication(BaseAuthentication):
    def authenticate(self, request):
        if not config.consumer_enabled():
            raise NotFound()

        ip = BaseThrottle().get_ident(request)
        if _is_blocked(ip):
            raise NotFound()

        client = request.headers.get(HEADER_CLIENT, "")
        timestamp = request.headers.get(HEADER_TIMESTAMP, "")
        signature = request.headers.get(HEADER_SIGNATURE, "")

        # An over-sized body must fail like every other bad request (same 404,
        # counted by the guard) instead of surfacing Django's own 400.
        try:
            body = request.body
        except SuspiciousOperation:
            body = None

        secret = config.provider_secrets().get(client)
        expected = compute_signature(
            secret or _DUMMY_SECRET,
            timestamp=timestamp,
            method=request.method,
            path=request.path,
            query=request.META.get("QUERY_STRING", ""),
            body=body or b"",
        )

        reason = None
        if body is None:
            reason = "oversize-body"
        elif not (client and timestamp and signature):
            reason = "missing-headers"
        elif not secret:
            reason = "unknown-partner"
        elif not self._fresh(timestamp):
            reason = "stale-timestamp"
        elif not signatures_match(expected, signature):
            reason = "bad-signature"

        if reason:
            _record_failure(ip)
            logger.warning("b2b auth failed ip=%s client=%.60r reason=%s", ip, client, reason)
            raise NotFound()

        return PartnerPrincipal(client), None

    @staticmethod
    def _fresh(timestamp: str) -> bool:
        try:
            sent_at = int(timestamp)
        except ValueError:
            return False
        return abs(time.time() - sent_at) <= config.signature_max_age_seconds()
