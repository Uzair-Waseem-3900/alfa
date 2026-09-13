from datetime import date, datetime, time
from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from billing.models import Invoice
from billing.services import (
    accept_return, confirm_invoice, create_customer, create_invoice,
    create_return, set_invoice_item_shelf_allocations,
    set_return_item_shelf_allocations,
)
from purchases.models import Category, LostInventoryRecord, Product, Shelf
from purchases.services import (
    accept_purchase_return, confirm_purchase_order, create_lost_inventory_record,
    create_purchase_order, create_purchase_return, create_supplier,
    set_purchase_item_shelf_allocations, set_purchase_return_item_shelf_allocations,
)
from rates.services import create_rate
from users.models import User

from .views import (
    InvoicesReportView, InventoryValuationReportView, LostInventoryReportView,
    StockMovementReportView,
)


def make_admin(email="admin@example.com"):
    return User.objects.create_user(
        email=email, password="Adm1n-secret!", first_name="Admin",
        last_name="User", is_staff=True,
    )


class ReportsTestBase(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.admin = make_admin()
        self.category = Category.objects.create(name="Cat A")
        self.shelf = Shelf.objects.create(name="Shelf A")
        self.supplier = create_supplier(name="Ali Traders", code="ALI", user=self.admin)
        self.customer = create_customer(name="Big Mart", code="BM", address="Main St", user=self.admin)

    def make_stocked_product(self, code="P001", name="Product 1", *, stock=10):
        product = Product.objects.create(
            name=name, code=code, category=self.category,
        )
        create_rate(product_id=product.id, selling_price=Decimal("100"), user=self.admin)
        order = create_purchase_order(
            supplier_id=self.supplier.id,
            items=[{"product_id": product.id, "quantity": stock, "unit_price": Decimal("50")}],
            user=self.admin,
        )
        for item in order.items.all():
            set_purchase_item_shelf_allocations(
                purchase_item_id=item.id,
                allocations=[{"shelf_id": self.shelf.id, "quantity": item.quantity}],
                user=self.admin,
            )
        confirm_purchase_order(order_id=order.id, user=self.admin)
        return product

    def make_confirmed_invoice(self, product, quantity=2, *, confirmed_on=None):
        invoice = create_invoice(
            customer_id=self.customer.id,
            items=[{"product_id": product.id, "quantity": quantity}],
            user=self.admin,
        )
        for item in invoice.items.all():
            set_invoice_item_shelf_allocations(
                invoice_item_id=item.id,
                allocations=[{"shelf_id": self.shelf.id, "quantity": item.quantity}],
                user=self.admin,
            )
        invoice = confirm_invoice(invoice_id=invoice.id, user=self.admin)
        if confirmed_on is not None:
            aware = timezone.make_aware(datetime.combine(confirmed_on, time(12, 0)))
            Invoice.objects.filter(pk=invoice.pk).update(confirmed_at=aware)
            invoice.refresh_from_db()
        return invoice


class InventoryValuationAvgCostTests(ReportsTestBase):
    """
    avg_unit_cost: Inventory.avg_unit_cost, a frozen moving-average updated
    only by purchases (fixed 2026-09-14). total_value: the TRUE live FIFO
    valuation (reverted 2026-09-14 after making it WAC-derived broke the
    Balance Sheet's reconciliation with FIFO-based COGS-at-sale — see
    get_inventory_valuation_report_data's docstring). The two figures agree
    only when a product's true remaining-batch cost hasn't drifted from its
    average — see test_total_value_diverges_from_avg_cost_after_a_return
    for the case where they don't.
    """

    def test_moving_average_across_two_purchases_at_different_costs(self):
        from purchases.models import Inventory
        from reports.selectors import get_inventory_valuation_report_data

        product = self.make_stocked_product(stock=10)  # unit_cost=50 -> avg=50
        # Second purchase at a different cost — same product, new PO.
        order = create_purchase_order(
            supplier_id=self.supplier.id,
            items=[{"product_id": product.id, "quantity": 10, "unit_price": Decimal("70")}],
            user=self.admin,
        )
        for item in order.items.all():
            set_purchase_item_shelf_allocations(
                purchase_item_id=item.id,
                allocations=[{"shelf_id": self.shelf.id, "quantity": item.quantity}],
                user=self.admin,
            )
        confirm_purchase_order(order_id=order.id, user=self.admin)

        # (10*50 + 10*70) / 20 = 60
        inv = Inventory.objects.get(product=product)
        self.assertEqual(inv.avg_unit_cost, Decimal("60.0000"))

        rows = get_inventory_valuation_report_data()
        row = next(r for r in rows if r["product_id"] == product.id)
        self.assertEqual(row["avg_unit_cost"], Decimal("60.0000"))
        # No depletion has happened yet, so both batches are still fully
        # intact — true FIFO total_value and avg*qty coincide here (this is
        # NOT a guaranteed identity in general, see the divergence test below).
        self.assertEqual(row["total_value"], Decimal("1200.0000"))
        self.assertEqual(row["total_value"], row["quantity_on_hand"] * row["avg_unit_cost"])

    def test_total_value_diverges_from_avg_cost_after_a_return(self):
        """
        Proves total_value is the true live FIFO valuation, NOT
        avg_unit_cost * quantity_on_hand — the exact scenario that broke the
        Balance Sheet when total_value was briefly WAC-derived (2026-09-14).
        """
        from purchases.models import Inventory
        from reports.selectors import get_inventory_valuation_report_data

        product = self.make_stocked_product(stock=10)  # unit_cost=50 -> batch A
        order_a = product.purchase_items.select_related("order").first().order
        order_b = create_purchase_order(
            supplier_id=self.supplier.id,
            items=[{"product_id": product.id, "quantity": 10, "unit_price": Decimal("70")}],
            user=self.admin,
        )
        for item in order_b.items.all():
            set_purchase_item_shelf_allocations(
                purchase_item_id=item.id,
                allocations=[{"shelf_id": self.shelf.id, "quantity": item.quantity}],
                user=self.admin,
            )
        confirm_purchase_order(order_id=order_b.id, user=self.admin)
        # avg = 60, qty = 20, true total_value = 10*50 + 10*70 = 1200

        # Return 4 units from batch A (cost 50) — avg_unit_cost stays 60,
        # but the TRUE remaining value drops by exactly 4*50=200.
        item_a = order_a.items.first()
        ret = create_purchase_return(
            order_id=order_a.id,
            items=[{"purchase_item_id": item_a.id, "quantity": 4}],
            user=self.admin,
        )
        for return_item in ret.items.all():
            set_purchase_return_item_shelf_allocations(
                return_item_id=return_item.id,
                allocations=[{"shelf_id": self.shelf.id, "quantity": return_item.quantity}],
                user=self.admin,
            )
        accept_purchase_return(return_id=ret.id, user=self.admin)

        inv = Inventory.objects.get(product=product)
        self.assertEqual(inv.avg_unit_cost, Decimal("60.0000"))  # frozen, unchanged
        self.assertEqual(inv.quantity, 16)

        row = next(r for r in get_inventory_valuation_report_data() if r["product_id"] == product.id)
        self.assertEqual(row["avg_unit_cost"], Decimal("60.0000"))
        self.assertEqual(row["total_value"], Decimal("1000.0000"))  # 6*50 + 10*70, true FIFO
        # The identity does NOT hold here — proves total_value is genuinely
        # independent of avg_unit_cost, not silently derived from it.
        self.assertNotEqual(row["total_value"], row["quantity_on_hand"] * row["avg_unit_cost"])

    def test_report_query_count_flat_regardless_of_batch_count(self):
        product = self.make_stocked_product(stock=5)
        view = InventoryValuationReportView.as_view()

        def count():
            request = self.factory.get("/reports/inventory-valuation/")
            force_authenticate(request, user=self.admin)
            with CaptureQueriesContext(connection) as ctx:
                response = view(request)
                response.render()
            self.assertEqual(response.status_code, 200)
            return len(ctx.captured_queries)

        baseline = count()
        for i in range(4):
            order = create_purchase_order(
                supplier_id=self.supplier.id,
                items=[{"product_id": product.id, "quantity": 5, "unit_price": Decimal(f"{50 + i}")}],
                user=self.admin,
            )
            for item in order.items.all():
                set_purchase_item_shelf_allocations(
                    purchase_item_id=item.id,
                    allocations=[{"shelf_id": self.shelf.id, "quantity": item.quantity}],
                    user=self.admin,
                )
            confirm_purchase_order(order_id=order.id, user=self.admin)
        grown = count()
        self.assertEqual(baseline, grown)


class BackfillInventoryAvgCostTests(ReportsTestBase):
    def test_backfill_reconstructs_from_history_and_is_idempotent(self):
        from django.core.management import call_command
        from purchases.models import Inventory

        product = self.make_stocked_product(stock=10)  # unit_cost=50
        # Field defaults to 0 until the backfill runs, even though a real
        # purchase already happened — simulates upgrading pre-existing data.
        Inventory.objects.filter(product=product).update(avg_unit_cost=0)

        call_command("backfill_inventory_avg_cost", verbosity=0)
        first = Inventory.objects.get(product=product).avg_unit_cost
        self.assertEqual(first, Decimal("50.0000"))

        # Re-run without --force: already-seeded (non-zero) rows are left
        # alone, so a later purchase's effect on avg_unit_cost isn't wiped.
        order = create_purchase_order(
            supplier_id=self.supplier.id,
            items=[{"product_id": product.id, "quantity": 10, "unit_price": Decimal("70")}],
            user=self.admin,
        )
        for item in order.items.all():
            set_purchase_item_shelf_allocations(
                purchase_item_id=item.id,
                allocations=[{"shelf_id": self.shelf.id, "quantity": item.quantity}],
                user=self.admin,
            )
        confirm_purchase_order(order_id=order.id, user=self.admin)
        after_purchase = Inventory.objects.get(product=product).avg_unit_cost
        self.assertEqual(after_purchase, Decimal("60.0000"))

        call_command("backfill_inventory_avg_cost", verbosity=0)
        self.assertEqual(Inventory.objects.get(product=product).avg_unit_cost, after_purchase)

    def test_backfill_corrects_a_snapshot_already_skewed_by_a_past_return(self):
        """
        The whole reason this command replays full history instead of
        seeding from today's live batch-walk: a purchase return that
        already happened (before this fix shipped) has already skewed
        which batch has how much remaining_quantity, so "today's live
        snapshot" is the WRONG number for any product with return history.
        """
        from django.core.management import call_command
        from purchases.models import Inventory

        product, order_a = self.make_product_with_two_cost_batches()  # 10@50 + 10@70

        # Accept a return of 4 units specifically from the 50-cost batch —
        # this is exactly what skews a live batch-walk (remaining: 6@50 + 10@70).
        item_a = order_a.items.first()
        ret = create_purchase_return(
            order_id=order_a.id,
            items=[{"purchase_item_id": item_a.id, "quantity": 4}],
            user=self.admin,
        )
        for return_item in ret.items.all():
            set_purchase_return_item_shelf_allocations(
                return_item_id=return_item.id,
                allocations=[{"shelf_id": self.shelf.id, "quantity": return_item.quantity}],
                user=self.admin,
            )
        accept_purchase_return(return_id=ret.id, user=self.admin)

        # Simulate this row predating the fix: avg_unit_cost never seeded.
        Inventory.objects.filter(product=product).update(avg_unit_cost=0)

        call_command("backfill_inventory_avg_cost", verbosity=0)

        reconstructed = Inventory.objects.get(product=product).avg_unit_cost
        # True historical average (purchases only, return never counted): 60.
        self.assertEqual(reconstructed, Decimal("60.0000"))
        # What the OLD (wrong) "seed from today's live snapshot" approach
        # would have produced instead — proves this isn't a no-op scenario:
        # remaining batches are 6@50 + 10@70 = 300+700=1000, qty=16 -> 62.5.
        self.assertNotEqual(reconstructed, Decimal("62.5000"))

    def make_product_with_two_cost_batches(self):
        """Returns (product, order_a) — order_a is the first (50-cost) PO,
        so callers can return specifically from that batch."""
        product = self.make_stocked_product(stock=10)  # unit_cost=50
        order_a = product.purchase_items.select_related("order").first().order
        order_b = create_purchase_order(
            supplier_id=self.supplier.id,
            items=[{"product_id": product.id, "quantity": 10, "unit_price": Decimal("70")}],
            user=self.admin,
        )
        for item in order_b.items.all():
            set_purchase_item_shelf_allocations(
                purchase_item_id=item.id,
                allocations=[{"shelf_id": self.shelf.id, "quantity": item.quantity}],
                user=self.admin,
            )
        confirm_purchase_order(order_id=order_b.id, user=self.admin)
        return product, order_a

    def test_replay_accounts_for_a_sale_between_two_purchases(self):
        """
        Proves this is a true chronological event replay, not just a
        quantity-weighted sum over every purchase ever made (which would be
        WRONG whenever stock was depleted by a sale before a later
        purchase): buy 10@50 (avg=50, qty=10) -> sell 8 (qty=2, avg still
        50) -> buy 10@70. True perpetual-average result: (2*50 + 10*70) /
        12 = 66.6667. A naive "sum every purchase ever" shortcut would give
        (10*50 + 10*70)/20 = 60 instead — this test fails against that
        shortcut and passes against a real event-order replay.
        """
        from django.core.management import call_command
        from purchases.models import Inventory

        product = self.make_stocked_product(stock=10)  # unit_cost=50

        customer = create_customer(name="Cust A", code="CUSTA", address="x", user=self.admin)
        invoice = create_invoice(
            customer_id=customer.id,
            items=[{"product_id": product.id, "quantity": 8}],
            user=self.admin,
        )
        for inv_item in invoice.items.all():
            set_invoice_item_shelf_allocations(
                invoice_item_id=inv_item.id,
                allocations=[{"shelf_id": self.shelf.id, "quantity": inv_item.quantity}],
                user=self.admin,
            )
        confirm_invoice(invoice_id=invoice.id, user=self.admin)

        order_b = create_purchase_order(
            supplier_id=self.supplier.id,
            items=[{"product_id": product.id, "quantity": 10, "unit_price": Decimal("70")}],
            user=self.admin,
        )
        for item in order_b.items.all():
            set_purchase_item_shelf_allocations(
                purchase_item_id=item.id,
                allocations=[{"shelf_id": self.shelf.id, "quantity": item.quantity}],
                user=self.admin,
            )
        confirm_purchase_order(order_id=order_b.id, user=self.admin)

        # This purchase already ran under the fixed sync_inventory, so the
        # live value is already correct — confirm it directly.
        self.assertEqual(
            Inventory.objects.get(product=product).avg_unit_cost.quantize(Decimal("0.0001")),
            ((Decimal("2") * 50 + Decimal("10") * 70) / Decimal("12")).quantize(Decimal("0.0001")),
        )

        # Now prove the BACKFILL command reconstructs the same correct
        # number from scratch, via full replay (not a naive sum).
        Inventory.objects.filter(product=product).update(avg_unit_cost=0)
        call_command("backfill_inventory_avg_cost", verbosity=0)
        reconstructed = Inventory.objects.get(product=product).avg_unit_cost
        self.assertEqual(
            reconstructed.quantize(Decimal("0.0001")),
            ((Decimal("2") * 50 + Decimal("10") * 70) / Decimal("12")).quantize(Decimal("0.0001")),
        )
        naive_sum_shortcut = (Decimal("10") * 50 + Decimal("10") * 70) / Decimal("20")
        self.assertNotEqual(reconstructed, naive_sum_shortcut)


class DateRangeFilterBoundaryTests(ReportsTestBase):
    """
    The __date cast → half-open datetime range rewrite must select exactly
    the same local calendar day as before — these pin the day boundary.
    """

    def invoices_report(self, **params):
        request = self.factory.get("/reports/invoices/", params)
        force_authenticate(request, user=self.admin)
        return InvoicesReportView.as_view()(request)

    def test_exact_date_filter_includes_only_that_local_day(self):
        product = self.make_stocked_product()
        day = date(2026, 3, 15)
        on_day = self.make_confirmed_invoice(product, confirmed_on=day)
        self.make_confirmed_invoice(product, confirmed_on=date(2026, 3, 16))

        response = self.invoices_report(date="2026-03-15")
        ids = [r["id"] for r in response.data["results"]]
        self.assertEqual(ids, [on_day.id])
        self.assertEqual(response.data["stats"]["total_invoices"], 1)

    def test_date_range_is_inclusive_of_both_endpoints(self):
        product = self.make_stocked_product()
        first = self.make_confirmed_invoice(product, confirmed_on=date(2026, 3, 10))
        last = self.make_confirmed_invoice(product, confirmed_on=date(2026, 3, 12))
        self.make_confirmed_invoice(product, confirmed_on=date(2026, 3, 13))  # outside range

        response = self.invoices_report(date_from="2026-03-10", date_to="2026-03-12")
        ids = {r["id"] for r in response.data["results"]}
        self.assertEqual(ids, {first.id, last.id})

    def test_lost_inventory_report_date_filter_uses_record_created_at(self):
        product = self.make_stocked_product(stock=20)
        record = create_lost_inventory_record(
            items=[{
                "product_id": product.id, "quantity": 2, "reason": "damaged",
                "shelf_allocations": [{"shelf_id": self.shelf.id, "quantity": 2}],
            }],
            user=self.admin,
        )
        day = date(2026, 4, 1)
        LostInventoryRecord.objects.filter(pk=record.pk).update(
            created_at=timezone.make_aware(datetime.combine(day, time(9, 0))),
        )

        request = self.factory.get("/reports/lost-inventory/", {"date": "2026-04-01"})
        force_authenticate(request, user=self.admin)
        response = LostInventoryReportView.as_view()(request)
        self.assertEqual(response.data["count"], 1)

        request = self.factory.get("/reports/lost-inventory/", {"date": "2026-04-02"})
        force_authenticate(request, user=self.admin)
        response = LostInventoryReportView.as_view()(request)
        self.assertEqual(response.data["count"], 0)


class SearchTests(ReportsTestBase):
    def test_inventory_valuation_search_via_search_q(self):
        self.make_stocked_product(code="STL01", name="Steel Rod")
        self.make_stocked_product(code="CPR01", name="Copper Wire")

        request = self.factory.get("/reports/inventory-valuation/", {"search": "STEEL"})
        force_authenticate(request, user=self.admin)
        response = InventoryValuationReportView.as_view()(request)
        self.assertEqual([r["product_name"] for r in response.data["results"]], ["Steel Rod"])

        request = self.factory.get("/reports/inventory-valuation/", {"search": "CPR01"})
        force_authenticate(request, user=self.admin)
        response = InventoryValuationReportView.as_view()(request)
        self.assertEqual([r["product_code"] for r in response.data["results"]], ["CPR01"])

    def test_stock_movement_search_matches_in_both_filtered_and_unfiltered_branches(self):
        product = self.make_stocked_product(code="STL01", name="Steel Rod")
        self.make_stocked_product(code="CPR01", name="Copper Wire")

        # No date filter — reads ProductStockMovement directly.
        request = self.factory.get("/reports/stock-movement/", {"search": "steel"})
        force_authenticate(request, user=self.admin)
        response = StockMovementReportView.as_view()(request)
        self.assertEqual([r["product_code"] for r in response.data["results"]], ["STL01"])

        # With a date filter — live per-window aggregation branch.
        today = timezone.localdate().isoformat()
        request = self.factory.get(
            "/reports/stock-movement/", {"date_from": today, "date_to": today, "search": "steel"},
        )
        force_authenticate(request, user=self.admin)
        response = StockMovementReportView.as_view()(request)
        self.assertEqual([r["product_code"] for r in response.data["results"]], ["STL01"])

    def test_stock_movement_date_filter_includes_data_entry_opening_stock_purchases(self):
        # Regression: _stock_movement_totals_by_product's date-filtered
        # aggregation used to exclude order__is_data_entry purchases, so an
        # opening-stock addition (e.g. from the Data Entry app) showed 0
        # "purchased" the moment ANY date filter was applied, even though
        # the no-filter path (reading ProductStockMovement directly) always
        # showed it correctly.
        from data_entry.services import create_opening_stock

        product = Product.objects.create(name="Max Blue", code="MAX-BLU", category=self.category)
        create_rate(product_id=product.id, selling_price=Decimal("100"), user=self.admin)
        sys_supplier = create_supplier(name="Opening Stock", code="SYS-OPENING", user=self.admin)

        create_opening_stock(
            items=[{
                "product_id": product.id, "quantity": 2, "unit_price": Decimal("50"),
                "shelf_id": self.shelf.id,
            }],
            user=self.admin,
        )

        today = timezone.localdate().isoformat()
        request = self.factory.get("/reports/stock-movement/", {"date": today, "search": "max"})
        force_authenticate(request, user=self.admin)
        response = StockMovementReportView.as_view()(request)

        rows = {r["product_code"]: r for r in response.data["results"]}
        self.assertEqual(rows["MAX-BLU"]["total_purchased"], 2)
        # search="max" scopes the header stats to just the matching
        # product(s) too (see test below) — exact, not just >=.
        self.assertEqual(response.data["stats"]["total_purchased"], 2)

    def test_stock_movement_header_stats_scoped_by_search(self):
        # search should scope the header "total_purchased" etc. to only the
        # matching products — no search means every product; search="max"
        # means only products matching "max". Covers both the no-date-filter
        # (all-time, live-aggregated-because-of-search) and date-filtered cases.
        max_product = self.make_stocked_product(code="MAX01", name="Max Blue", stock=5)
        self.make_stocked_product(code="STL01", name="Steel Rod", stock=7)

        # No search — stats cover both products (5 + 7 = 12).
        request = self.factory.get("/reports/stock-movement/", {})
        force_authenticate(request, user=self.admin)
        response = StockMovementReportView.as_view()(request)
        self.assertEqual(response.data["stats"]["total_purchased"], 12)

        # search="max", no date filter — stats scoped to MAX01 only (5),
        # not the company-wide total (12).
        request = self.factory.get("/reports/stock-movement/", {"search": "max"})
        force_authenticate(request, user=self.admin)
        response = StockMovementReportView.as_view()(request)
        self.assertEqual(response.data["stats"]["total_purchased"], 5)
        self.assertEqual([r["product_code"] for r in response.data["results"]], ["MAX01"])

        # search="max" WITH a date filter too — still scoped to MAX01 only.
        today = timezone.localdate().isoformat()
        request = self.factory.get("/reports/stock-movement/", {"date": today, "search": "max"})
        force_authenticate(request, user=self.admin)
        response = StockMovementReportView.as_view()(request)
        self.assertEqual(response.data["stats"]["total_purchased"], 5)

    def test_stock_movement_search_scoped_stats_query_count_flat(self):
        # Query count for a search-scoped stats call must not grow with the
        # number of UNRELATED products in the system — search_q() resolves
        # matching product ids first (one indexed query), then every one of
        # the 6 aggregation queries is scoped to just those ids. This is
        # what keeps the endpoint fast regardless of company size.
        self.make_stocked_product(code="MAX01", name="Max Blue")
        baseline_request = self.factory.get("/reports/stock-movement/", {"search": "max"})
        force_authenticate(baseline_request, user=self.admin)
        with CaptureQueriesContext(connection) as ctx_baseline:
            StockMovementReportView.as_view()(baseline_request)
        baseline_count = len(ctx_baseline.captured_queries)

        for i in range(10):
            self.make_stocked_product(code=f"OTH{i}", name=f"Other Product {i}")

        grown_request = self.factory.get("/reports/stock-movement/", {"search": "max"})
        force_authenticate(grown_request, user=self.admin)
        with CaptureQueriesContext(connection) as ctx_grown:
            StockMovementReportView.as_view()(grown_request)
        grown_count = len(ctx_grown.captured_queries)

        self.assertEqual(baseline_count, grown_count)
