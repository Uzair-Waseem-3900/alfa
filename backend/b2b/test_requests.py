import io
import json
from datetime import timedelta
import time
import uuid
from decimal import Decimal
from unittest.mock import patch
from urllib import error, parse

from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from billing.utils import calculate_line_item
from django.utils import timezone
from ledger.models import SupplierLedgerEntry
from purchases.models import Category, Inventory, Product, PurchaseOrder, Shelf, ShelfStock
from purchases.services import create_supplier

from . import client as b2b_client
from .models import PurchaseRequest, PurchaseRequestItem, SyncState
from .request_services import fit_shelves, run_catch_up
from .signing import compute_signature
from .tests import CONSUMER_ON, OWN_NAME, PROVIDER, REQUEST_URL, SECRET, FakeResponse, make_user

SUPPLIER_CODE = "APK-SUP"
DOORBELL_PATH = "/api/b2b/partner/purchase-requests/decided/"
LIST_URL = "/api/b2b/purchase-requests/"


class FakePartner:
    """Stands in for the partner's server: replaces b2b.client._open."""

    def __init__(self):
        self.calls = []
        self.submit_status = "pending"
        self.submit_error = None
        self.cancel_result = "cancelled"
        self.decisions = {}            # request_uuid -> {"status": ..., "items": [...]}
        self.search_rows = []
        self.rates_allowed = False
        self.fail = None               # exception raised for every call (offline partner)
        self.asleep = False            # only the readiness check fails (partner "sleeping")
        self.refuses = False           # readiness answers 404 (wrong secret / name)
        self.asleep_hosts = set()      # hosts whose readiness check fails (a second partner that sleeps)
        self.error_hosts = set()       # hosts whose submit fails after a successful readiness check
        self.refuse_code = 404

    def __call__(self, req, timeout):
        self.calls.append(req)
        if self.fail is not None:
            raise self.fail
        split = parse.urlsplit(req.full_url)
        path, method = split.path, req.get_method()
        if path.endswith("/ping/"):
            if self.asleep or split.netloc in self.asleep_hosts:
                raise error.URLError("still waking up")
            if self.refuses:
                raise error.HTTPError(req.full_url, self.refuse_code, "Refused", {}, None)
            return FakeResponse({"ok": True})
        if path.endswith("/products/"):
            return FakeResponse({
                "rates_allowed": self.rates_allowed, "count": len(self.search_rows), "total_pages": 1,
                "current_page": 1, "page_size": 25, "results": self.search_rows,
            })
        if path.endswith("/cancel/"):
            return FakeResponse({"status": self.cancel_result})
        if path.endswith("/decisions/"):
            wanted = parse.parse_qs(split.query)["uuids"][0].split(",")
            rows = [dict(self.decisions[u], request_uuid=u) for u in wanted if u in self.decisions]
            return FakeResponse({"count": len(rows), "results": rows})
        if path.endswith("/purchase-requests/") and method == "POST":
            if self.submit_error is not None:
                raise self.submit_error
            if split.netloc in self.error_hosts:
                raise error.URLError("dropped mid-send")
            return FakeResponse({"request_uuid": "x", "status": self.submit_status})
        raise AssertionError(f"unexpected call {method} {path}")

    def bodies(self):
        return [json.loads(c.data) for c in self.calls if c.data]

    def real_calls(self):
        """Every call except the readiness checks."""
        return [c for c in self.calls if not parse.urlsplit(c.full_url).path.endswith("/ping/")]


def accepted(*lines):
    return {"status": "accepted", "items": [
        {"product_code": code, "quantity": qty, "unit_price": price, "gst": gst, "wht": wht}
        for code, qty, price, gst, wht in lines
    ]}


@override_settings(**CONSUMER_ON, B2B_PARTNER_SUPPLIER_CODES={PROVIDER: SUPPLIER_CODE})
class RequestBase(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = make_user("admin@example.com", is_staff=True)
        self.api = APIClient()
        self.api.force_authenticate(self.admin)
        self.partner = FakePartner()
        patcher = patch.object(b2b_client, "_open", self.partner)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.category = Category.objects.create(name="Cat A")
        self.shelf_a = Shelf.objects.create(name="Shelf A")
        self.shelf_b = Shelf.objects.create(name="Shelf B")
        self.supplier = create_supplier(name="Alpha PK", code=SUPPLIER_CODE, user=self.admin)
        self.pen = Product.objects.create(name="Blue Pen", code="PEN-1", category=self.category)
        self.pad = Product.objects.create(name="Note Pad", code="PAD-2", category=self.category)

    def body(self, items=None, note=""):
        items = items or [{
            "product_id": self.pen.id, "quantity": 5, "discount": "10", "gst": "18", "wht": "1",
            "shelf_allocations": [
                {"shelf_id": self.shelf_a.id, "quantity": 3}, {"shelf_id": self.shelf_b.id, "quantity": 2},
            ],
        }]
        return {"provider": PROVIDER, "note": note, "items": items}

    def make_request(self, items=None):
        response = self.api.post(LIST_URL, self.body(items), format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return PurchaseRequest.objects.get(pk=response.json()["id"])

    def ring(self, request_uuid, *, secret=SECRET, client=PROVIDER, ts=None):
        body = json.dumps({"request_uuid": str(request_uuid)}).encode()
        ts = int(time.time()) if ts is None else ts
        sig = compute_signature(secret, timestamp=ts, method="POST", path=DOORBELL_PATH, query="", body=body)
        return APIClient().post(
            DOORBELL_PATH, data=body, content_type="application/json",
            HTTP_X_B2B_CLIENT=client, HTTP_X_B2B_TIMESTAMP=str(ts), HTTP_X_B2B_SIGNATURE=sig,
        )


class ProductSearchTests(RequestBase):
    def test_rows_are_marked_with_the_matching_local_product(self):
        self.partner.search_rows = [
            {"code": "PEN-1", "name": "  blue   pen ", "selling_price": None},     # same code + name (loosely)
            {"code": "PAD-2", "name": "Different Name", "selling_price": None},    # code matches, name does not
            {"code": "NEW-3", "name": "Not Here", "selling_price": None},          # not in this catalog
        ]
        body = self.api.get(f"/api/b2b/providers/{PROVIDER}/products/").json()
        flags = {r["code"]: (r["in_catalog"], r["local_product_id"]) for r in body["results"]}
        self.assertEqual(flags, {"PEN-1": (True, self.pen.id), "PAD-2": (False, None), "NEW-3": (False, None)})
        self.assertFalse(body["rates_allowed"])

    def test_price_is_passed_through_only_when_the_partner_sent_it(self):
        self.partner.rates_allowed = True
        self.partner.search_rows = [{"code": "PEN-1", "name": "Blue Pen", "selling_price": "12.5000"}]
        row = self.api.get(f"/api/b2b/providers/{PROVIDER}/products/").json()["results"][0]
        self.assertEqual(row["selling_price"], "12.5000")

    def test_one_local_query_for_the_whole_page_and_failures_are_clean(self):
        self.partner.search_rows = [{"code": f"C{i}", "name": "x", "selling_price": None} for i in range(20)]
        with CaptureQueriesContext(connection) as ctx:
            self.api.get(f"/api/b2b/providers/{PROVIDER}/products/")
        self.assertLessEqual(len(ctx), 2, [q["sql"] for q in ctx])
        self.partner.fail = error.URLError("down")
        self.assertEqual(self.api.get(f"/api/b2b/providers/{PROVIDER}/products/").status_code, 503)
        self.partner.fail = error.HTTPError("u", 404, "nf", {}, None)
        self.assertEqual(self.api.get(f"/api/b2b/providers/{PROVIDER}/products/").json()["status"], "not_configured")


class CreateTests(RequestBase):
    def test_saved_locally_sent_signed_and_shelves_never_leave(self):
        request = self.make_request()
        self.assertIsNotNone(request.sent_at)
        self.assertEqual(request.status, "pending")
        item = request.items.get()
        self.assertEqual(sorted(item.shelves.values_list("quantity", flat=True)), [2, 3])
        sent = self.partner.bodies()[0]
        self.assertEqual(sent["items"], [{
            "product_code": "PEN-1", "product_name": "Blue Pen", "quantity": 5,
            "discount": "10.0000", "gst": "18.00", "wht": "1.00",
        }])
        self.assertNotIn("shelf", json.dumps(sent).lower())

    def test_validation_failures_save_nothing_and_send_nothing(self):
        bad_sets = {
            "shelf total": [{"product_id": self.pen.id, "quantity": 5,
                             "shelf_allocations": [{"shelf_id": self.shelf_a.id, "quantity": 4}]}],
            "unknown product": [{"product_id": 99999, "quantity": 1,
                                 "shelf_allocations": [{"shelf_id": self.shelf_a.id, "quantity": 1}]}],
            "unknown shelf": [{"product_id": self.pen.id, "quantity": 1,
                               "shelf_allocations": [{"shelf_id": 99999, "quantity": 1}]}],
            "duplicate product": [
                {"product_id": self.pen.id, "quantity": 1, "shelf_allocations": [{"shelf_id": self.shelf_a.id, "quantity": 1}]},
                {"product_id": self.pen.id, "quantity": 1, "shelf_allocations": [{"shelf_id": self.shelf_a.id, "quantity": 1}]},
            ],
            "same shelf twice": [{"product_id": self.pen.id, "quantity": 2, "shelf_allocations": [
                {"shelf_id": self.shelf_a.id, "quantity": 1}, {"shelf_id": self.shelf_a.id, "quantity": 1}]}],
            "no items": [],
            "bad tax": [{"product_id": self.pen.id, "quantity": 1, "gst": "150",
                         "shelf_allocations": [{"shelf_id": self.shelf_a.id, "quantity": 1}]}],
        }
        for label, items in bad_sets.items():
            response = self.api.post(LIST_URL, {"provider": PROVIDER, "items": items}, format="json")
            self.assertEqual(response.status_code, 400, label)
        self.assertEqual(PurchaseRequest.objects.count(), 0)
        self.assertEqual(self.partner.calls, [])

    def test_unknown_provider_is_404(self):
        response = self.api.post(LIST_URL, dict(self.body(), provider="NOPE"), format="json")
        self.assertEqual(response.status_code, 404)

    def test_partner_refusal_shows_its_message_and_removes_the_local_row(self):
        refusal = error.HTTPError("u", 400, "bad", {}, io.BytesIO(json.dumps({"items": ["'PEN-1' is not available to request."]}).encode()))
        self.partner.submit_error = refusal
        response = self.api.post(LIST_URL, self.body(), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("not available", str(response.json()))
        self.assertEqual(PurchaseRequest.objects.count(), 0)
        self.assertEqual(PurchaseRequestItem.objects.count(), 0)

    def test_a_send_that_fails_after_a_successful_wake_check_stays_saved_and_catch_up_delivers_it(self):
        self.partner.submit_error = error.URLError("dropped mid-send")     # the readiness check passes, the send does not
        response = self.api.post(LIST_URL, self.body(), format="json")
        self.assertEqual(response.status_code, 201)
        self.assertIn("saved", response.json()["notice"])
        request = PurchaseRequest.objects.get()
        self.assertIsNone(request.sent_at)
        self.assertFalse(response.json()["delivered"])

        self.partner.submit_error = None
        self.assertGreaterEqual(run_catch_up(force=True), 1)
        request.refresh_from_db()
        self.assertIsNotNone(request.sent_at)
        sent = [b for b in self.partner.bodies() if b["request_uuid"] == str(request.request_uuid)]
        self.assertEqual(len(sent), 2)       # the failed attempt body + the retry: same request_uuid both times


class CancelTests(RequestBase):
    def test_cancel_when_the_partner_confirms(self):
        request = self.make_request()
        response = self.api.post(f"{LIST_URL}{request.id}/cancel/")
        self.assertEqual(response.status_code, 200)
        request.refresh_from_db()
        self.assertEqual(request.status, "cancelled")

    def test_partner_already_accepted_blocks_the_cancel_and_picks_up_the_decision(self):
        request = self.make_request()
        self.partner.cancel_result = "accepted"
        self.partner.decisions[str(request.request_uuid)] = accepted(("PEN-1", 5, "90.0000", "18.00", "1.00"))
        response = self.api.post(f"{LIST_URL}{request.id}/cancel/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("already decided", str(response.json()))
        request.refresh_from_db()
        self.assertEqual(request.status, "accepted")
        self.assertTrue(request.order_id)            # and the order was created straight away

    def test_unreachable_partner_leaves_it_pending_and_only_pending_can_cancel(self):
        request = self.make_request()
        self.partner.fail = error.URLError("down")
        self.assertEqual(self.api.post(f"{LIST_URL}{request.id}/cancel/").status_code, 409)
        request.refresh_from_db()
        self.assertEqual(request.status, "pending")
        self.partner.fail = None
        self.api.post(f"{LIST_URL}{request.id}/cancel/")
        self.assertEqual(self.api.post(f"{LIST_URL}{request.id}/cancel/").status_code, 400)


class DecisionAndImportTests(RequestBase):
    def decide(self, request, decision):
        self.partner.decisions[str(request.request_uuid)] = decision
        return self.ring(request.request_uuid)

    def test_accepted_creates_a_confirmed_order_stock_ledger_and_the_order_number(self):
        request = self.make_request()
        response = self.decide(request, accepted(("PEN-1", 4, "90.0000", "18.00", "1.00")))
        self.assertEqual(response.status_code, 200)

        request.refresh_from_db()
        order = request.order
        self.assertEqual(request.status, "accepted")
        self.assertEqual(order.status, "confirmed")
        self.assertEqual(order.order_number, request.order_number)
        self.assertEqual(order.supplier_id, self.supplier.id)
        self.assertEqual(order.created_by_id, self.admin.pk)           # attributed to who made the request
        self.assertEqual(order.payment_type, "after_delivery")
        line = order.items.get()
        self.assertEqual((line.quantity, line.unit_price, line.gst, line.wht), (4, Decimal("90"), Decimal("18"), Decimal("1")))
        self.assertEqual(order.net_payable, Decimal("90") * 4 * Decimal("1.17"))      # equals the partner's invoice total
        self.assertEqual(order.payable_outstanding, order.net_payable)
        self.assertTrue(SupplierLedgerEntry.objects.filter(purchase_order=order).exists())
        self.assertEqual(Inventory.objects.get(product=self.pen).quantity, 4)
        # requested 3+2 shelves, accepted 4 -> the LAST row is trimmed: A=3, B=1
        stock = {s.shelf.name: s.quantity for s in ShelfStock.objects.filter(product=self.pen)}
        self.assertEqual(stock, {"Shelf A": 3, "Shelf B": 1})
        self.assertEqual(request.items.get().accepted_quantity, 4)

    def test_increased_quantity_goes_to_the_last_shelf_and_zero_lines_are_skipped(self):
        items = [
            {"product_id": self.pen.id, "quantity": 5, "shelf_allocations": [{"shelf_id": self.shelf_a.id, "quantity": 3}, {"shelf_id": self.shelf_b.id, "quantity": 2}]},
            {"product_id": self.pad.id, "quantity": 2, "shelf_allocations": [{"shelf_id": self.shelf_a.id, "quantity": 2}]},
        ]
        request = self.make_request(items)
        self.decide(request, accepted(("PEN-1", 8, "100.0000", "0.00", "0.00")))     # PAD-2 absent => not supplied
        request.refresh_from_db()
        stock = {s.shelf.name: s.quantity for s in ShelfStock.objects.filter(product=self.pen)}
        self.assertEqual(stock, {"Shelf A": 3, "Shelf B": 5})
        self.assertEqual(request.order.items.count(), 1)
        self.assertEqual({i.product_code: i.accepted_quantity for i in request.items.all()}, {"PEN-1": 8, "PAD-2": 0})
        self.assertFalse(Inventory.objects.filter(product=self.pad, quantity__gt=0).exists())

    def test_the_doorbell_is_repeat_safe_so_only_one_order_is_ever_created(self):
        request = self.make_request()
        self.decide(request, accepted(("PEN-1", 5, "90.0000", "18.00", "1.00")))
        self.ring(request.request_uuid)
        self.ring(request.request_uuid)
        run_catch_up(force=True)
        self.assertEqual(PurchaseOrder.objects.count(), 1)
        self.assertEqual(Inventory.objects.get(product=self.pen).quantity, 5)

    def test_denied_and_remotely_cancelled_change_nothing_but_the_status(self):
        denied = self.make_request()
        self.decide(denied, {"status": "denied", "items": []})
        cancelled = self.make_request()
        self.decide(cancelled, {"status": "cancelled", "items": []})
        pending = self.make_request()
        self.decide(pending, {"status": "pending", "items": []})
        for obj, expected in ((denied, "denied"), (cancelled, "cancelled"), (pending, "pending")):
            obj.refresh_from_db()
            self.assertEqual(obj.status, expected)
            self.assertIsNone(obj.order_id)
        self.assertEqual(PurchaseOrder.objects.count(), 0)

    def test_missing_supplier_records_the_error_creates_nothing_and_is_retried(self):
        request = self.make_request()
        with override_settings(B2B_PARTNER_SUPPLIER_CODES={PROVIDER: "NO-SUCH"}):
            self.decide(request, accepted(("PEN-1", 5, "90.0000", "18.00", "1.00")))
        request.refresh_from_db()
        self.assertEqual(request.status, "accepted")
        self.assertIsNone(request.order_id)
        self.assertIn("NO-SUCH", request.import_error)
        self.assertEqual(PurchaseOrder.objects.count(), 0)          # rolled back: no draft left behind
        self.assertEqual(Inventory.objects.filter(quantity__gt=0).count(), 0)

        run_catch_up(force=True)                                    # the supplier code is right again
        request.refresh_from_db()
        self.assertTrue(request.order_id)
        self.assertEqual(request.import_error, "")

    def test_an_untrustworthy_answer_leaves_the_request_pending_with_the_reason(self):
        request = self.make_request()
        self.decide(request, accepted(("OTHER-9", 5, "90.0000", "18.00", "1.00")))
        request.refresh_from_db()
        self.assertEqual(request.status, "pending")
        self.assertIn("not on this request", request.import_error)
        self.decide(request, accepted(("PEN-1", "abc", "90.0000", "18.00", "1.00")))
        request.refresh_from_db()
        self.assertEqual((request.status, request.order_id), ("pending", None))

    def test_the_partners_taxes_win_if_they_differ_from_the_request(self):
        request = self.make_request()
        self.decide(request, accepted(("PEN-1", 5, "90.0000", "17.00", "0.50")))
        line = request.refresh_from_db() or request.order.items.get()
        self.assertEqual((line.gst, line.wht), (Decimal("17"), Decimal("0.5")))


class FitShelvesTests(TestCase):
    def test_fewer_units_come_off_the_last_rows_and_extra_go_on_the_last_row(self):
        self.assertEqual(fit_shelves([(1, 3), (2, 2)], 4), [(1, 3), (2, 1)])
        self.assertEqual(fit_shelves([(1, 3), (2, 2)], 2), [(1, 2)])
        self.assertEqual(fit_shelves([(1, 3), (2, 2)], 1), [(1, 1)])
        self.assertEqual(fit_shelves([(1, 3), (2, 2)], 5), [(1, 3), (2, 2)])
        self.assertEqual(fit_shelves([(1, 3), (2, 2)], 9), [(1, 3), (2, 6)])
        self.assertEqual(fit_shelves([(7, 4)], 6), [(7, 6)])


class DoorbellEndpointTests(RequestBase):
    def test_only_a_correctly_signed_known_partner_can_ring(self):
        request = self.make_request()
        self.assertEqual(APIClient().post(DOORBELL_PATH, {"request_uuid": str(request.request_uuid)}, format="json").status_code, 404)
        self.assertEqual(self.ring(request.request_uuid, secret="wrong").status_code, 404)
        self.assertEqual(self.ring(request.request_uuid, client="SOMEONE ELSE").status_code, 404)
        self.assertEqual(self.ring(request.request_uuid, ts=int(time.time()) - 3600).status_code, 404)
        self.assertEqual(self.ring(request.request_uuid).status_code, 200)

    def test_unknown_request_and_bad_uuid_are_harmless(self):
        self.assertEqual(self.ring(uuid.uuid4()).json(), {"ok": True})
        body = json.dumps({"request_uuid": "nope"}).encode()
        ts = int(time.time())
        sig = compute_signature(SECRET, timestamp=ts, method="POST", path=DOORBELL_PATH, query="", body=body)
        response = APIClient().post(
            DOORBELL_PATH, data=body, content_type="application/json",
            HTTP_X_B2B_CLIENT=PROVIDER, HTTP_X_B2B_TIMESTAMP=str(ts), HTTP_X_B2B_SIGNATURE=sig,
        )
        self.assertEqual(response.status_code, 400)

    def test_an_offline_partner_never_makes_the_doorbell_fail(self):
        request = self.make_request()
        self.partner.fail = error.URLError("down")
        self.assertEqual(self.ring(request.request_uuid).status_code, 200)
        request.refresh_from_db()
        self.assertEqual(request.status, "pending")

    @override_settings(B2B_CONSUMER_ENABLED=False)
    def test_switched_off_is_404(self):
        self.assertEqual(self.ring(uuid.uuid4()).status_code, 404)


class CatchUpTests(RequestBase):
    def test_nothing_outstanding_costs_one_query_and_never_calls_the_partner(self):
        with self.assertNumQueries(1):
            self.assertEqual(run_catch_up(), 0)
        self.assertEqual(self.partner.calls, [])

    def age(self, request, minutes):
        PurchaseRequest.objects.filter(pk=request.pk).update(sent_at=timezone.now() - timedelta(minutes=minutes))

    def test_a_fresh_pending_request_is_never_asked_about_unless_the_user_forces_it(self):
        request = self.make_request()                                # delivered a moment ago; the doorbell will tell us
        self.partner.decisions[str(request.request_uuid)] = {"status": "pending", "items": []}
        self.partner.calls.clear()
        self.assertEqual(run_catch_up(), 0)
        self.assertEqual(self.partner.calls, [])                     # no readiness check, nothing: we don't need the partner
        run_catch_up(force=True)                                     # "Check for Updates"
        self.assertTrue(any(c.full_url.split("?")[0].endswith("/decisions/") for c in self.partner.calls))

    def test_a_request_undecided_for_over_ten_minutes_is_asked_about_at_most_every_fifteen(self):
        request = self.make_request()
        self.partner.decisions[str(request.request_uuid)] = {"status": "pending", "items": []}
        self.age(request, 11)                                        # its doorbell should have arrived by now
        self.partner.calls.clear()
        run_catch_up()
        first_run = len(self.partner.calls)
        self.assertGreaterEqual(first_run, 2)                        # readiness check + the decision lookup
        run_catch_up()
        self.assertEqual(len(self.partner.calls), first_run)         # not again inside the 15 minutes
        SyncState.objects.update(last_checked_at=timezone.now() - timedelta(minutes=16))
        run_catch_up()
        self.assertGreater(len(self.partner.calls), first_run)       # 15 minutes later: once more
        self.assertIsNotNone(SyncState.objects.get(pk=2).last_checked_at)   # the "ask about a stale request" clock

    def test_importing_an_accepted_request_never_calls_the_partner(self):
        request = self.make_request()
        # The decision is already stored here (e.g. the process stopped before the import ran).
        PurchaseRequest.objects.filter(pk=request.pk).update(status="accepted", decided_at=timezone.now())
        PurchaseRequestItem.objects.filter(request=request).update(accepted_quantity=5, unit_price=Decimal("90"))
        self.partner.calls.clear()
        self.assertEqual(run_catch_up(), 1)
        request.refresh_from_db()
        self.assertTrue(request.order_id)
        self.assertEqual(self.partner.calls, [])                     # purely local: no readiness check, no call

    def test_a_failed_import_is_retried_only_on_force_not_on_every_catch_up(self):
        request = self.make_request()
        PurchaseRequest.objects.filter(pk=request.pk).update(
            status="accepted", decided_at=timezone.now(), import_error="supplier missing",
        )
        PurchaseRequestItem.objects.filter(request=request).update(accepted_quantity=5, unit_price=Decimal("90"))
        self.assertEqual(run_catch_up(), 0)                          # known failure: not re-run on every dashboard load
        self.assertEqual(run_catch_up(force=True), 1)                # "Check for Updates" / "Try Again" retries it

    def test_an_offline_partner_is_not_an_error(self):
        self.make_request()
        self.partner.fail = error.URLError("down")
        self.assertEqual(run_catch_up(force=True), 0)

    def test_switched_off_does_nothing(self):
        self.make_request()
        with override_settings(B2B_CONSUMER_ENABLED=False):
            self.assertEqual(run_catch_up(force=True), 0)

    def test_the_system_catch_up_endpoint_reports_the_b2b_phase(self):
        request = self.make_request()
        self.age(request, 11)                                        # long enough that a missed doorbell is suspected
        self.partner.decisions[str(request.request_uuid)] = accepted(("PEN-1", 5, "90.0000", "18.00", "1.00"))
        SyncState.objects.all().delete()
        response = self.api.get("/api/system/catch-up/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["b2b_error"])
        self.assertGreaterEqual(response.json()["b2b_requests_synced"], 1)
        request.refresh_from_db()
        self.assertTrue(request.order_id)


class ListAndPermissionTests(RequestBase):
    def test_list_detail_and_query_counts(self):
        for _ in range(12):
            self.make_request()
        with CaptureQueriesContext(connection) as ctx:
            body = self.api.get(LIST_URL + "?page_size=10").json()
        self.assertEqual((body["count"], len(body["results"])), (12, 10))
        self.assertLessEqual(len(ctx), 4, [q["sql"] for q in ctx])
        self.assertEqual(self.api.get(LIST_URL + "?status=accepted").json()["count"], 0)

        request = PurchaseRequest.objects.first()
        with CaptureQueriesContext(connection) as ctx:
            detail = self.api.get(f"{LIST_URL}{request.id}/").json()
        self.assertLessEqual(len(ctx), 5, [q["sql"] for q in ctx])
        self.assertEqual({s["shelf_name"] for s in detail["items"][0]["shelves"]}, {"Shelf A", "Shelf B"})

    def test_only_admin_or_superuser(self):
        request = self.make_request()
        normal = APIClient()
        normal.force_authenticate(make_user("normal@example.com", is_staff=False))
        self.assertEqual(APIClient().get(LIST_URL).status_code, 401)
        for response in (
            normal.get(LIST_URL), normal.post(LIST_URL, self.body(), format="json"),
            normal.get(f"{LIST_URL}{request.id}/"), normal.post(f"{LIST_URL}{request.id}/cancel/"),
            normal.post(f"{LIST_URL}sync/"), normal.get(f"/api/b2b/providers/{PROVIDER}/products/"),
        ):
            self.assertEqual(response.status_code, 403)

    def test_sync_button_forces_a_check(self):
        request = self.make_request()
        self.partner.decisions[str(request.request_uuid)] = {"status": "denied", "items": []}
        self.assertEqual(self.api.post(f"{LIST_URL}sync/").json()["updated"], 1)
        request.refresh_from_db()
        self.assertEqual(request.status, "denied")

    @override_settings(B2B_CONSUMER_ENABLED=False)
    def test_switched_off_is_404(self):
        self.assertEqual(self.api.get(LIST_URL).status_code, 404)


class AuditHardeningTests(RequestBase):
    def item(self, product, qty=2, shelf=None):
        return {
            "product_id": product.id, "quantity": qty,
            "shelf_allocations": [{"shelf_id": (shelf or self.shelf_a).id, "quantity": qty}],
        }

    def test_create_uses_the_same_number_of_queries_for_two_items_or_ten(self):
        def count(n):
            products = [Product.objects.create(name=f"P{n}-{i}", code=f"C{n}-{i}", category=self.category) for i in range(n)]
            with CaptureQueriesContext(connection) as ctx:
                response = self.api.post(LIST_URL, self.body([self.item(p) for p in products]), format="json")
            self.assertEqual(response.status_code, 201, response.content)
            return len(ctx)
        self.assertEqual(count(2), count(10))

    def test_a_repeated_form_submit_returns_the_same_request(self):
        request_uuid = str(uuid.uuid4())
        first = self.api.post(LIST_URL, dict(self.body(), request_uuid=request_uuid), format="json")
        second = self.api.post(LIST_URL, dict(self.body(), request_uuid=request_uuid), format="json")
        self.assertEqual((first.status_code, second.status_code), (201, 201))
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(PurchaseRequest.objects.count(), 1)
        submits = [c for c in self.partner.calls if c.get_method() == "POST"]
        self.assertEqual(len(submits), 1)                       # the partner was only asked once

    def test_hostile_decision_values_never_crash_and_never_import(self):
        hostile = [
            accepted(("PEN-1", -3, "90.0000", "18.00", "1.00")),
            accepted(("PEN-1", 5, "NaN", "18.00", "1.00")),
            accepted(("PEN-1", 5, "Infinity", "18.00", "1.00")),
            accepted(("PEN-1", 5, "90.0000", "150.00", "1.00")),
            accepted(("PEN-1", 5, "90.0000", "18.00", "-1.00")),
            accepted(("PEN-1", 5, "99999999999999999999", "18.00", "1.00")),
            accepted(("PEN-1", "5.0", "90.0000", "18.00", "1.00")),
        ]
        for decision in hostile:
            request = self.make_request()
            self.partner.decisions[str(request.request_uuid)] = decision
            self.assertEqual(self.ring(request.request_uuid).status_code, 200)
            request.refresh_from_db()
            self.assertEqual((request.status, request.order_id), ("pending", None), decision)
            self.assertTrue(request.import_error)
        self.assertEqual(PurchaseOrder.objects.count(), 0)

    def test_a_failure_midway_through_the_import_leaves_nothing_behind(self):
        request = self.make_request()
        Shelf.objects.filter(pk=self.shelf_b.pk).update(is_deleted=True)      # a shelf vanishes before the import
        self.partner.decisions[str(request.request_uuid)] = accepted(("PEN-1", 5, "90.0000", "18.00", "1.00"))
        self.ring(request.request_uuid)
        request.refresh_from_db()
        self.assertEqual(request.status, "accepted")
        self.assertIsNone(request.order_id)
        self.assertTrue(request.import_error)                                  # written AFTER the rollback
        self.assertEqual(PurchaseOrder.objects.count(), 0)                    # no draft order left behind
        self.assertFalse(SupplierLedgerEntry.objects.exists())
        self.assertFalse(Inventory.objects.filter(quantity__gt=0).exists())
        self.assertFalse(ShelfStock.objects.filter(quantity__gt=0).exists())

    def test_order_totals_equal_the_partners_invoice_maths_even_for_awkward_numbers(self):
        product = Product.objects.create(name="Bulk Item", code="BULK-1", category=self.category)
        request = self.make_request([{
            "product_id": product.id, "quantity": 123457, "discount": "0.0001", "gst": "17.5", "wht": "0.5",
            "shelf_allocations": [{"shelf_id": self.shelf_a.id, "quantity": 123457}],
        }])
        self.partner.decisions[str(request.request_uuid)] = accepted(("BULK-1", 123457, "33.3332", "17.50", "0.50"))
        self.ring(request.request_uuid)
        request.refresh_from_db()
        expected = calculate_line_item(
            quantity=123457, selling_price=Decimal("33.3333"), discount=Decimal("0.0001"),
            gst=Decimal("17.5"), wht=Decimal("0.5"),
        )
        self.assertEqual(request.order.net_payable, expected["line_total"])

    def test_catch_up_stops_at_the_first_dead_partner_call(self):
        self.partner.submit_error = error.URLError("dropped mid-send")
        for _ in range(3):
            self.api.post(LIST_URL, self.body(), format="json")               # three saved-but-unsent requests
        sends_before = len([c for c in self.partner.real_calls() if c.get_method() == "POST"])
        run_catch_up(force=True)
        sends_after = len([c for c in self.partner.real_calls() if c.get_method() == "POST"])
        self.assertEqual(sends_after - sends_before, 1)                       # one failed send, then it gave up

    def test_catch_up_asks_in_bounded_chunks(self):
        now = timezone.now()
        PurchaseRequest.objects.bulk_create([
            PurchaseRequest(provider_name=PROVIDER, created_by=self.admin, sent_at=now) for _ in range(105)
        ])
        run_catch_up(force=True)
        asked = [c for c in self.partner.calls if c.full_url.split("?")[0].endswith("/decisions/")]
        self.assertEqual(len(asked), 2)                                        # 100 + 5, never one giant query

    def test_the_idle_check_has_a_partial_index_for_outstanding_rows(self):
        names = {i.name for i in PurchaseRequest._meta.indexes}
        self.assertIn("b2b_my_req_outstanding_idx", names)

    def test_a_cancel_between_catch_up_loading_and_sending_is_respected(self):
        self.partner.submit_error = error.URLError("dropped mid-send")
        self.api.post(LIST_URL, self.body(), format="json")
        request = PurchaseRequest.objects.get()
        self.partner.submit_error = None
        PurchaseRequest.objects.filter(pk=request.pk).update(status="cancelled")      # cancelled just now
        submits_before = len([c for c in self.partner.calls if c.get_method() == "POST"])
        run_catch_up(force=True)
        self.assertEqual(len([c for c in self.partner.calls if c.get_method() == "POST"]), submits_before)


WRITE_VERBS = ("INSERT", "UPDATE", "DELETE")


def writes(ctx):
    return [q["sql"][:90] for q in ctx.captured_queries if q["sql"].lstrip().upper().startswith(WRITE_VERBS)]


class WakeGateTests(RequestBase):
    """A partner that does not answer its readiness check: nothing is written here, nothing else is sent."""

    def only_readiness_checks_were_made(self):
        self.assertEqual(self.partner.real_calls(), [])
        self.assertGreaterEqual(len(self.partner.calls), 1)       # it DID try the wake-up check

    def test_create_with_a_sleeping_partner_saves_nothing_and_sends_nothing(self):
        self.partner.asleep = True
        with CaptureQueriesContext(connection) as ctx:
            response = self.api.post(LIST_URL, self.body(), format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "partner_not_awake")
        self.assertIn("nothing was changed", response.json()["detail"])
        self.assertEqual(PurchaseRequest.objects.count(), 0)
        self.assertEqual(PurchaseRequestItem.objects.count(), 0)
        self.assertEqual(writes(ctx), [])
        self.only_readiness_checks_were_made()

    def test_cancel_with_a_sleeping_partner_changes_nothing(self):
        request = self.make_request()
        self.partner.asleep = True
        self.partner.calls.clear()
        with CaptureQueriesContext(connection) as ctx:
            response = self.api.post(f"{LIST_URL}{request.id}/cancel/")
        self.assertEqual(response.status_code, 409)
        request.refresh_from_db()
        self.assertEqual(request.status, "pending")
        self.assertEqual(writes(ctx), [])
        self.only_readiness_checks_were_made()

    def test_asking_for_rate_list_access_needs_the_partner_awake(self):
        self.partner.asleep = True
        with CaptureQueriesContext(connection) as ctx:
            response = self.api.post(REQUEST_URL)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(writes(ctx), [])
        self.only_readiness_checks_were_made()

    def test_catch_up_and_the_sync_button_do_nothing_when_the_partner_sleeps(self):
        request = self.make_request()
        PurchaseRequest.objects.filter(pk=request.pk).update(sent_at=None)      # an unsent one
        self.partner.asleep = True
        self.partner.calls.clear()
        self.assertEqual(run_catch_up(force=True), 0)
        body = self.api.post(f"{LIST_URL}sync/").json()
        self.assertEqual((body["updated"], body["partner_asleep"]), (0, True))
        request.refresh_from_db()
        self.assertIsNone(request.sent_at)
        self.only_readiness_checks_were_made()

    def test_the_doorbell_asks_only_for_the_one_decision_with_no_readiness_check_back(self):
        request = self.make_request()
        self.partner.decisions[str(request.request_uuid)] = accepted(("PEN-1", 5, "90.0000", "18.00", "1.00"))
        self.partner.calls.clear()
        self.assertEqual(self.ring(request.request_uuid).status_code, 200)
        paths = [c.full_url.split("?")[0].rsplit("/", 2)[-2] for c in self.partner.calls]
        self.assertEqual(paths, ["decisions"])                       # the partner just rang us: it is obviously awake
        request.refresh_from_db()
        self.assertTrue(request.order_id)

    def test_the_doorbell_changes_nothing_if_the_decision_cannot_be_fetched(self):
        request = self.make_request()
        self.partner.fail = error.URLError("went down right after ringing")
        self.assertEqual(self.ring(request.request_uuid).status_code, 200)
        request.refresh_from_db()
        self.assertEqual((request.status, request.order_id), ("pending", None))
        self.assertEqual(PurchaseOrder.objects.count(), 0)

    def test_a_partner_that_refuses_us_is_reported_as_not_configured_and_nothing_is_saved(self):
        self.partner.refuses = True
        response = self.api.post(LIST_URL, self.body(), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("did not accept this connection", str(response.json()))
        self.assertEqual(PurchaseRequest.objects.count(), 0)
        self.only_readiness_checks_were_made()

    def test_every_changing_operation_checks_first_and_goes_ahead_when_awake(self):
        request = self.make_request()                                          # create: check -> save -> send
        kinds = [(c.get_method(), parse.urlsplit(c.full_url).path.rsplit("/", 2)[-2]) for c in self.partner.calls]
        self.assertEqual(kinds[0], ("GET", "ping"))                           # the check is the FIRST thing sent
        self.partner.calls.clear()
        self.api.post(f"{LIST_URL}{request.id}/cancel/")                       # cancel: check -> cancel
        kinds = [(c.get_method(), parse.urlsplit(c.full_url).path.rsplit("/", 2)[-2]) for c in self.partner.calls]
        self.assertEqual(kinds[0], ("GET", "ping"))
        self.assertEqual(kinds[1][0], "POST")

    def test_the_wake_endpoint_reports_awake_asleep_and_not_configured(self):
        url = f"/api/b2b/providers/{PROVIDER}/wake/"
        self.assertEqual(self.api.post(url).json(), {"awake": True})
        self.partner.asleep = True
        self.assertEqual(self.api.post(url).json(), {"awake": False, "reason": "asleep", "detail": None})
        self.partner.asleep, self.partner.refuses = False, True
        body = self.api.post(url).json()
        self.assertEqual((body["awake"], body["reason"]), (False, "not_configured"))
        self.assertIn("did not accept", body["detail"])
        self.assertEqual(self.api.post("/api/b2b/providers/NOPE/wake/").status_code, 404)
        normal = APIClient()
        normal.force_authenticate(make_user("normal@example.com", is_staff=False))
        self.assertEqual(normal.post(url).status_code, 403)
        self.assertEqual(len(PurchaseRequest.objects.all()), 0)               # waking changes no data


class ReadinessEndpointTests(RequestBase):
    PING = "/api/b2b/partner/ping/"

    def signed_ping(self, secret=SECRET, client=PROVIDER):
        ts = int(time.time())
        sig = compute_signature(secret, timestamp=ts, method="GET", path=self.PING, query="", body=b"")
        return APIClient().get(
            self.PING, HTTP_X_B2B_CLIENT=client, HTTP_X_B2B_TIMESTAMP=str(ts), HTTP_X_B2B_SIGNATURE=sig,
        )

    def test_only_a_correctly_signed_known_partner_gets_200(self):
        self.assertEqual(self.signed_ping().json(), {"ok": True})
        self.assertEqual(APIClient().get(self.PING).status_code, 404)
        self.assertEqual(self.signed_ping(secret="wrong").status_code, 404)
        self.assertEqual(self.signed_ping(client="SOMEONE ELSE").status_code, 404)

    def test_a_broken_database_means_not_ready_and_switched_off_is_404(self):
        with patch("b2b.request_views.connection.cursor", side_effect=Exception("db down")):
            self.assertEqual(self.signed_ping().status_code, 503)
        with override_settings(B2B_CONSUMER_ENABLED=False):
            self.assertEqual(self.signed_ping().status_code, 404)


class AuditHardeningWakeTests(RequestBase):
    def test_a_401_or_403_on_the_readiness_check_also_means_not_configured_not_asleep(self):
        url = f"/api/b2b/providers/{PROVIDER}/wake/"
        for code in (401, 403, 404):
            self.partner.refuses, self.partner.refuse_code = True, code
            body = self.api.post(url).json()
            self.assertEqual((body["awake"], body["reason"]), (False, "not_configured"), code)

    def test_asleep_catch_up_writes_only_the_throttle_marker_and_pings_once_per_run(self):
        now = timezone.now()
        PurchaseRequest.objects.bulk_create([
            PurchaseRequest(provider_name=PROVIDER, created_by=self.admin, sent_at=now) for _ in range(105)
        ])
        self.partner.asleep = True
        self.partner.calls.clear()
        with CaptureQueriesContext(connection) as ctx:
            run_catch_up(force=True)
        self.assertEqual(len(self.partner.calls), 1)                 # one ping for the run, not one per chunk
        self.assertTrue(all("b2b_syncstate" in sql for sql in writes(ctx)), writes(ctx))

    def test_a_non_forced_catch_up_inside_the_minute_does_not_ping_again(self):
        request = self.make_request()
        PurchaseRequest.objects.filter(pk=request.pk).update(sent_at=None)      # undelivered: the one thing worth retrying
        self.partner.asleep = True
        run_catch_up(force=True)
        pings_after_first = len(self.partner.calls)
        run_catch_up()                                               # inside the 60s window
        self.assertEqual(len(self.partner.calls), pings_after_first)

    def test_the_sync_button_only_says_asleep_when_the_partner_really_is(self):
        self.make_request()
        self.partner.refuses = True
        body = self.api.post(f"{LIST_URL}sync/").json()
        self.assertEqual(body["partner_asleep"], False)              # refused is not "asleep"
        self.partner.refuses, self.partner.asleep = False, True
        self.assertEqual(self.api.post(f"{LIST_URL}sync/").json()["partner_asleep"], True)


TWO_PARTNERS = dict(
    B2B_PARTNER_BASE_URLS='{"%s": "https://alpha.example", "OTHER": "https://other.example"}' % PROVIDER,
    B2B_PARTNER_SECRETS='{"%s": "%s", "OTHER": "%s"}' % (PROVIDER, SECRET, SECRET),
)


class CatchUpCostAndFairnessTests(RequestBase):
    def raw_request(self, provider=PROVIDER, *, sent_minutes_ago=None):
        sent = None if sent_minutes_ago is None else timezone.now() - timedelta(minutes=sent_minutes_ago)
        return PurchaseRequest.objects.create(provider_name=provider, created_by=self.admin, sent_at=sent)

    def test_idle_fresh_pending_and_failed_imports_each_cost_exactly_one_query(self):
        with self.assertNumQueries(1):
            run_catch_up()                                           # idle
        self.raw_request(sent_minutes_ago=1)                         # fresh pending
        with self.assertNumQueries(1):
            run_catch_up()
        PurchaseRequest.objects.update(status="accepted", import_error="supplier missing")
        with self.assertNumQueries(1):
            run_catch_up()                                           # known failure, not retried without force

    def test_nine_minutes_is_not_stale_eleven_is(self):
        request = self.raw_request(sent_minutes_ago=9)
        self.partner.calls.clear()
        run_catch_up()
        self.assertEqual(self.partner.calls, [])
        PurchaseRequest.objects.filter(pk=request.pk).update(sent_at=timezone.now() - timedelta(minutes=11))
        run_catch_up()
        self.assertTrue(any(c.full_url.split("?")[0].endswith("/decisions/") for c in self.partner.calls))

    def test_retrying_unsent_requests_does_not_reset_the_stale_clock(self):
        self.raw_request(sent_minutes_ago=None)                      # unsent: retried every minute
        run_catch_up()
        self.assertIsNotNone(SyncState.objects.get(pk=1).last_checked_at)
        self.assertFalse(SyncState.objects.filter(pk=2).exists())    # nothing stale was asked, so that clock is untouched

    def test_the_unsent_retry_clock_is_60_seconds(self):
        request = self.raw_request(sent_minutes_ago=None)
        self.partner.submit_error = error.URLError("dropped mid-send")
        run_catch_up()
        sends = lambda: len([c for c in self.partner.real_calls() if c.get_method() == "POST"])
        first = sends()
        run_catch_up()
        self.assertEqual(sends(), first)                             # inside the minute: not again
        SyncState.objects.filter(pk=1).update(last_checked_at=timezone.now() - timedelta(seconds=61))
        run_catch_up()
        self.assertGreater(sends(), first)
        self.assertEqual(PurchaseRequest.objects.get(pk=request.pk).status, "pending")

    @override_settings(**TWO_PARTNERS, B2B_PARTNER_SUPPLIER_CODES={PROVIDER: SUPPLIER_CODE, "OTHER": SUPPLIER_CODE})
    def test_a_sleeping_partner_does_not_hold_up_another(self):
        sleeping = self.raw_request("OTHER", sent_minutes_ago=None)
        awake = self.raw_request(PROVIDER, sent_minutes_ago=None)
        self.partner.asleep_hosts = {"other.example"}
        run_catch_up(force=True)
        sleeping.refresh_from_db()
        awake.refresh_from_db()
        self.assertIsNone(sleeping.sent_at)                          # untouched
        self.assertIsNotNone(awake.sent_at)                          # went through

    @override_settings(**TWO_PARTNERS, B2B_PARTNER_SUPPLIER_CODES={PROVIDER: SUPPLIER_CODE, "OTHER": SUPPLIER_CODE})
    def test_one_partners_failed_send_does_not_stop_another_partners(self):
        failing = self.raw_request("OTHER", sent_minutes_ago=None)
        fine = self.raw_request(PROVIDER, sent_minutes_ago=None)
        self.partner.error_hosts = {"other.example"}
        run_catch_up(force=True)
        failing.refresh_from_db()
        fine.refresh_from_db()
        self.assertIsNone(failing.sent_at)
        self.assertIsNotNone(fine.sent_at)

    def test_only_a_bounded_number_of_local_imports_run_per_dashboard_load(self):
        for _ in range(13):
            request = self.make_request()
            PurchaseRequest.objects.filter(pk=request.pk).update(status="accepted", decided_at=timezone.now())
            PurchaseRequestItem.objects.filter(request=request).update(accepted_quantity=1, unit_price=Decimal("10"))
        self.assertEqual(run_catch_up(), 10)
        self.assertEqual(PurchaseRequest.objects.filter(order__isnull=True, status="accepted").count(), 3)
        self.assertEqual(run_catch_up(), 3)                          # the rest on the next load
