from datetime import date, timedelta
from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from assets.services import create_asset, create_asset_category
from billing.services import (
    confirm_invoice, create_customer, create_invoice, create_payment,
    set_invoice_item_shelf_allocations, update_invoice_due_date,
)
from cash_flow.services import create_expense, create_expense_category
from purchases.models import Category, Product, Shelf
from purchases.services import (
    confirm_purchase_order, create_opening_stock_order, create_purchase_order,
    create_supplier, set_purchase_item_shelf_allocations,
)
from cash_management.services import create_investor
from data_entry.services import (
    create_customer_opening_balance, create_opening_cash,
    create_opening_investor_investment, create_supplier_opening_balance,
)
from profits.services import _add_months, catch_up_monthly_profits
from rates.services import create_rate

from .models import BalanceSheetSnapshot
from .services import catch_up_balance_sheet_snapshots
from .selectors import (
    AGING_BUCKETS, _bucket_for_days_overdue,
    get_ap_aging_rows, get_ap_aging_summary, get_ar_aging_rows,
    get_ar_aging_summary, get_balance_sheet_for_period, get_balance_sheet_live,
    get_cash_flow_statement, get_fixed_asset_register_rows,
    get_fixed_asset_register_summary, get_income_statement,
)
from .views import (
    APAgingListView, ARAgingListView, BalanceSheetView,
    CashFlowStatementView, FixedAssetRegisterListView, IncomeStatementView,
)
from payment_methods.models import PaymentMethod
from users.models import User


def make_admin(email="admin@example.com"):
    return User.objects.create_user(
        email=email, password="Adm1n-secret!", first_name="Admin",
        last_name="User", is_staff=True,
    )


def make_normal_user(email="normal@example.com"):
    return User.objects.create_user(
        email=email, password="N0rmal-secret!", first_name="Normal", last_name="User",
    )


class AccountingTestBase(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.admin = make_admin()
        self.category = Category.objects.create(name="Cat A")
        self.shelf = Shelf.objects.create(name="Shelf A")
        self.supplier = create_supplier(name="Ali Traders", code="ALI", user=self.admin)
        self.customer = create_customer(
            name="Big Mart", code="BM", address="Main St", user=self.admin,
        )
        self.cash = PaymentMethod.objects.get_or_create(name="Cash", defaults={"balance": Decimal("1000000")})[0]

    def cash_split(self, amount):
        return [(self.cash, Decimal(amount))]

    def make_stocked_product(self, code="P001", stock=10, unit_cost="50", selling_price="100"):
        product = Product.objects.create(name="Product 1", code=code, category=self.category)
        create_rate(product_id=product.id, selling_price=Decimal(selling_price), user=self.admin)
        order = create_purchase_order(
            supplier_id=self.supplier.id,
            items=[{"product_id": product.id, "quantity": stock, "unit_price": Decimal(unit_cost)}],
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

    def make_confirmed_invoice(self, product, quantity=4, due_date=None):
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
        if due_date is not None:
            update_invoice_due_date(invoice_id=invoice.id, new_due_date=due_date, user=self.admin)
            invoice.refresh_from_db()
        return invoice

    def make_confirmed_purchase_order(self, product, quantity=4, unit_cost="50"):
        order = create_purchase_order(
            supplier_id=self.supplier.id,
            items=[{"product_id": product.id, "quantity": quantity, "unit_price": Decimal(unit_cost)}],
            user=self.admin,
        )
        for item in order.items.all():
            set_purchase_item_shelf_allocations(
                purchase_item_id=item.id,
                allocations=[{"shelf_id": self.shelf.id, "quantity": item.quantity}],
                user=self.admin,
            )
        return confirm_purchase_order(order_id=order.id, user=self.admin)


# ---------------------------------------------------------------------------
# A/R Aging
# ---------------------------------------------------------------------------

class ARAgingTests(AccountingTestBase):
    def test_bucketing_by_days_overdue(self):
        product = self.make_stocked_product(stock=20)
        today = timezone.localdate()
        current_invoice = self.make_confirmed_invoice(product, quantity=1, due_date=today + timedelta(days=5))
        overdue_invoice = self.make_confirmed_invoice(product, quantity=1, due_date=today - timedelta(days=45))

        rows = get_ar_aging_rows()
        by_id = {r["invoice_id"]: r for r in rows}
        self.assertEqual(by_id[current_invoice.id]["bucket"], "current")
        self.assertEqual(by_id[overdue_invoice.id]["bucket"], "31_60")
        self.assertEqual(by_id[overdue_invoice.id]["outstanding"], overdue_invoice.credit_outstanding)

        summary = get_ar_aging_summary(rows)
        self.assertEqual(summary["invoice_count"], 2)
        self.assertEqual(
            summary["grand_total"],
            current_invoice.credit_outstanding + overdue_invoice.credit_outstanding,
        )
        self.assertEqual(summary["buckets"]["31_60"]["count"], 1)

    def test_view_bucket_filter_narrows_results_but_not_summary(self):
        product = self.make_stocked_product(stock=20)
        today = timezone.localdate()
        self.make_confirmed_invoice(product, quantity=1, due_date=today + timedelta(days=5))
        overdue_invoice = self.make_confirmed_invoice(product, quantity=1, due_date=today - timedelta(days=45))

        request = self.factory.get("/api/accounting/ar-aging/", {"bucket": "31_60"})
        force_authenticate(request, user=self.admin)
        response = ARAgingListView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        # Table narrows to just the matching bucket...
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["invoice_id"], overdue_invoice.id)
        # ...but the summary cards still reflect BOTH invoices, unfiltered.
        self.assertEqual(response.data["summary"]["invoice_count"], 2)

    def test_fully_paid_invoice_excluded(self):
        product = self.make_stocked_product(stock=20)
        invoice = self.make_confirmed_invoice(product, quantity=1)
        from billing.services import create_payment
        create_payment(
            invoice_id=invoice.id, amount=invoice.credit_outstanding,
            method_allocations=self.cash_split(invoice.credit_outstanding), payment_date=timezone.localdate(), user=self.admin,
        )
        rows = get_ar_aging_rows()
        self.assertNotIn(invoice.id, {r["invoice_id"] for r in rows})

    # ---- SQL bucketing must match the old Python bucketing exactly ---------
    # Bucketing/ordering/pagination moved from Python into the database so a
    # page of 25 stops materializing every outstanding invoice. That's only
    # acceptable if not one number moved, and the boundaries are where an
    # off-by-one would hide.

    def test_sql_buckets_match_python_bucketing_at_every_boundary(self):
        product = self.make_stocked_product(stock=200)
        today = timezone.localdate()

        # Exact boundary days, on both sides of each cutoff.
        expected = {}
        for offset in (-5, 0, 1, 30, 31, 60, 61, 90, 91, 200):
            inv = self.make_confirmed_invoice(
                product, quantity=1, due_date=today - timedelta(days=offset),
            )
            # `offset` days past due == days_overdue, so the pre-existing
            # Python classifier is the oracle the SQL must reproduce.
            expected[inv.id] = _bucket_for_days_overdue(offset)

        by_id = {r["invoice_id"]: r for r in get_ar_aging_rows()}
        self.assertEqual(len(by_id), len(expected))
        for invoice_id, want in expected.items():
            self.assertEqual(
                by_id[invoice_id]["bucket"], want,
                f"invoice {invoice_id}: SQL bucket disagrees with _bucket_for_days_overdue",
            )
            self.assertEqual(
                by_id[invoice_id]["days_overdue"],
                (today - by_id[invoice_id]["due_date"]).days,
            )

        # Every bucket actually got exercised — otherwise this test could pass
        # while silently only checking one branch of the CASE.
        self.assertEqual(set(expected.values()), set(AGING_BUCKETS))

    def test_ordering_is_worst_first_and_deterministic(self):
        """_due_date ASC == days_overdue DESC. The `id` tiebreaker matters
        now that pagination is real LIMIT/OFFSET — without it, rows sharing a
        due date could repeat or vanish between pages."""
        product = self.make_stocked_product(stock=200)
        today = timezone.localdate()
        for offset in (10, 90, 45, 90, 1):
            self.make_confirmed_invoice(
                product, quantity=1, due_date=today - timedelta(days=offset),
            )

        rows = get_ar_aging_rows()
        days = [r["days_overdue"] for r in rows]
        self.assertEqual(days, sorted(days, reverse=True))

        tied = [r["invoice_id"] for r in rows if r["days_overdue"] == 90]
        self.assertEqual(len(tied), 2)
        self.assertEqual(tied, sorted(tied), "tied rows must order by id")

    def test_db_summary_matches_rows_summary(self):
        """get_ar_aging_summary() has two paths — a GROUP BY (list view) and a
        Python loop over materialized dicts (print view). They must agree, or
        the page and its PDF would disagree."""
        product = self.make_stocked_product(stock=200)
        today = timezone.localdate()
        for offset in (-3, 5, 40, 75, 120):
            self.make_confirmed_invoice(
                product, quantity=1, due_date=today - timedelta(days=offset),
            )

        from_db = get_ar_aging_summary()
        from_rows = get_ar_aging_summary(get_ar_aging_rows())
        self.assertEqual(from_db, from_rows)

    def test_list_view_does_not_materialize_every_row(self):
        """The point of the change: query count must stay flat as the
        outstanding set grows, instead of scaling with it."""
        product = self.make_stocked_product(stock=300)
        today = timezone.localdate()
        for offset in range(0, 60):
            self.make_confirmed_invoice(
                product, quantity=1, due_date=today - timedelta(days=offset),
            )

        request = self.factory.get("/api/accounting/ar-aging/", {"page_size": 25})
        force_authenticate(request, user=self.admin)
        with CaptureQueriesContext(connection) as ctx:
            response = ARAgingListView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(
            len(ctx.captured_queries), 6,
            "count + page + summary GROUP BY, not one query per row",
        )
        # 60 outstanding invoices exist, but only a page came back.
        self.assertEqual(response.data["count"], 60)
        self.assertEqual(len(response.data["results"]), 25)
        self.assertEqual(response.data["summary"]["invoice_count"], 60)

    def test_view_requires_admin(self):
        product = self.make_stocked_product(stock=20)
        self.make_confirmed_invoice(product, quantity=1)

        normal = make_normal_user()
        request = self.factory.get("/api/accounting/ar-aging/")
        force_authenticate(request, user=normal)
        response = ARAgingListView.as_view()(request)
        self.assertEqual(response.status_code, 403)

        request = self.factory.get("/api/accounting/ar-aging/")
        force_authenticate(request, user=self.admin)
        response = ARAgingListView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

    def test_query_count_is_bounded(self):
        product = self.make_stocked_product(stock=50)
        for _ in range(5):
            self.make_confirmed_invoice(product, quantity=1)

        request = self.factory.get("/api/accounting/ar-aging/")
        force_authenticate(request, user=self.admin)
        with CaptureQueriesContext(connection) as ctx:
            response = ARAgingListView.as_view()(request)
            response.render()
        self.assertEqual(response.status_code, 200)
        # One count-ish query from the paginator's list() + one row query
        # (select_related pulls customer in the same query) — no N+1.
        self.assertLessEqual(len(ctx.captured_queries), 3)


# ---------------------------------------------------------------------------
# A/P Aging
# ---------------------------------------------------------------------------

class APAgingTests(AccountingTestBase):
    def test_outstanding_purchase_order_appears(self):
        # make_stocked_product itself confirms a purchase order (to stock
        # inventory) that's left unpaid, so it's a second outstanding order
        # alongside the one this test creates directly — both are real.
        product = self.make_stocked_product(stock=20)
        order = self.make_confirmed_purchase_order(product, quantity=2)

        rows = get_ap_aging_rows()
        by_id = {r["order_id"]: r for r in rows}
        self.assertIn(order.id, by_id)
        self.assertEqual(by_id[order.id]["outstanding"], order.payable_outstanding)
        self.assertEqual(by_id[order.id]["bucket"], "current")

        summary = get_ap_aging_summary(rows)
        self.assertEqual(summary["order_count"], 2)
        self.assertEqual(
            summary["grand_total"],
            sum((r["outstanding"] for r in rows), Decimal("0")),
        )

    def test_fully_paid_order_excluded(self):
        product = self.make_stocked_product(stock=20)
        order = self.make_confirmed_purchase_order(product, quantity=2)
        from purchases.services import create_supplier_payment
        create_supplier_payment(
            order_id=order.id, amount=order.payable_outstanding,
            method_allocations=self.cash_split(order.payable_outstanding), payment_date=timezone.localdate(), user=self.admin,
        )
        rows = get_ap_aging_rows()
        self.assertNotIn(order.id, {r["order_id"] for r in rows})

    def test_view_requires_admin(self):
        normal = make_normal_user()
        request = self.factory.get("/api/accounting/ap-aging/")
        force_authenticate(request, user=normal)
        response = APAgingListView.as_view()(request)
        self.assertEqual(response.status_code, 403)


# ---------------------------------------------------------------------------
# Fixed Asset Register
# ---------------------------------------------------------------------------

class FixedAssetRegisterTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.admin = make_admin()
        self.category = create_asset_category(
            name="Machinery", valuation_method="depreciation",
            depreciation_rate=Decimal("0.12"), user=self.admin,
        )
        self.asset = create_asset(
            name="Generator", category_id=self.category.id, acquisition_type="existing",
            cost=Decimal("1200"), acquisition_date=date.today(), user=self.admin,
        )

    def test_register_row_matches_stored_worth(self):
        rows = get_fixed_asset_register_rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.asset.refresh_from_db()
        self.assertEqual(row["cost"], Decimal("1200"))
        self.assertEqual(row["net_book_value"], self.asset.current_worth)
        self.assertEqual(row["accumulated_depreciation"], Decimal("1200") - self.asset.current_worth)
        self.assertFalse(row["is_disposed"])

    def test_summary_totals(self):
        summary = get_fixed_asset_register_summary()
        self.assertEqual(summary["asset_count"], 1)
        self.assertEqual(summary["total_cost"], Decimal("1200"))

    def test_view_requires_admin(self):
        normal = make_normal_user()
        request = self.factory.get("/api/accounting/fixed-asset-register/")
        force_authenticate(request, user=normal)
        response = FixedAssetRegisterListView.as_view()(request)
        self.assertEqual(response.status_code, 403)

        request = self.factory.get("/api/accounting/fixed-asset-register/")
        force_authenticate(request, user=self.admin)
        response = FixedAssetRegisterListView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)


# ---------------------------------------------------------------------------
# Cash Flow Statement
# ---------------------------------------------------------------------------

class CashFlowStatementTests(AccountingTestBase):
    def test_classifies_operating_activities_and_nets_correctly(self):
        product = self.make_stocked_product(stock=20)
        invoice = self.make_confirmed_invoice(product, quantity=1)
        today = timezone.localdate()

        create_payment(
            invoice_id=invoice.id, amount=invoice.credit_outstanding,
            method_allocations=self.cash_split(invoice.credit_outstanding), payment_date=today, user=self.admin,
        )
        cat = create_expense_category(name="Utilities", user=self.admin)
        create_expense(
            name="Electricity", category_id=cat.id, amount=Decimal("50"),
            expense_date=today, user=self.admin,
            method_allocations=self.cash_split("50"),
        )

        result = get_cash_flow_statement(
            date_from=today.replace(day=1).isoformat(), date_to=today.isoformat(),
        )
        operating_labels = {line["label"] for line in result["operating"]["lines"]}
        self.assertIn("Invoice Payments Received", operating_labels)
        self.assertIn("Expenses Paid", operating_labels)
        self.assertEqual(
            result["operating"]["net"],
            invoice.credit_outstanding - Decimal("50"),
        )
        self.assertEqual(result["investing"]["lines"], [])
        self.assertEqual(result["financing"]["lines"], [])
        self.assertEqual(result["net_change_in_cash"], result["operating"]["net"])

    def test_opening_closing_only_present_when_range_ends_today(self):
        today = timezone.localdate()
        result_today = get_cash_flow_statement(
            date_from=today.isoformat(), date_to=today.isoformat(),
        )
        self.assertIsNotNone(result_today["closing_cash"])
        self.assertIsNotNone(result_today["opening_cash"])

        past_day = (today - timedelta(days=10)).isoformat()
        result_past = get_cash_flow_statement(date_from=past_day, date_to=past_day)
        self.assertIsNone(result_past["closing_cash"])
        self.assertIsNone(result_past["opening_cash"])

    def test_view_requires_admin(self):
        normal = make_normal_user()
        request = self.factory.get("/api/accounting/cash-flow-statement/")
        force_authenticate(request, user=normal)
        response = CashFlowStatementView.as_view()(request)
        self.assertEqual(response.status_code, 403)

        request = self.factory.get("/api/accounting/cash-flow-statement/")
        force_authenticate(request, user=self.admin)
        response = CashFlowStatementView.as_view()(request)
        self.assertEqual(response.status_code, 200)

    # ---- Date-range validation -------------------------------------------
    # date_from/date_to arrive straight from the query string. Before this,
    # nothing parsed or bounded them: a malformed date reached the ORM and
    # surfaced as a 500, an inverted range returned an empty statement that
    # looked like a real answer, and a typo'd year scanned the entire
    # CashMovement table.

    def _get(self, params):
        request = self.factory.get("/api/accounting/cash-flow-statement/", params)
        force_authenticate(request, user=self.admin)
        return CashFlowStatementView.as_view()(request)

    def test_malformed_date_is_400_not_500(self):
        response = self._get({"date_from": "not-a-date", "date_to": "2026-08-15"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("date_from", response.data)

    def test_inverted_range_is_rejected_not_silently_empty(self):
        response = self._get({"date_from": "2026-08-15", "date_to": "2026-01-01"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("date_from", response.data)

    def test_range_over_ten_years_is_rejected(self):
        response = self._get({"date_from": "1900-01-01", "date_to": "2026-08-15"})
        self.assertEqual(response.status_code, 400)

    def test_exactly_120_months_is_allowed(self):
        """The cap is 120 months INCLUSIVE — guards an off-by-one that would
        reject a legitimate 10-year request."""
        response = self._get({"date_from": "2017-01-05", "date_to": "2026-12-31"})
        self.assertEqual(response.status_code, 200)

    def test_valid_range_still_works(self):
        response = self._get({"date_from": "2026-01-01", "date_to": "2026-08-15"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["date_from"], "2026-01-01")
        self.assertEqual(response.data["date_to"], "2026-08-15")


# ---------------------------------------------------------------------------
# Income Statement
# ---------------------------------------------------------------------------

class IncomeStatementTests(AccountingTestBase):
    def _finalize_last_month(self):
        product = self.make_stocked_product(stock=20, unit_cost="50", selling_price="100")
        invoice = self.make_confirmed_invoice(product, quantity=4)

        today = timezone.localdate()
        y, m = _add_months(today.year, today.month, -1)
        period = f"{y:04d}-{m:02d}"
        from billing.models import Invoice
        Invoice.objects.filter(pk=invoice.pk).update(
            confirmed_at=timezone.now().replace(year=y, month=m, day=15),
        )

        cat = create_expense_category(name="Rent", user=self.admin)
        create_expense(
            name="Shop Rent", category_id=cat.id, amount=Decimal("30"),
            expense_date=date(y, m, 20), user=self.admin,
            method_allocations=self.cash_split("30"),
        )

        catch_up_monthly_profits(user=self.admin)
        return period

    def test_finished_period_matches_monthly_profit_and_includes_breakdown(self):
        period = self._finalize_last_month()
        from profits.models import MonthlyProfit
        mp = MonthlyProfit.objects.get(period=period)

        data = get_income_statement(period=period)
        self.assertFalse(data["is_provisional"])
        self.assertEqual(data["net_profit"], mp.net_profit)
        self.assertEqual(data["gross_profit"], mp.gross_profit)
        categories = {line["category"] for line in data["expense_breakdown"]}
        self.assertIn("Rent", categories)

    def test_current_month_is_provisional(self):
        data = get_income_statement()
        self.assertTrue(data["is_provisional"])

    def test_view_404_for_unfinalized_period(self):
        request = self.factory.get("/api/accounting/income-statement/", {"period": "2020-01"})
        force_authenticate(request, user=self.admin)
        response = IncomeStatementView.as_view()(request)
        self.assertEqual(response.status_code, 404)

    def test_view_requires_admin(self):
        normal = make_normal_user()
        request = self.factory.get("/api/accounting/income-statement/")
        force_authenticate(request, user=normal)
        response = IncomeStatementView.as_view()(request)
        self.assertEqual(response.status_code, 403)

    def _pay_recurring_expense(self, *, period, category_name, amount, payment_date):
        """Creates a template + assignment + payment for `period` so the month
        has a RecurringExpenseAssignmentPayment row to (not) show up in the
        breakdown."""
        from recurring_expenses.services import (
            create_recurring_expense, create_recurring_expense_assignment,
            create_recurring_expense_category, create_recurring_expense_payment,
        )

        cat = create_recurring_expense_category(name=category_name, user=self.admin)
        template = create_recurring_expense(
            name=f"{category_name} Bill", category_id=cat.id, amount=Decimal(amount),
            start_date=payment_date, user=self.admin,
        )
        assignment = create_recurring_expense_assignment(
            recurring_expense_id=template.id, period=period, user=self.admin,
        )
        create_recurring_expense_payment(
            assignment_id=assignment.id, amount=Decimal(amount),
            payment_date=payment_date, method_allocations=self.cash_split(amount), user=self.admin,
        )

    def test_expense_breakdown_excludes_recurring_and_foots_to_expenses_paid(self):
        """
        Regression: the breakdown used to concatenate recurring-expense
        categories too, while the Income Statement ALSO renders a separate
        "Recurring Expenses" total line — so recurring expenses appeared
        twice in the visible lines and the section's own lines no longer
        added up to its own "Total Operating Expenses" subtotal (overstated
        by exactly recurring_expenses_paid). The breakdown must decompose
        expenses_paid and nothing else.
        """
        product = self.make_stocked_product(stock=20, unit_cost="50", selling_price="100")
        invoice = self.make_confirmed_invoice(product, quantity=4)

        today = timezone.localdate()
        y, m = _add_months(today.year, today.month, -1)
        period = f"{y:04d}-{m:02d}"
        from billing.models import Invoice
        Invoice.objects.filter(pk=invoice.pk).update(
            confirmed_at=timezone.now().replace(year=y, month=m, day=15),
        )

        # A one-off expense and a recurring payment sharing the SAME category
        # name — the exact collision that produced two identical-looking rows.
        cat = create_expense_category(name="Utilities", user=self.admin)
        create_expense(
            name="Electricity Top-Up", category_id=cat.id, amount=Decimal("40"),
            expense_date=date(y, m, 20), user=self.admin,
            method_allocations=self.cash_split("40"),
        )
        self._pay_recurring_expense(
            period=period, category_name="Utilities", amount="25",
            payment_date=date(y, m, 21),
        )

        catch_up_monthly_profits(user=self.admin)
        data = get_income_statement(period=period)

        # Both figures are genuinely non-zero, so this test can actually fail.
        self.assertEqual(Decimal(data["expenses_paid"]), Decimal("40"))
        self.assertEqual(Decimal(data["recurring_expenses_paid"]), Decimal("25"))

        breakdown = data["expense_breakdown"]
        self.assertEqual(
            sum(Decimal(line["amount"]) for line in breakdown),
            Decimal(data["expenses_paid"]),
            "expense_breakdown must sum to expenses_paid exactly — no recurring rows.",
        )
        # "Utilities" must appear exactly once (the one-off), not twice.
        utilities_rows = [b for b in breakdown if b["category"] == "Utilities"]
        self.assertEqual(len(utilities_rows), 1)
        self.assertEqual(Decimal(utilities_rows[0]["amount"]), Decimal("40"))

    def test_print_operating_expense_lines_foot_to_their_subtotal(self):
        """
        Guards the PDF itself, not just the selector — the print view builds
        its sections independently of the API view and is what an accountant
        actually reads. Every non-bold line in Operating Expenses must add up
        to the bold "Total Operating Expenses" line.
        """
        from .views import IncomeStatementPrintView

        product = self.make_stocked_product(stock=20, unit_cost="50", selling_price="100")
        invoice = self.make_confirmed_invoice(product, quantity=4)
        today = timezone.localdate()
        y, m = _add_months(today.year, today.month, -1)
        period = f"{y:04d}-{m:02d}"
        from billing.models import Invoice
        Invoice.objects.filter(pk=invoice.pk).update(
            confirmed_at=timezone.now().replace(year=y, month=m, day=15),
        )
        cat = create_expense_category(name="Utilities", user=self.admin)
        create_expense(
            name="Electricity Top-Up", category_id=cat.id, amount=Decimal("40"),
            expense_date=date(y, m, 20), user=self.admin,
            method_allocations=self.cash_split("40"),
        )
        self._pay_recurring_expense(
            period=period, category_name="Utilities", amount="25",
            payment_date=date(y, m, 21),
        )
        catch_up_monthly_profits(user=self.admin)

        captured = {}
        original = IncomeStatementPrintView._build_sections

        def _capture(self_view, data):
            sections = original(self_view, data)
            captured["sections"] = sections
            return sections

        IncomeStatementPrintView._build_sections = _capture
        try:
            request = self.factory.get(
                "/api/accounting/income-statement/print/", {"period": period},
            )
            force_authenticate(request, user=self.admin)
            response = IncomeStatementPrintView.as_view()(request)
            self.assertEqual(response.status_code, 200)
        finally:
            IncomeStatementPrintView._build_sections = original

        opex = next(s for s in captured["sections"] if s["heading"] == "Operating Expenses")
        line_total = sum(
            Decimal(line["amount"]) for line in opex["lines"] if not line.get("bold")
        )
        subtotal = next(
            Decimal(line["amount"]) for line in opex["lines"]
            if line.get("bold") and line["label"] == "Total Operating Expenses"
        )
        self.assertEqual(
            line_total, subtotal,
            "Printed Operating Expenses lines must add up to their own subtotal.",
        )


# ---------------------------------------------------------------------------
# Balance Sheet
# ---------------------------------------------------------------------------

class BalanceSheetTests(AccountingTestBase):
    def test_live_balance_sheet_balances(self):
        product = self.make_stocked_product(stock=20, unit_cost="50", selling_price="100")
        self.make_confirmed_invoice(product, quantity=2)

        data = get_balance_sheet_live()
        self.assertEqual(
            data["assets"]["total"] - data["liabilities"]["total"] - data["equity"]["total"],
            data["balance_check"],
        )
        self.assertTrue(data["is_balanced"], msg=f"balance_check={data['balance_check']}")

    def test_balances_with_data_entry_bootstrap_data(self):
        """
        Regression test for a real Rs 1000 mismatch traced back to exactly
        this gap: customer/supplier opening balances and opening stock each
        create one side of a transaction (an asset or liability) with no
        natural double-entry counterpart, so without opening_balance_equity
        the balance sheet would never balance for a business that used the
        Data Entry app to bootstrap pre-existing debts/stock at go-live.
        """
        customer = create_customer(name="Old Customer", code="OLDC", address="X", user=self.admin)
        create_customer_opening_balance(customer_id=customer.id, amount=Decimal("5000"), user=self.admin)

        supplier2 = create_supplier(name="Old Supplier", code="OLDS", user=self.admin)
        create_supplier_opening_balance(supplier_id=supplier2.id, amount=Decimal("8000"), user=self.admin)

        product = Product.objects.create(name="Legacy Stock", code="LEGACY", category=self.category)
        system_supplier = create_supplier(name="System", code="SYS", user=self.admin)
        create_opening_stock_order(
            supplier=system_supplier,
            items=[{"product_id": product.id, "quantity": 10, "unit_price": Decimal("300"), "shelf_id": self.shelf.id}],
            user=self.admin,
        )

        data = get_balance_sheet_live()
        # +5000 (customer OB) +3000 (10*300 opening stock) -8000 (supplier OB) = 0
        self.assertEqual(data["equity"]["opening_balance_equity"], Decimal("0"))
        self.assertTrue(data["is_balanced"], msg=f"balance_check={data['balance_check']}")

    def test_balances_with_opening_cash(self):
        """Opening Cash (data_entry Feature 3) is a cash asset with nothing
        offsetting it — must be added to opening_balance_equity, same
        reasoning as customer opening balances."""
        create_opening_cash(amount=Decimal("2000"), user=self.admin)

        data = get_balance_sheet_live()
        self.assertEqual(data["equity"]["opening_balance_equity"], Decimal("2000"))
        self.assertTrue(data["is_balanced"], msg=f"balance_check={data['balance_check']}")

    def test_balances_with_opening_investor_investment(self):
        """
        Opening Investor Investment (data_entry Feature 5) is the OPPOSITE
        direction from the other four: it inflates CashManagementFlow.
        net_investor_capital (this Balance Sheet's equity.investor_capital)
        with NO cash asset behind it, by design — cash_management.services.
        create_investor_transaction's is_data_entry branch deliberately
        skips the cash_in_hand sync ("the cash isn't actually sitting in
        the till"). Without subtracting it, equity would exceed assets.
        """
        investor = create_investor(name="Old Investor", growth_rate=Decimal("0"), user=self.admin)
        create_opening_investor_investment(investor_id=investor.id, amount=Decimal("3000"), user=self.admin)

        data = get_balance_sheet_live()
        self.assertEqual(data["equity"]["investor_capital"], Decimal("3000"))
        self.assertEqual(data["equity"]["opening_balance_equity"], Decimal("-3000"))
        self.assertTrue(data["is_balanced"], msg=f"balance_check={data['balance_check']}")

    def test_opening_balance_equity_never_imports_data_entry(self):
        """
        The data_entry app is meant to be removed after go-live — if
        accounting.selectors ever imports FROM data_entry.models again,
        the entire Balance Sheet breaks the moment that happens. Checks for
        an actual import statement, not the bare word (which legitimately
        appears in comments explaining WHY it's avoided).
        """
        import inspect
        from . import selectors as accounting_selectors

        source = inspect.getsource(accounting_selectors)
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("from data_entry") or stripped.startswith("import data_entry"):
                self.fail(f"accounting/selectors.py imports data_entry: {stripped!r}")

    def test_live_view_query_count_is_small_and_fixed(self):
        """
        Per architecture.md's STRICT 200ms rule and verification.md rule 6 —
        counted, never eyeballed. 7 is the honest number today, down from 21:

            1  subquery-joined read of all five Flow singletons
            2  get_gross_profit_trend (invoice + return TruncMonth GROUP BY)
            1  profits.compute_month_figures_in_one_query — ten month
               figures that used to be ten separate round-trips
            2  inventory valuation (Inventory rows + FIFO batches)
            1  _compute_equity_offsets — eight bootstrap/asset offsets that
               used to be six separate round-trips

        None is an N+1 or proportional to total data size; each was verified
        by reading the emitted SQL, not inferred.

        Bound set a little above 7 so this catches a REAL regression (an
        accidental N+1, or a collapsed query silently un-collapsing) instead
        of false-alarming on variance. If it creeps past 10, investigate —
        do not just raise the bound. Getting below ~4 would need caching
        opening_balance_equity on a singleton, which is a design change (new
        persistent state + an invalidation obligation), not an optimization.
        """
        product = self.make_stocked_product(stock=20)
        self.make_confirmed_invoice(product, quantity=1)

        # Measure STEADY STATE. The read-first singleton fallbacks (CashFlow,
        # ProfitFlow) each cost a few extra queries on their very first miss —
        # a fresh test database pays that, a live system paid it once and
        # never again. Counting the bootstrap path would report ~12 and
        # describe a state no real request is ever in.
        get_balance_sheet_live()

        request = self.factory.get("/api/accounting/balance-sheet/")
        force_authenticate(request, user=self.admin)
        with CaptureQueriesContext(connection) as ctx:
            response = BalanceSheetView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(
            len(ctx.captured_queries), 10,
            msg=f"{len(ctx.captured_queries)} queries — investigate before shipping:\n"
                + "\n".join(q["sql"][:120] for q in ctx.captured_queries),
        )

    def test_catch_up_snapshots_only_most_recent_finished_month(self):
        product = self.make_stocked_product(stock=20)
        invoice = self.make_confirmed_invoice(product, quantity=1)
        today = timezone.localdate()
        y, m = _add_months(today.year, today.month, -1)
        period = f"{y:04d}-{m:02d}"
        from billing.models import Invoice
        Invoice.objects.filter(pk=invoice.pk).update(
            confirmed_at=timezone.now().replace(year=y, month=m, day=15),
        )
        catch_up_monthly_profits(user=self.admin)

        created = catch_up_balance_sheet_snapshots()
        self.assertEqual(created, 1)
        self.assertTrue(BalanceSheetSnapshot.objects.filter(period=period).exists())

        # Idempotent — calling again creates nothing new.
        self.assertEqual(catch_up_balance_sheet_snapshots(), 0)
        self.assertEqual(BalanceSheetSnapshot.objects.count(), 1)

        snap = BalanceSheetSnapshot.objects.get(period=period)
        self.assertEqual(snap.total_assets - snap.total_liabilities - snap.total_equity,
                          snap.total_assets - (snap.total_liabilities + snap.total_equity))

        # get_balance_sheet_for_period reads it back without recomputing.
        via_selector = get_balance_sheet_for_period(period)
        self.assertEqual(via_selector["assets"]["total"], snap.total_assets)

    def test_period_without_snapshot_raises(self):
        with self.assertRaises(BalanceSheetSnapshot.DoesNotExist):
            get_balance_sheet_for_period("2020-01")

    # ---- Asset-side equity offsets ----------------------------------------
    # An asset can appear on the books with no cash paid and no liability
    # incurred. Every such path needs an equity counterpart or Assets
    # permanently outrun Liabilities + Equity. These were found by seeding
    # real asset activity, not by reading the code.

    def _depreciating_category(self, rate="0.10"):
        from assets.services import create_asset_category
        return create_asset_category(
            name=f"Machinery {rate}", valuation_method="depreciation",
            depreciation_rate=Decimal(rate), user=self.admin,
        )

    def _revaluing_category(self):
        from assets.services import create_asset_category
        return create_asset_category(
            name="Land", valuation_method="revaluation", user=self.admin,
        )

    def test_pre_owned_asset_does_not_unbalance_the_sheet(self):
        """
        acquisition_type='existing' is documented as "already owned before
        being registered. No cash movement." — an asset from nothing, exactly
        like data-entry Opening Stock. Without an equity offset the sheet is
        off by its cost. This is NOT go-live-only: it fires whenever anyone
        registers a pre-owned asset.
        """
        from assets.services import create_asset

        before = get_balance_sheet_live()
        self.assertTrue(before["is_balanced"])

        create_asset(
            name="Inherited Generator", category_id=self._revaluing_category().id,
            acquisition_type="existing", cost=Decimal("500000"),
            acquisition_date=timezone.localdate(), user=self.admin,
        )

        after = get_balance_sheet_live()
        self.assertEqual(after["equity"]["pre_owned_asset_equity"], Decimal("500000"))
        self.assertTrue(
            after["is_balanced"],
            f"pre-owned asset unbalanced the sheet by {after['balance_check']}",
        )

    def test_purchased_asset_gets_no_pre_owned_offset(self):
        """'new' assets are paid for in cash — the cash decrease and the asset
        increase already cancel, so adding an offset would DOUBLE count."""
        from assets.services import create_asset

        create_asset(
            name="New Forklift", category_id=self._revaluing_category().id,
            acquisition_type="new", cost=Decimal("300000"),
            acquisition_date=timezone.localdate(), user=self.admin, method_allocations=self.cash_split("300000"),

        )

        sheet = get_balance_sheet_live()
        self.assertEqual(sheet["equity"]["pre_owned_asset_equity"], Decimal("0"))
        self.assertTrue(sheet["is_balanced"], f"off by {sheet['balance_check']}")

    def test_revaluation_does_not_unbalance_the_sheet(self):
        """Only DEPRECIATION entries feed net profit, so a REVALUATION moves
        current_worth with nothing on the other side unless equity carries a
        revaluation surplus."""
        from assets.services import create_asset, revalue_asset

        asset = create_asset(
            name="Warehouse Plot", category_id=self._revaluing_category().id,
            acquisition_type="new", cost=Decimal("1000000"),
            acquisition_date=timezone.localdate(), user=self.admin, method_allocations=self.cash_split("1000000"),

        )
        revalue_asset(
            asset_id=asset.id, new_worth=Decimal("1250000"),
            revaluation_date=timezone.localdate(), user=self.admin,
        )

        sheet = get_balance_sheet_live()
        self.assertEqual(sheet["equity"]["asset_revaluation_surplus"], Decimal("250000"))
        self.assertTrue(sheet["is_balanced"], f"off by {sheet['balance_check']}")

    def test_downward_revaluation_reduces_the_surplus(self):
        """`amount` is stored signed, so a write-down must REDUCE the surplus
        rather than adding its absolute value."""
        from assets.services import create_asset, revalue_asset

        asset = create_asset(
            name="Old Plot", category_id=self._revaluing_category().id,
            acquisition_type="new", cost=Decimal("1000000"),
            acquisition_date=timezone.localdate(), user=self.admin, method_allocations=self.cash_split("1000000"),

        )
        revalue_asset(
            asset_id=asset.id, new_worth=Decimal("800000"),
            revaluation_date=timezone.localdate(), user=self.admin,
        )

        sheet = get_balance_sheet_live()
        self.assertEqual(sheet["equity"]["asset_revaluation_surplus"], Decimal("-200000"))
        self.assertTrue(sheet["is_balanced"], f"off by {sheet['balance_check']}")

    def test_scrapping_an_asset_does_not_unbalance_the_sheet(self):
        """
        Scrapping removes the asset's remaining book value with no sale
        proceeds. profits._compute_disposal_gain_loss used to filter
        disposal_type=SOLD only, so a scrapped asset's worth vanished from
        the asset side with nothing recorded as a loss.
        """
        from assets.services import create_asset, dispose_asset

        asset = create_asset(
            name="Crashed Van", category_id=self._revaluing_category().id,
            acquisition_type="new", cost=Decimal("400000"),
            acquisition_date=timezone.localdate(), user=self.admin, method_allocations=self.cash_split("400000"),

        )
        dispose_asset(
            asset_id=asset.id, disposal_type="scrapped",
            disposal_date=timezone.localdate(), user=self.admin,
        )

        sheet = get_balance_sheet_live()
        self.assertTrue(
            sheet["is_balanced"],
            f"scrapping unbalanced the sheet by {sheet['balance_check']}",
        )

    def test_scrapped_loss_reaches_the_income_statement(self):
        """The balance check alone could pass for the wrong reason — assert
        the loss actually appears as a loss, not just that things add up."""
        from assets.services import create_asset, dispose_asset
        from profits.services import _compute_disposal_gain_loss

        asset = create_asset(
            name="Burnt Compressor", category_id=self._revaluing_category().id,
            acquisition_type="new", cost=Decimal("250000"),
            acquisition_date=timezone.localdate(), user=self.admin, method_allocations=self.cash_split("250000"),

        )
        dispose_asset(
            asset_id=asset.id, disposal_type="scrapped",
            disposal_date=timezone.localdate(), user=self.admin,
        )

        today = timezone.localdate()
        first = today.replace(day=1)
        self.assertEqual(
            _compute_disposal_gain_loss(first, today), Decimal("-250000"),
            "a scrapped asset must be recorded as a loss of its book value",
        )

    def test_sold_asset_still_uses_its_stored_gain_loss(self):
        """Guards the scrapped fix against changing SOLD behaviour — sold
        disposals must keep the gain_loss computed at disposal time."""
        from assets.services import create_asset, dispose_asset
        from profits.services import _compute_disposal_gain_loss

        asset = create_asset(
            name="Resold Printer", category_id=self._revaluing_category().id,
            acquisition_type="new", cost=Decimal("100000"),
            acquisition_date=timezone.localdate(), user=self.admin, method_allocations=self.cash_split("100000"),

        )
        dispose_asset(
            asset_id=asset.id, disposal_type="sold",
            disposal_date=timezone.localdate(),
            sale_amount=Decimal("120000"), method_allocations=self.cash_split("120000"), user=self.admin,
        )

        today = timezone.localdate()
        self.assertEqual(
            _compute_disposal_gain_loss(today.replace(day=1), today), Decimal("20000"),
        )
        self.assertTrue(get_balance_sheet_live()["is_balanced"])

    # ---- Snapshot freshness (lag_days) --------------------------------------
    # A snapshot copies all-time singletons and stamps last month's label on
    # them, so a LATE one silently contains the following month's activity and
    # is frozen that way forever. These guard that the lag is surfaced.

    def _make_snapshot_taken_on(self, *, period, taken_on):
        """Freezes a snapshot for `period`, then forces computed_at to
        `taken_on` local time. computed_at is auto_now_add, so it has to be
        overwritten with .update() (which bypasses auto_now_add) rather than
        set on create."""
        from datetime import datetime, time as time_cls

        snap = BalanceSheetSnapshot.objects.create(period=period)
        aware = timezone.make_aware(
            datetime.combine(taken_on, time_cls(12, 0)),
            timezone.get_current_timezone(),
        )
        BalanceSheetSnapshot.objects.filter(pk=snap.pk).update(computed_at=aware)
        return snap

    def test_lag_days_is_small_when_snapshot_taken_promptly(self):
        # July 2026 ends the 31st; frozen Aug 1 => 1 day late, not stale.
        self._make_snapshot_taken_on(period="2026-07", taken_on=date(2026, 8, 1))
        freshness = get_balance_sheet_for_period("2026-07")["freshness"]

        self.assertTrue(freshness["is_snapshot"])
        self.assertEqual(freshness["lag_days"], 1)
        self.assertEqual(freshness["snapshot_taken_on"], date(2026, 8, 1))
        self.assertFalse(freshness["is_stale"])

    def test_lag_days_flags_a_late_snapshot_as_stale(self):
        # Frozen Aug 20 for July => 20 days of August bled into "July".
        self._make_snapshot_taken_on(period="2026-07", taken_on=date(2026, 8, 20))
        freshness = get_balance_sheet_for_period("2026-07")["freshness"]

        self.assertEqual(freshness["lag_days"], 20)
        self.assertTrue(freshness["is_stale"])

    def test_live_sheet_reports_no_snapshot_lag(self):
        """The live sheet reads the singletons directly, so lag is meaningless
        — it must report is_snapshot=False rather than a misleading 0."""
        freshness = get_balance_sheet_live()["freshness"]

        self.assertFalse(freshness["is_snapshot"])
        self.assertIsNone(freshness["lag_days"])
        self.assertIsNone(freshness["snapshot_taken_on"])
        self.assertFalse(freshness["is_stale"])

    def test_view_exposes_freshness(self):
        self._make_snapshot_taken_on(period="2026-07", taken_on=date(2026, 8, 20))
        request = self.factory.get("/api/accounting/balance-sheet/", {"period": "2026-07"})
        force_authenticate(request, user=self.admin)
        response = BalanceSheetView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["freshness"]["lag_days"], 20)
        self.assertTrue(response.data["freshness"]["is_stale"])

    def test_print_pdf_carries_the_stale_warning(self):
        """A printed PDF outlives the screen it came from, so the caveat has
        to travel with it — not just live on the page."""
        from .views import BalanceSheetPrintView

        self._make_snapshot_taken_on(period="2026-07", taken_on=date(2026, 8, 20))

        captured = {}
        import accounting.views as accounting_views
        original = accounting_views.generate_statement_pdf_bytes

        def _capture(**kwargs):
            captured.update(kwargs)
            return original(**kwargs)

        accounting_views.generate_statement_pdf_bytes = _capture
        try:
            request = self.factory.get(
                "/api/accounting/balance-sheet/print/", {"period": "2026-07"},
            )
            force_authenticate(request, user=self.admin)
            response = BalanceSheetPrintView.as_view()(request)
            self.assertEqual(response.status_code, 200)
        finally:
            accounting_views.generate_statement_pdf_bytes = original

        self.assertIn("WARNING", captured["filter_description"])
        self.assertIn("20 days", captured["filter_description"])

    def test_view_requires_admin(self):
        normal = make_normal_user()
        request = self.factory.get("/api/accounting/balance-sheet/")
        force_authenticate(request, user=normal)
        response = BalanceSheetView.as_view()(request)
        self.assertEqual(response.status_code, 403)

        request = self.factory.get("/api/accounting/balance-sheet/")
        force_authenticate(request, user=self.admin)
        response = BalanceSheetView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn("is_balanced", response.data)

    def test_view_404_for_period_without_snapshot(self):
        request = self.factory.get("/api/accounting/balance-sheet/", {"period": "2020-01"})
        force_authenticate(request, user=self.admin)
        response = BalanceSheetView.as_view()(request)
        self.assertEqual(response.status_code, 404)


# ---------------------------------------------------------------------------
# profits.compute_month_figures_in_one_query equivalence
# ---------------------------------------------------------------------------

class ProfitsCombinedQueryEquivalenceTests(AccountingTestBase):
    """
    The live current-month path now gets all ten month figures from ONE
    query instead of ten single-row aggregates (~1s of Supabase round-trips
    on every Income Statement / Balance Sheet load).

    The ten individual _compute_* helpers remain the single definition of
    each predicate and still drive the FROZEN monthly finalization, which is
    written once and never recomputed. This test is the contract between the
    two: if the combined query ever diverges from the helpers by so much as a
    rounding step, it fails here rather than silently mis-stating profit.

    Every figure is made non-zero on purpose — a test where all ten are 0
    would pass no matter how badly the query was wired.
    """

    def _build_a_month_with_every_figure_nonzero(self):
        from assets.services import (
            create_asset, create_asset_category, dispose_asset, revalue_asset,
        )
        from cash_management.services import create_cash_adjustment
        from recurring_expenses.services import (
            create_recurring_expense, create_recurring_expense_assignment,
            create_recurring_expense_category, create_recurring_expense_payment,
        )

        today = timezone.localdate()
        period = f"{today.year:04d}-{today.month:02d}"

        product = self.make_stocked_product(stock=50, unit_cost="50", selling_price="120")
        self.make_confirmed_invoice(product, quantity=5)

        cat = create_expense_category(name="Fuel", user=self.admin)
        create_expense(
            name="Diesel", category_id=cat.id, amount=Decimal("321.50"),
            expense_date=today, user=self.admin,
            method_allocations=self.cash_split("321.50"),
        )

        rcat = create_recurring_expense_category(name="Rent", user=self.admin)
        template = create_recurring_expense(
            name="Shop Rent", category_id=rcat.id, amount=Decimal("777.25"),
            start_date=today, user=self.admin,
        )
        assignment = create_recurring_expense_assignment(
            recurring_expense_id=template.id, period=period, user=self.admin,
        )
        create_recurring_expense_payment(
            assignment_id=assignment.id, amount=Decimal("777.25"),
            payment_date=today, method_allocations=self.cash_split("777.25"), user=self.admin,
        )

        for kind, amount in (("lost", "150.75"), ("found", "60.25")):
            create_cash_adjustment(
                adjustment_type=kind, amount=Decimal(amount),
                adjustment_date=today, method_allocations=self.cash_split(amount), reason="test", user=self.admin,
            )

        dep_cat = create_asset_category(
            name="Machines", valuation_method="depreciation",
            depreciation_rate=Decimal("0.12"), user=self.admin,
        )
        create_asset(
            name="Old Lathe", category_id=dep_cat.id, acquisition_type="existing",
            cost=Decimal("240000"),
            acquisition_date=today.replace(year=today.year - 1), user=self.admin,
        )

        rev_cat = create_asset_category(
            name="Vehicles", valuation_method="revaluation", user=self.admin,
        )
        sold = create_asset(
            name="Old Van", category_id=rev_cat.id, acquisition_type="new",
            cost=Decimal("90000"), acquisition_date=today, method_allocations=self.cash_split("90000"), user=self.admin,
        )
        dispose_asset(
            asset_id=sold.id, disposal_type="sold", disposal_date=today,
            sale_amount=Decimal("95000"), method_allocations=self.cash_split("95000"), user=self.admin,
        )
        scrapped = create_asset(
            name="Dead Van", category_id=rev_cat.id, acquisition_type="new",
            cost=Decimal("70000"), acquisition_date=today, method_allocations=self.cash_split("70000"), user=self.admin,
        )
        dispose_asset(
            asset_id=scrapped.id, disposal_type="scrapped",
            disposal_date=today, user=self.admin,
        )
        revalue_asset(
            asset_id=create_asset(
                name="Plot", category_id=rev_cat.id, acquisition_type="new",
                cost=Decimal("500000"), acquisition_date=today, method_allocations=self.cash_split("500000"), user=self.admin,
            ).id,
            new_worth=Decimal("560000"), revaluation_date=today, user=self.admin,
        )
        return period

    def test_combined_query_matches_the_ten_individual_helpers(self):
        from profits.services import (
            _compute_depreciation, _compute_disposal_gain_loss, _compute_expenses_paid,
            _compute_found_cash, _compute_found_inventory, _compute_gst_paid,
            _compute_lost_cash, _compute_lost_inventory, _month_bounds,
            _compute_recurring_expenses_paid, _compute_wht_paid,
            compute_month_figures_in_one_query,
        )

        period = self._build_a_month_with_every_figure_nonzero()
        first_day, _ = _month_bounds(period)
        last_day = timezone.localdate()

        combined = compute_month_figures_in_one_query(first_day, last_day, period)
        individual = {
            "expenses_paid": _compute_expenses_paid(first_day, last_day),
            "recurring_expenses_paid": _compute_recurring_expenses_paid(first_day, last_day),
            "gst_paid": _compute_gst_paid(first_day, last_day),
            "wht_paid": _compute_wht_paid(first_day, last_day),
            "lost_cash": _compute_lost_cash(first_day, last_day),
            "found_cash": _compute_found_cash(first_day, last_day),
            "lost_inventory": _compute_lost_inventory(first_day, last_day),
            "found_inventory": _compute_found_inventory(first_day, last_day),
            "depreciation": _compute_depreciation(period),
            "disposal_gain_loss": _compute_disposal_gain_loss(first_day, last_day),
        }

        for key, expected in individual.items():
            self.assertEqual(
                Decimal(combined[key]), Decimal(expected),
                f"combined query disagrees with _compute_{key} "
                f"({combined[key]} vs {expected})",
            )

        # Guard the guard: several figures must actually be non-zero, or the
        # comparison above proves nothing.
        nonzero = [k for k, v in individual.items() if Decimal(v) != 0]
        self.assertGreaterEqual(
            len(nonzero), 6,
            f"only {nonzero} were non-zero — this test would pass trivially",
        )

    def test_combined_query_is_one_query(self):
        """
        Measures STEADY STATE, which is the only state that matters here: the
        ProfitFlow singleton is created once in the system's lifetime, and on
        the very first call the read-first fallback legitimately costs a few
        extra queries (read miss -> get_or_create -> re-read). Every
        subsequent call — i.e. every real page load — is one statement.
        """
        from profits.models import ProfitFlow
        from profits.services import compute_month_figures_in_one_query, _month_bounds

        period = self._build_a_month_with_every_figure_nonzero()
        first_day, _ = _month_bounds(period)
        today = timezone.localdate()

        ProfitFlow.get_instance()   # bootstrap done, as it is in any live system
        compute_month_figures_in_one_query(first_day, today, period)

        with CaptureQueriesContext(connection) as ctx:
            compute_month_figures_in_one_query(first_day, today, period)

        self.assertEqual(
            len(ctx.captured_queries), 1,
            "the ten separate aggregates must collapse into exactly one "
            f"statement; got {len(ctx.captured_queries)}",
        )


# ---------------------------------------------------------------------------
# Data-entry opening balances belong in the aging reports
# ---------------------------------------------------------------------------

class AgingIncludesDataEntryTests(AccountingTestBase):
    """
    Both aging reports used to filter is_data_entry=False, which silently
    dropped every pre-go-live debt.

    Those are real balances, not bookkeeping artifacts: a customer opening
    balance is a CONFIRMED Invoice with credit_outstanding set, a supplier
    opening balance is a CONFIRMED PurchaseOrder with payable_outstanding set,
    and BOTH feed the CashFlow counters the Balance Sheet reports as Accounts
    Receivable and Accounts Payable. So the aging reports could never
    reconcile with the Balance Sheet, and money genuinely owed was missing
    from the collections list.
    """

    def test_customer_opening_balance_appears_in_ar_aging(self):
        ob = create_customer_opening_balance(
            customer_id=self.customer.id, amount=Decimal("7500"), user=self.admin,
        )
        rows = get_ar_aging_rows()
        matched = [r for r in rows if r["outstanding"] == Decimal("7500.0000")]
        self.assertEqual(
            len(matched), 1,
            "a customer opening balance is a real receivable and must be listed",
        )
        self.assertEqual(matched[0]["customer_name"], self.customer.name)
        self.assertEqual(ob.amount, Decimal("7500"))

    def test_supplier_opening_balance_appears_in_ap_aging(self):
        create_supplier_opening_balance(
            supplier_id=self.supplier.id, amount=Decimal("4200"), user=self.admin,
        )
        rows = get_ap_aging_rows()
        matched = [r for r in rows if r["outstanding"] == Decimal("4200.0000")]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["supplier_name"], self.supplier.name)

    def test_ar_aging_total_reconciles_with_the_balance_sheet(self):
        """The point of the fix: the report's grand total must equal the same
        Accounts Receivable figure the Balance Sheet shows."""
        product = self.make_stocked_product(stock=20)
        self.make_confirmed_invoice(product, quantity=3)
        create_customer_opening_balance(
            customer_id=self.customer.id, amount=Decimal("7500"), user=self.admin,
        )

        summary = get_ar_aging_summary()
        balance_sheet_ar = get_balance_sheet_live()["assets"]["accounts_receivable"]
        self.assertEqual(
            summary["grand_total"], balance_sheet_ar,
            "A/R Aging total must match the Balance Sheet's Accounts Receivable",
        )

    def test_ap_aging_total_reconciles_with_the_balance_sheet(self):
        product = self.make_stocked_product(stock=20)
        self.make_confirmed_purchase_order(product, quantity=4)
        create_supplier_opening_balance(
            supplier_id=self.supplier.id, amount=Decimal("4200"), user=self.admin,
        )

        summary = get_ap_aging_summary()
        balance_sheet_ap = get_balance_sheet_live()["liabilities"]["accounts_payable"]
        self.assertEqual(
            summary["grand_total"], balance_sheet_ap,
            "A/P Aging total must match the Balance Sheet's Accounts Payable",
        )

    def test_opening_STOCK_order_stays_out_of_ap_aging(self):
        """
        Opening stock orders are is_data_entry too, but they are NOT payables —
        create_opening_stock_order never calls _sync_order_payable, so
        payable_outstanding stays 0 and the `> 0` filter excludes them. This
        guards against the fix over-reaching and pulling inventory bootstrap
        rows into a list of debts.
        """
        from purchases.models import PurchaseOrder, Supplier

        product = self.make_stocked_product(stock=5)
        sys_supplier = create_supplier(name="Opening Stock", code="SYS-OPENING", user=self.admin)
        order = create_opening_stock_order(
            supplier=sys_supplier,
            items=[{"product_id": product.id, "quantity": 4,
                    "unit_price": Decimal("25"), "shelf_id": self.shelf.id}],
            user=self.admin,
        )
        order.refresh_from_db()
        self.assertEqual(order.payable_outstanding, Decimal("0"),
                         "opening stock must not create a payable")
        self.assertNotIn(
            order.id, {r["order_id"] for r in get_ap_aging_rows()},
            "opening STOCK is not a debt and must not appear in A/P aging",
        )
