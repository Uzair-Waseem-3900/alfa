from datetime import date, datetime, time
from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from billing.models import Invoice
from billing.services import (
    confirm_invoice, create_customer, create_invoice,
    set_invoice_item_shelf_allocations,
)
from purchases.models import Category, LostInventoryRecord, Product, Shelf
from purchases.services import (
    confirm_purchase_order, create_lost_inventory_record, create_purchase_order,
    create_supplier, set_purchase_item_shelf_allocations,
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
