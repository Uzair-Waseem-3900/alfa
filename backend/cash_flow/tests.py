from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from users.models import User

from .models import CashFlow, CashMovement, Expense
from .selectors import (
    get_cash_flow_totals_up_to, get_cash_in_hand_breakdown,
    get_cash_in_hand_breakdown_from_sources,
)
from payment_methods.models import PaymentMethod

from .services import create_expense, delete_expense, update_expense
from .views import CashInHandBreakdownView, ExpenseListCreateView, ExpensesBreakdownView


def make_admin(email="admin@example.com"):
    return User.objects.create_user(
        email=email, password="Adm1n-secret!", first_name="Admin",
        last_name="User", is_staff=True,
    )


def _event_rows(**filters):
    """The event table shaped exactly like the drawer's response rows."""
    return [
        {
            "direction"  : m.direction,
            "type"       : m.movement_type,
            "date"       : str(m.date),
            "created_at" : m.occurred_at,
            "description": m.description,
            "reference"  : m.reference,
            "amount"     : m.amount,
            "method"     : m.method,
        }
        for m in get_cash_in_hand_breakdown(**filters)
    ]


def _normalize(rows):
    """Deterministic ordering for comparison — same sort key as the drawer
    (created_at desc, reference tie-break), with amounts normalized so
    Decimal('500') == Decimal('500.0000')."""
    out = []
    for r in rows:
        r = dict(r)
        r["amount"] = Decimal(r["amount"]).quantize(Decimal("0.0001"))
        out.append(r)
    return sorted(out, key=lambda r: (r["created_at"], r["reference"]), reverse=True)


class CashFlowTestBase(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.admin = make_admin()
        self.cash_method = PaymentMethod.objects.get_or_create(name="Cash", defaults={"balance": Decimal("1000000")})[0]

    def cash(self):
        return CashFlow.get_instance().cash_in_hand

    def cash_split(self, amount):
        return [(self.cash_method, Decimal(amount))]


class CashMovementOracleTests(CashFlowTestBase):
    """
    Builds a mix of cash events through the REAL services of every wired app,
    then asserts the CashMovement event table returns exactly what the
    original 14-source Python merge (kept as
    get_cash_in_hand_breakdown_from_sources — the oracle) produces.
    """

    def build_world(self):
        from assets.services import create_asset, create_asset_category, dispose_asset
        from billing.services import create_customer, create_payment
        from cash_management.services import (
            create_cash_adjustment, create_investor, create_investor_transaction,
            create_owner_transaction,
        )
        from data_entry.services import (
            create_customer_opening_balance, create_opening_cash,
            create_supplier_opening_balance,
        )
        from purchases.services import create_supplier, create_supplier_payment
        from recurring_expenses.services import (
            create_recurring_expense, create_recurring_expense_assignment,
            create_recurring_expense_category, create_recurring_expense_payment,
        )
        from taxes.services import create_tax_payment, create_wht_payment
        from .services import create_expense_category

        u = self.admin
        today = timezone.now().date()

        create_opening_cash(amount=Decimal("100000"), user=u)

        customer = create_customer(name="Ali Traders", code="CUST1", address="Lahore", user=u)
        cob = create_customer_opening_balance(customer_id=customer.id, amount=Decimal("5000"), user=u)
        create_payment(
            invoice_id=cob.invoice_id, amount=Decimal("3000"),
            method_allocations=self.cash_split("3000"), payment_date=today, user=u,
        )

        cat = create_expense_category(name="Utilities", user=u)
        # Backdated business date — exercises the drawer's date filter.
        create_expense(
            name="Electricity", category_id=cat.id, amount=Decimal("500"),
            expense_date=date(2026, 1, 15), method_allocations=self.cash_split("500"), user=u,
        )

        supplier = create_supplier(name="Karachi Metals", code="SUP1", user=u)
        sob = create_supplier_opening_balance(supplier_id=supplier.id, amount=Decimal("4000"), user=u)
        create_supplier_payment(
            order_id=sob.purchase_order_id, amount=Decimal("1500"),
            method_allocations=self.cash_split("1500"), payment_date=today, user=u,
        )

        create_tax_payment(amount=Decimal("200"), payment_date=today, method_allocations=self.cash_split("200"), note="Q1 GST", user=u)
        create_wht_payment(amount=Decimal("100"), payment_date=today, method_allocations=self.cash_split("100"), user=u)

        create_cash_adjustment(amount=Decimal("50"), adjustment_type="lost", adjustment_date=today, method_allocations=self.cash_split("50"), reason="till miscount", user=u)
        create_cash_adjustment(amount=Decimal("20"), adjustment_type="found", adjustment_date=today, method_allocations=self.cash_split("20"), user=u)

        investor = create_investor(name="Bilal", user=u)
        create_investor_transaction(
            investor_id=investor.id, transaction_type="investment",
            amount=Decimal("1000"), transaction_date=today, method_allocations=self.cash_split("1000"), user=u,
        )
        create_owner_transaction(transaction_type="contribution", amount=Decimal("800"), transaction_date=today, method_allocations=self.cash_split("800"), user=u)
        create_owner_transaction(transaction_type="drawing", amount=Decimal("300"), transaction_date=today, method_allocations=self.cash_split("300"), note="personal", user=u)

        asset_cat = create_asset_category(name="Machinery", valuation_method="none", user=u)
        new_asset = create_asset(
            name="Generator", category_id=asset_cat.id, acquisition_type="new",
            cost=Decimal("700"), acquisition_date=today, method_allocations=self.cash_split("700"), user=u,
        )
        # 'existing' asset — must NOT appear in the drawer.
        create_asset(
            name="Old Van", category_id=asset_cat.id, acquisition_type="existing",
            cost=Decimal("900"), acquisition_date=today, user=u,
        )
        dispose_asset(
            asset_id=new_asset.id, disposal_type="sold", disposal_date=today,
            sale_amount=Decimal("400"), method_allocations=self.cash_split("400"), user=u,
        )

        rec_cat = create_recurring_expense_category(name="Salaries", user=u)
        template = create_recurring_expense(
            name="Office Rent", category_id=rec_cat.id,
            amount=Decimal("250"), start_date=date(2026, 1, 1), user=u,
        )
        assignment = create_recurring_expense_assignment(
            recurring_expense_id=template.id, period="2026-08", user=u,
        )
        create_recurring_expense_payment(
            assignment_id=assignment.id, amount=Decimal("250"),
            payment_date=today, method_allocations=self.cash_split("250"), user=u,
        )

    def test_event_table_matches_source_oracle_exactly(self):
        self.build_world()

        oracle = get_cash_in_hand_breakdown_from_sources()
        events = _event_rows()
        self.assertEqual(len(events), len(oracle))
        self.assertEqual(_normalize(events), _normalize(oracle))

        # Filters agree too (movement_type + a date range that isolates the
        # backdated expense).
        for params in ({"movement_type": "outflow"}, {"date_to": "2026-06-30"}):
            self.assertEqual(
                _normalize(_event_rows(**params)),
                _normalize(get_cash_in_hand_breakdown_from_sources(**params)),
                params,
            )

        # Unfiltered header totals come from the O(1) singleton — they must
        # equal the oracle's sums, and reconcile with the till itself and
        # with the independent source-derived aggregator.
        cf = CashFlow.get_instance()
        oracle_in  = sum((m["amount"] for m in oracle if m["direction"] == "inflow"), Decimal("0"))
        oracle_out = sum((m["amount"] for m in oracle if m["direction"] == "outflow"), Decimal("0"))
        self.assertEqual(cf.total_cash_inflow, oracle_in)
        self.assertEqual(cf.total_cash_outflow, oracle_out)
        self.assertEqual(cf.total_cash_inflow - cf.total_cash_outflow, cf.cash_in_hand)
        totals = get_cash_flow_totals_up_to(None)
        self.assertEqual((totals["inflow"], totals["outflow"]), (oracle_in, oracle_out))

        # Stored dashboard counters equal what the old live COUNT queries
        # would have returned (same filters).
        from billing.models import Invoice
        from purchases.models import PurchaseOrder
        self.assertEqual(
            cf.total_invoices_count,
            Invoice.objects.filter(is_deleted=False, is_data_entry=False).exclude(status="draft").count(),
        )
        self.assertEqual(
            cf.total_purchases_count,
            PurchaseOrder.objects.filter(is_deleted=False, is_data_entry=False, status="confirmed").count(),
        )
        self.assertEqual(cf.total_expenses_count, 1)

        # The view responds with the same rows and DB-aggregated totals.
        request = self.factory.get("/cash-flow/breakdown/cash-in-hand/", {"date_to": "2026-06-30"})
        force_authenticate(request, user=self.admin)
        response = CashInHandBreakdownView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["type"], "expense")
        self.assertEqual(response.data["totals"]["total_outflow"], Decimal("500.0000"))

    def test_backfill_rebuilds_identical_events(self):
        self.build_world()
        before = _normalize(_event_rows())

        CashMovement.objects.all().delete()
        self.assertEqual(_event_rows(), [])

        call_command("backfill_cash_movements")
        self.assertEqual(_normalize(_event_rows()), before)


class ExpenseRoundTripTests(CashFlowTestBase):
    def setUp(self):
        super().setUp()
        from data_entry.services import create_opening_cash
        from .services import create_expense_category
        # Seed cash — cash_in_hand floors at 0, so deductions from an empty
        # till would vanish and hide round-trip errors.
        create_opening_cash(amount=Decimal("50000"), user=self.admin)
        self.category = create_expense_category(name="Utilities", user=self.admin)

    def test_create_update_delete_round_trip_with_events(self):
        cash_start = self.cash()

        expense = create_expense(
            name="Internet", category_id=self.category.id, amount=Decimal("2000"),
            expense_date=timezone.now().date(), method_allocations=self.cash_split("2000"), user=self.admin,
        )
        self.assertEqual(self.cash(), cash_start - Decimal("2000"))
        self.assertEqual(CashFlow.get_instance().total_expenses_count, 1)
        event = CashMovement.objects.get(source_model="cash_flow.expense", source_id=expense.id)
        self.assertEqual((event.direction, event.movement_type, event.amount, event.is_deleted),
                         ("outflow", "expense", Decimal("2000.0000"), False))
        self.assertEqual(event.description, "Expense: Internet (Utilities)")

        # Edit name + amount — cash adjusts by the difference, event follows.
        update_expense(pk=expense.pk, name="Fiber Internet", amount=Decimal("1500"), method_allocations=self.cash_split("1500"), user=self.admin)
        self.assertEqual(self.cash(), cash_start - Decimal("1500"))
        event.refresh_from_db()
        self.assertEqual(event.amount, Decimal("1500.0000"))
        self.assertEqual(event.description, "Expense: Fiber Internet (Utilities)")

        delete_expense(pk=expense.pk, user=self.admin)
        self.assertEqual(self.cash(), cash_start)
        self.assertEqual(CashFlow.get_instance().total_expenses_count, 0)
        event.refresh_from_db()
        self.assertTrue(event.is_deleted)
        self.assertEqual(len(_event_rows(movement_type="outflow")), 0)

    def test_delete_category_with_expenses_returns_400_not_500(self):
        from rest_framework.exceptions import ValidationError
        from .models import ExpenseCategory
        from .services import create_expense_category, delete_expense_category

        create_expense(
            name="Internet", category_id=self.category.id, amount=Decimal("100"),
            expense_date=timezone.now().date(), method_allocations=self.cash_split("100"), user=self.admin,
        )
        # Used category → friendly validation error (was an unhandled 500).
        with self.assertRaises(ValidationError):
            delete_expense_category(pk=self.category.pk)
        self.assertTrue(ExpenseCategory.objects.filter(pk=self.category.pk).exists())

        # Empty category still deletes fine.
        empty = create_expense_category(name="Unused", user=self.admin)
        delete_expense_category(pk=empty.pk)
        self.assertFalse(ExpenseCategory.objects.filter(pk=empty.pk).exists())

    def test_create_expense_rolls_back_completely_if_cash_sync_fails(self):
        cash_start = self.cash()
        with patch("cash_flow.services._adjust_cashflow", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                create_expense(
                    name="Doomed", category_id=self.category.id, amount=Decimal("100"),
                    expense_date=timezone.now().date(), method_allocations=self.cash_split("100"), user=self.admin,
                )
        # Nothing survives: no expense row, no event, cash untouched.
        self.assertEqual(Expense.objects.count(), 0)
        self.assertEqual(CashMovement.objects.filter(source_model="cash_flow.expense").count(), 0)
        self.assertEqual(self.cash(), cash_start)


class ExpenseAllocationQueryCountTests(CashFlowTestBase):
    """architecture.md's STRICT O(1)-per-page rule — Expense's allocations
    field must not N+1 as row count grows, on EITHER view that serializes
    a list of Expense rows: the main list AND the dashboard breakdown
    drawer (ExpensesBreakdownView reuses the same ExpenseReadSerializer —
    caught missing its own context injection by the Phase 6 performance
    audit, fixed in BreakdownTotalsMixin.list()).

    Writing this test also caught a second, PRE-EXISTING N+1 unrelated to
    payment_methods: get_all_expenses()'s select_related("category", ...)
    never chained into "category__created_by", so
    ExpenseCategoryReadSerializer's own created_by field (nested inside
    ExpenseReadSerializer.category) re-queried the category's creator once
    per row. Fixed alongside this test in cash_flow/selectors.py."""

    def setUp(self):
        super().setUp()
        from data_entry.services import create_opening_cash
        from .services import create_expense_category
        create_opening_cash(amount=Decimal("50000"), user=self.admin)
        self.category = create_expense_category(name="Utilities", user=self.admin)

    def count_queries(self, view, url):
        request = self.factory.get(url)
        force_authenticate(request, user=self.admin)
        with CaptureQueriesContext(connection) as ctx:
            response = view(request)
            response.render()
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries)

    def _make_expense(self, amount):
        create_expense(
            name="Electricity", category_id=self.category.id, amount=Decimal(amount),
            expense_date=timezone.now().date(), method_allocations=self.cash_split(amount), user=self.admin,
        )

    def test_expense_list_query_count_flat(self):
        view = ExpenseListCreateView.as_view()
        self._make_expense("10")
        baseline = self.count_queries(view, "/cash-flow/expenses/")

        for _ in range(4):
            self._make_expense("10")
        grown = self.count_queries(view, "/cash-flow/expenses/")
        self.assertEqual(baseline, grown)

    def test_expenses_breakdown_query_count_flat(self):
        view = ExpensesBreakdownView.as_view()
        self._make_expense("10")
        baseline = self.count_queries(view, "/cash-flow/breakdown/expenses/")

        for _ in range(4):
            self._make_expense("10")
        grown = self.count_queries(view, "/cash-flow/breakdown/expenses/")
        self.assertEqual(baseline, grown)


class DraftAdvanceQuirkFixTests(CashFlowTestBase):
    """Deleting a draft PO with an advance now cancels the advance payment
    row (and its ledger entry + drawer event) instead of only restoring the
    cash — fix approved 2026-08-03."""

    def test_deleting_draft_po_cancels_advance_everywhere(self):
        from data_entry.services import create_opening_cash
        from ledger.models import SupplierLedgerEntry
        from purchases.models import SupplierPayment
        from purchases.services import (
            create_category, create_product, create_purchase_order,
            create_shelf, create_supplier, delete_purchase_order,
            set_purchase_item_shelf_allocations,
        )

        create_opening_cash(amount=Decimal("50000"), user=self.admin)
        supplier = create_supplier(name="Karachi Metals", code="SUP1", user=self.admin)
        cat = create_category(name="Raw", user=self.admin)
        product = create_product(
            name="Steel Rod", code="PRD1", category_id=cat.id, user=self.admin,
        )
        shelf = create_shelf(name="Shelf A", user=self.admin)
        cash_start = self.cash()

        order = create_purchase_order(
            supplier_id=supplier.id,
            items=[{"product_id": product.id, "quantity": 10, "unit_price": Decimal("100")}],
            payment_type="advance", advance_amount=Decimal("600"),
            method_allocations=self.cash_split("600"), user=self.admin,
        )
        self.assertEqual(self.cash(), cash_start - Decimal("600"))

        payment = SupplierPayment.objects.get(order=order)
        event = CashMovement.objects.get(source_model="purchases.supplierpayment", source_id=payment.id)
        self.assertEqual((event.movement_type, event.amount), ("advance_payment", Decimal("600.0000")))
        self.assertEqual(SupplierLedgerEntry.objects.filter(supplier_payment=payment).count(), 1)

        delete_purchase_order(order_id=order.id, user=self.admin)

        # Cash restored AND payment row gone AND ledger entry gone AND event gone.
        self.assertEqual(self.cash(), cash_start)
        payment.refresh_from_db()
        self.assertTrue(payment.is_deleted)
        self.assertEqual(SupplierLedgerEntry.objects.filter(supplier_payment=payment).count(), 0)
        event.refresh_from_db()
        self.assertTrue(event.is_deleted)

        # Confirming a real order bumps the stored dashboard counter.
        from purchases.services import confirm_purchase_order
        order2 = create_purchase_order(
            supplier_id=supplier.id,
            items=[{"product_id": product.id, "quantity": 5, "unit_price": Decimal("100")}],
            user=self.admin,
        )
        for item in order2.items.all():
            set_purchase_item_shelf_allocations(
                purchase_item_id=item.id,
                allocations=[{"shelf_id": shelf.id, "quantity": item.quantity}],
                user=self.admin,
            )
        self.assertEqual(CashFlow.get_instance().total_purchases_count, 0)
        confirm_purchase_order(order_id=order2.id, user=self.admin)
        self.assertEqual(CashFlow.get_instance().total_purchases_count, 1)


# ---------------------------------------------------------------------------
# cash_in_hand is a live balance, not a cumulative counter
# ---------------------------------------------------------------------------

class CashInHandClampTests(CashFlowTestBase):
    """
    _adjust_cashflow used to do max(Decimal("0"), cash_in_hand + delta).

    When a movement would take cash negative the shortfall was DISCARDED, not
    deferred — later inflows then built on the clamped-up figure, so the error
    was permanent, cumulative, silent (no error, no log) and undetectable
    afterwards. On seeded test data it fired 152 times and fabricated ~21M of
    cash that never existed.

    A negative cash_in_hand is information: it means recorded outflows exceed
    recorded inflows, i.e. something is missing from the records. Showing it
    is strictly better than absorbing it, and it self-corrects the moment the
    missing inflow is entered.
    """

    def test_deficit_is_retained_not_discarded(self):
        from .services import _adjust_cashflow

        cf = CashFlow.get_instance()
        cf.cash_in_hand = Decimal("1000")
        cf.save(update_fields=["cash_in_hand"])

        _adjust_cashflow(cash_in_hand_delta=Decimal("-1500"), user=self.admin)

        cf.refresh_from_db()
        self.assertEqual(cf.cash_in_hand, Decimal("-500"))

    def test_deficit_self_corrects_when_the_missing_inflow_arrives(self):
        """The whole point: 1000 - 1500 + 2000 must land on 1500, not 2000.
        Under the clamp the 500 was invented and never went away."""
        from .services import _adjust_cashflow

        cf = CashFlow.get_instance()
        cf.cash_in_hand = Decimal("1000")
        cf.save(update_fields=["cash_in_hand"])

        _adjust_cashflow(cash_in_hand_delta=Decimal("-1500"), user=self.admin)
        _adjust_cashflow(cash_in_hand_delta=Decimal("2000"), user=self.admin)

        cf.refresh_from_db()
        self.assertEqual(
            cf.cash_in_hand, Decimal("1500"),
            "the clamp would leave 2000 here — 500 fabricated out of nothing",
        )

    def test_cumulative_counters_keep_their_floor(self):
        """Guards against over-correcting — the one-way totals should still be
        floored, since a negative there is meaningless rather than
        informative."""
        from .services import _adjust_cashflow

        cf = CashFlow.get_instance()
        cf.total_paid_payables = Decimal("100")
        cf.save(update_fields=["total_paid_payables"])

        _adjust_cashflow(total_paid_payables_delta=Decimal("-999"), user=self.admin)

        cf.refresh_from_db()
        self.assertEqual(cf.total_paid_payables, Decimal("0"))
