"""
Request signing shared by both ends of the B2B link (this file is identical
in every software that carries the b2b app).

A signed request carries three headers:
    X-B2B-Client     the caller's COMPANY_NAME
    X-B2B-Timestamp  unix seconds when the request was signed
    X-B2B-Signature  hex HMAC-SHA256 of the canonical string below, keyed
                     with the secret shared between the two softwares

The secret itself never travels over the wire. The signature covers the
method, path, query string and body hash, so none of them can be altered
in flight, and the timestamp (checked against a short window by the
provider) stops old captures from being replayed.
"""

import hashlib
import hmac

HEADER_CLIENT = "X-B2B-Client"
HEADER_TIMESTAMP = "X-B2B-Timestamp"
HEADER_SIGNATURE = "X-B2B-Signature"


def _canonical(timestamp, method, path, query, body) -> bytes:
    body_digest = hashlib.sha256(body or b"").hexdigest()
    return "\n".join([str(timestamp), method.upper(), path, query, body_digest]).encode("utf-8")


def compute_signature(secret: str, *, timestamp, method: str, path: str, query: str, body: bytes = b"") -> str:
    return hmac.new(
        secret.encode("utf-8"),
        _canonical(timestamp, method, path, query, body),
        hashlib.sha256,
    ).hexdigest()


def signatures_match(expected: str, provided: str) -> bool:
    # Constant-time compare on bytes (str compare_digest raises on non-ASCII).
    return hmac.compare_digest(
        expected.encode("utf-8"),
        (provided or "").encode("utf-8", "ignore"),
    )
