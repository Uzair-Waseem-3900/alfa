import http.client
import json
import socket
from unittest.mock import patch
from urllib import error, parse

from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from users.models import User

from . import client as b2b_client
from . import config as b2b_config
from .signing import (
    HEADER_CLIENT, HEADER_SIGNATURE, HEADER_TIMESTAMP, compute_signature,
)

PROVIDER = "ALPHA PROVIDER"
SECRET = "unit-test-shared-secret"
OWN_NAME = "ALFA TEST"

CONSUMER_ON = dict(
    B2B_CONSUMER_ENABLED=True,
    B2B_PARTNER_BASE_URLS='{"%s": "https://provider.example"}' % PROVIDER,
    B2B_PARTNER_SECRETS='{"%s": "%s"}' % (PROVIDER, SECRET),
    B2B_PARTNER_TIMEOUT_SECONDS=3,
    COMPANY_NAME=OWN_NAME,
)

LIST_URL = f"/api/b2b/providers/{PROVIDER}/rate-list/"
REQUEST_URL = f"/api/b2b/providers/{PROVIDER}/request/"


class FakeResponse:
    def __init__(self, payload=None, raw=None, error_after=None):
        self._raw = raw if raw is not None else json.dumps(payload).encode()
        self._pos = 0
        self._error_after = error_after   # raise this after the first chunk (truncated body etc.)

    def read(self, n=-1):
        if self._error_after is not None and self._pos > 0:
            raise self._error_after
        end = len(self._raw) if n is None or n < 0 else self._pos + n
        chunk = self._raw[self._pos:end]
        self._pos += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def rate_page(status="approved", rows=None, **extra):
    rows = rows if rows is not None else [{"code": "P1", "name": "Pen", "selling_price": "12.5000"}]
    return {
        "status": status, "count": len(rows), "total_pages": 1, "current_page": 1,
        "page_size": 25, "results": rows, **extra,
    }


def make_user(email, *, is_staff):
    return User.objects.create_user(
        email=email, password="Pass-word-1!", first_name="T", last_name="U", is_staff=is_staff,
    )


@override_settings(**CONSUMER_ON)
class B2BConsumerTestBase(TestCase):
    def setUp(self):
        self.admin_client = APIClient()
        self.admin_client.force_authenticate(make_user("admin@example.com", is_staff=True))


class PermissionAndSwitchTests(B2BConsumerTestBase):
    def test_only_admin_or_superuser(self):
        self.assertEqual(APIClient().get("/api/b2b/providers/").status_code, 401)
        normal = APIClient()
        normal.force_authenticate(make_user("normal@example.com", is_staff=False))
        for response in (
            normal.get("/api/b2b/providers/"),
            normal.get(LIST_URL),
            normal.post(REQUEST_URL),
        ):
            self.assertEqual(response.status_code, 403)

    @override_settings(B2B_CONSUMER_ENABLED=False)
    def test_switched_off_is_404(self):
        self.assertEqual(self.admin_client.get("/api/b2b/providers/").status_code, 404)
        self.assertEqual(self.admin_client.get(LIST_URL).status_code, 404)

    def test_provider_list_is_paginated_and_only_lists_fully_configured_ones(self):
        body = self.admin_client.get("/api/b2b/providers/").json()
        self.assertEqual(body["results"], [{"key": PROVIDER}])
        self.assertEqual(body["count"], 1)

    @override_settings(B2B_PARTNER_SECRETS="{}")
    def test_provider_without_a_secret_is_not_listed_and_is_404(self):
        self.assertEqual(self.admin_client.get("/api/b2b/providers/").json()["results"], [])
        self.assertEqual(self.admin_client.get(LIST_URL).status_code, 404)

    @override_settings(B2B_PARTNER_BASE_URLS="{broken")
    def test_malformed_env_means_no_providers_not_a_crash(self):
        self.assertEqual(self.admin_client.get("/api/b2b/providers/").json()["results"], [])

    def test_unknown_provider_key_is_404(self):
        self.assertEqual(self.admin_client.get("/api/b2b/providers/NOPE/rate-list/").status_code, 404)


class RateListProxyTests(B2BConsumerTestBase):
    def test_success_is_signed_and_rebuilt_field_by_field(self):
        payload = rate_page(rows=[{
            "code": "P1", "name": "Pen", "selling_price": "12.5000", "cost": "1", "secret": "x",
        }], injected="<script>")
        with patch.object(b2b_client, "_open", return_value=FakeResponse(payload)) as opened:
            response = self.admin_client.get(LIST_URL + "?search=pen&page=2&page_size=10")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "approved")
        self.assertEqual(body["results"], [{"code": "P1", "name": "Pen", "selling_price": "12.5000"}])
        self.assertNotIn("injected", body)

        req, timeout = opened.call_args.args
        self.assertEqual(timeout, 3)
        self.assertEqual(req.get_method(), "GET")
        split = parse.urlsplit(req.full_url)
        self.assertEqual(split.path, "/api/b2b/partner/rate-list/")
        self.assertEqual(split.query, "page=2&page_size=10&search=pen")
        headers = {k.lower(): v for k, v in req.header_items()}
        self.assertEqual(headers[HEADER_CLIENT.lower()], OWN_NAME)
        expected = compute_signature(
            SECRET, timestamp=headers[HEADER_TIMESTAMP.lower()], method="GET",
            path=split.path, query=split.query, body=b"",
        )
        self.assertEqual(headers[HEADER_SIGNATURE.lower()], expected)
        self.assertNotIn(SECRET, req.full_url)

    def test_non_approved_statuses_pass_through_with_no_rows(self):
        for status in ("pending", "rejected", "revoked", "not_requested"):
            payload = rate_page(status=status, rows=[])
            with patch.object(b2b_client, "_open", return_value=FakeResponse(payload)):
                body = self.admin_client.get(LIST_URL).json()
            self.assertEqual((body["status"], body["results"]), (status, []))

    def test_page_size_is_clamped_and_bad_page_defaults(self):
        with patch.object(b2b_client, "_open", return_value=FakeResponse(rate_page())) as opened:
            self.admin_client.get(LIST_URL + "?page_size=9999&page=abc")
        query = parse.urlsplit(opened.call_args.args[0].full_url).query
        self.assertEqual(query, "page=1&page_size=100")

    def test_provider_404_is_reported_as_not_configured_without_details(self):
        not_found = error.HTTPError("https://provider.example", 404, "Not Found", {}, None)
        with patch.object(b2b_client, "_open", side_effect=not_found):
            response = self.admin_client.get(LIST_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "not_configured")
        self.assertNotIn(SECRET, response.content.decode())

    def test_unreachable_cases_are_503(self):
        failures = [
            socket.timeout("slow"),
            error.URLError("refused"),
            error.HTTPError("https://provider.example", 500, "boom", {}, None),
            error.HTTPError("https://provider.example", 302, "redirect", {}, None),
        ]
        for failure in failures:
            with patch.object(b2b_client, "_open", side_effect=failure):
                self.assertEqual(self.admin_client.get(LIST_URL).status_code, 503, repr(failure))

    def test_malformed_replies_are_503(self):
        replies = [
            FakeResponse(raw=b"not json"),
            FakeResponse(payload=["a", "list"]),
            FakeResponse(payload={"status": "something-new"}),
            FakeResponse(payload=rate_page(rows=[{"code": "P1"}])),                 # row missing fields
            FakeResponse(raw=b"x" * (b2b_client.MAX_RESPONSE_BYTES + 5)),           # oversize
        ]
        for reply in replies:
            with patch.object(b2b_client, "_open", return_value=reply):
                self.assertEqual(self.admin_client.get(LIST_URL).status_code, 503)

    @override_settings(B2B_PARTNER_BASE_URLS='{"%s": "http://provider.example"}' % PROVIDER)
    def test_plain_http_is_refused_outside_debug_and_never_called(self):
        with patch.object(b2b_client, "_open") as opened:
            body = self.admin_client.get(LIST_URL).json()
        self.assertEqual(body["status"], "not_configured")
        opened.assert_not_called()

    @override_settings(B2B_PARTNER_BASE_URLS='{"%s": "http://localhost:8001/"}' % PROVIDER, DEBUG=True)
    def test_plain_http_is_allowed_in_debug_and_trailing_slash_is_handled(self):
        with patch.object(b2b_client, "_open", return_value=FakeResponse(rate_page())) as opened:
            self.assertEqual(self.admin_client.get(LIST_URL).status_code, 200)
        self.assertEqual(
            parse.urlsplit(opened.call_args.args[0].full_url).path, "/api/b2b/partner/rate-list/",
        )

    @override_settings(COMPANY_NAME=None)
    def test_missing_own_company_name_is_not_configured(self):
        with patch.object(b2b_client, "_open") as opened:
            self.assertEqual(self.admin_client.get(LIST_URL).json()["status"], "not_configured")
        opened.assert_not_called()

    def test_b2b_code_itself_runs_no_queries_and_stores_nothing(self):
        # force_authenticate skips the JWT user lookup (shared project overhead),
        # so this proves the b2b code adds no query of its own.
        with patch.object(b2b_client, "_open", return_value=FakeResponse(rate_page())):
            with self.assertNumQueries(0):
                self.admin_client.get(LIST_URL)

    def test_unusual_provider_replies_are_503_never_a_500(self):
        replies = [
            FakeResponse(payload={"status": []}),                                   # unhashable status
            FakeResponse(payload={"status": {}}),
            FakeResponse(payload=rate_page(count=1e999)),                           # inf count
            FakeResponse(raw=b'{"status": "approved", "count": 1e999, "results": []}'),
            FakeResponse(payload=rate_page(rows=[{"code": "P1", "name": "x", "selling_price": "1"}]),
                         error_after=http.client.IncompleteRead(b"")),              # truncated body
        ]
        for reply in replies:
            with patch.object(b2b_client, "_open", return_value=reply):
                self.assertEqual(self.admin_client.get(LIST_URL).status_code, 503)
        for failure in (http.client.BadStatusLine("x"), http.client.InvalidURL("x"), ValueError("x")):
            with patch.object(b2b_client, "_open", side_effect=failure):
                self.assertEqual(self.admin_client.get(LIST_URL).status_code, 503, repr(failure))

    def test_rows_beyond_the_requested_page_size_are_dropped(self):
        rows = [{"code": f"P{i}", "name": "n", "selling_price": "1"} for i in range(50)]
        with patch.object(b2b_client, "_open", return_value=FakeResponse(rate_page(rows=rows))):
            body = self.admin_client.get(LIST_URL + "?page_size=10").json()
        self.assertEqual(len(body["results"]), 10)

    def test_non_approved_status_never_relays_rows(self):
        leaked = rate_page(status="pending")
        with patch.object(b2b_client, "_open", return_value=FakeResponse(leaked)):
            self.assertEqual(self.admin_client.get(LIST_URL).json()["results"], [])

    def test_search_is_truncated_urlencoded_and_signed_as_sent(self):
        search = "café & pens " + "x" * 200
        with patch.object(b2b_client, "_open", return_value=FakeResponse(rate_page())) as opened:
            self.admin_client.get(LIST_URL, {"search": search})
        req = opened.call_args.args[0]
        split = parse.urlsplit(req.full_url)
        sent = dict(parse.parse_qsl(split.query))
        self.assertEqual(len(sent["search"]), 100)
        self.assertTrue(sent["search"].startswith("café & pens"))
        headers = {k.lower(): v for k, v in req.header_items()}
        expected = compute_signature(
            SECRET, timestamp=headers[HEADER_TIMESTAMP.lower()], method="GET",
            path=split.path, query=split.query, body=b"",
        )
        self.assertEqual(headers[HEADER_SIGNATURE.lower()], expected)

    def test_huge_page_number_is_clamped(self):
        with patch.object(b2b_client, "_open", return_value=FakeResponse(rate_page())) as opened:
            self.admin_client.get(LIST_URL + "?page=" + "9" * 400)
        query = dict(parse.parse_qsl(parse.urlsplit(opened.call_args.args[0].full_url).query))
        self.assertEqual(query["page"], "1000000")

    def test_slow_trickling_reply_hits_the_total_deadline(self):
        slow = FakeResponse(raw=b"x" * 100_000)
        with patch.object(b2b_client, "_open", return_value=slow), \
             patch.object(b2b_client, "_now", side_effect=[0, 0, 99, 99, 99]):
            self.assertEqual(self.admin_client.get(LIST_URL).status_code, 503)

    def test_secret_and_signature_never_reach_logs_or_error_bodies(self):
        failures = [error.URLError("down"), error.HTTPError("u", 404, "nf", {}, None), socket.timeout("t")]
        with self.assertLogs("b2b.client", level="WARNING") as captured:
            for failure in failures:
                with patch.object(b2b_client, "_open", side_effect=failure):
                    body = self.admin_client.get(LIST_URL).content.decode()
                    self.assertNotIn(SECRET, body)
            b2b_client.logger.warning("sentinel so assertLogs always has a record")
        self.assertNotIn(SECRET, "\n".join(captured.output))

    @override_settings(COMPANY_NAME="bad\nname")
    def test_unsendable_company_name_is_not_configured_not_a_500(self):
        with patch.object(b2b_client, "_open") as opened:
            self.assertEqual(self.admin_client.get(LIST_URL).json()["status"], "not_configured")
        opened.assert_not_called()

    def test_timeout_setting_is_clamped_and_parsed_safely(self):
        for raw, expected in (("inf", 10.0), ("300", 10.0), ("0", 0.5), ("abc", 3.0), ("2", 2.0)):
            with override_settings(B2B_PARTNER_TIMEOUT_SECONDS=raw):
                self.assertEqual(b2b_config.timeout_seconds(), expected, raw)


class RequestAccessTests(B2BConsumerTestBase):
    def test_request_posts_signed_empty_body_and_returns_status(self):
        # A fresh response per call: the readiness check and the real request each read their own body.
        with patch.object(b2b_client, "_open", side_effect=lambda req, timeout: FakeResponse({"status": "pending"})) as opened:
            response = self.admin_client.post(REQUEST_URL)
        self.assertEqual(response.json(), {"status": "pending"})
        req = opened.call_args.args[0]
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.data, b"")
        headers = {k.lower(): v for k, v in req.header_items()}
        expected = compute_signature(
            SECRET, timestamp=headers[HEADER_TIMESTAMP.lower()], method="POST",
            path="/api/b2b/partner/request/", query="", body=b"",
        )
        self.assertEqual(headers[HEADER_SIGNATURE.lower()], expected)

    def test_request_failures_map_like_the_list(self):
        not_found = error.HTTPError("https://provider.example", 404, "Not Found", {}, None)
        with patch.object(b2b_client, "_open", side_effect=not_found):
            self.assertEqual(self.admin_client.post(REQUEST_URL).json()["status"], "not_configured")
        with patch.object(b2b_client, "_open", side_effect=error.URLError("down")):
            response = self.admin_client.post(REQUEST_URL)       # the wake-up check fails first: 409, nothing sent
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "partner_not_awake")


class NoRedirectTests(SimpleTestCase):
    def test_redirects_are_never_followed(self):
        handler = b2b_client._NoRedirect()
        self.assertIsNone(handler.redirect_request(None, None, 302, "Found", {}, "https://elsewhere"))
