from decimal import Decimal

from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory, force_authenticate

from users.models import User

from payment_methods.models import PaymentAllocation, PaymentMethod

from .models import CashManagementFlow, Investor, InvestorValuationEntry
from .selectors import get_all_investors, get_cash_management_stats
from .services import (
    _add_months, create_cash_adjustment, create_investor,
    create_investor_transaction, create_owner_transaction,
    delete_cash_adjustment, delete_investor, delete_investor_transaction,
    delete_owner_transaction,
)
from .views import (
    CashAdjustmentListCreateView, InvestorTransactionListCreateView,
    OwnerTransactionListCreateView,
)


def make_admin(email="admin@example.com"):
    return User.objects.create_user(
        email=email, password="Adm1n-secret!", first_name="Admin",
        last_name="User", is_staff=True,
    )


class InvestorGrowthCatchUpTests(TestCase):
    """The month-marker gate must skip work when current and post the exact
    same compounded entries as the old per-request loop when stale."""

    def setUp(self):
        self.admin = make_admin()
        from data_entry.services import create_opening_cash
        create_opening_cash(amount=Decimal("50000"), user=self.admin)
        self.cash = PaymentMethod.objects.get_or_create(name="Cash", defaults={"balance": Decimal("1000000")})[0]

        # 12%/year → 1%/month, invested 1000.
        self.investor = create_investor(name="Bilal", growth_rate=Decimal("0.12"), user=self.admin)
        create_investor_transaction(
            investor_id=self.investor.id, transaction_type="investment",
            amount=Decimal("1000"), transaction_date=timezone.now().date(),
            method_allocations=[(self.cash, Decimal("1000"))], user=self.admin,
        )

    def _backdate_two_months_and_reset_marker(self):
        today = timezone.localdate()
        y, m = _add_months(today.year, today.month, -2)
        Investor.objects.filter(pk=self.investor.pk).update(
            created_at=timezone.now().replace(year=y, month=m, day=1),
        )
        CashManagementFlow.objects.filter(pk=1).update(growth_caught_up_through="")

    def test_stale_marker_posts_compounded_months_then_goes_idle(self):
        self._backdate_two_months_and_reset_marker()

        get_cash_management_stats()

        # Two elapsed months at 1%: 1000 → 1010 → 1020.10, one entry each.
        entries = InvestorValuationEntry.objects.filter(investor=self.investor).order_by("period")
        self.assertEqual(entries.count(), 2)
        self.assertEqual(entries[0].amount, Decimal("10.0000"))
        self.assertEqual(entries[1].amount, Decimal("10.1000"))
        self.investor.refresh_from_db()
        self.assertEqual(self.investor.current_worth, Decimal("1020.1000"))

        # Marker stamped with the current month → subsequent reads post nothing.
        today = timezone.localdate()
        cmf = CashManagementFlow.get_instance()
        self.assertEqual(cmf.growth_caught_up_through, f"{today.year:04d}-{today.month:02d}")
        get_cash_management_stats()
        get_all_investors()
        self.assertEqual(InvestorValuationEntry.objects.filter(investor=self.investor).count(), 2)

    def test_duplicate_month_posting_is_impossible(self):
        self._backdate_two_months_and_reset_marker()
        get_cash_management_stats()
        entry = InvestorValuationEntry.objects.filter(investor=self.investor).first()

        # uniq_investor_valuation_period — the DB refuses a second row for
        # the same investor+month, so concurrent catch-ups can't double-post.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InvestorValuationEntry.objects.create(
                    investor=self.investor, period=entry.period,
                    rate_applied=entry.rate_applied, worth_before=0, worth_after=0, amount=0,
                )


class DeleteInvestorGuardTests(TestCase):
    def test_delete_blocked_with_transactions_allowed_without(self):
        admin = make_admin()
        from data_entry.services import create_opening_cash
        create_opening_cash(amount=Decimal("10000"), user=admin)
        cash = PaymentMethod.objects.get_or_create(name="Cash", defaults={"balance": Decimal("1000000")})[0]

        investor = create_investor(name="Bilal", user=admin)
        create_investor_transaction(
            investor_id=investor.id, transaction_type="investment",
            amount=Decimal("500"), transaction_date=timezone.now().date(),
            method_allocations=[(cash, Decimal("500"))], user=admin,
        )
        with self.assertRaises(ValidationError):
            delete_investor(pk=investor.pk, user=admin)

        empty = create_investor(name="Sara", user=admin)
        delete_investor(pk=empty.pk, user=admin)
        empty.refresh_from_db()
        self.assertTrue(empty.is_deleted)


class SearchTests(TestCase):
    def test_investor_search_via_search_q(self):
        admin = make_admin()
        create_investor(name="Bilal Ahmed", email="bilal@x.com", user=admin)
        create_investor(name="Sara Khan", contact_number="0300-1234567", user=admin)

        self.assertEqual([i.name for i in get_all_investors(search="BILAL")], ["Bilal Ahmed"])
        self.assertEqual([i.name for i in get_all_investors(search="1234")], ["Sara Khan"])
        self.assertEqual(list(get_all_investors(search="nomatch")), [])


# ---------------------------------------------------------------------------
# Phase 5 Batch A — payment_methods wiring
# ---------------------------------------------------------------------------

class CashManagementAllocationTests(TestCase):
    """CashAdjustment/InvestorTransaction/OwnerTransaction now require a
    method split, same as billing/purchases (Phase 3) and profits (Phase 4).
    is_data_entry InvestorTransactions are the one exception (no real cash
    moves, so no method is required)."""

    def setUp(self):
        self.admin = make_admin()
        self.cash = PaymentMethod.objects.get_or_create(name="Cash", defaults={"balance": Decimal("1000000")})[0]

    def cash_split(self, amount):
        return [(self.cash, Decimal(amount))]

    def test_cash_adjustment_without_method_allocations_rejected(self):
        with self.assertRaises(ValidationError):
            create_cash_adjustment(
                amount=Decimal("50"), adjustment_type="lost",
                adjustment_date=timezone.now().date(), method_allocations=None, user=self.admin,
            )

    def test_cash_adjustment_round_trip_moves_and_restores_balance(self):
        adj = create_cash_adjustment(
            amount=Decimal("50"), adjustment_type="lost", adjustment_date=timezone.now().date(),
            method_allocations=self.cash_split("50"), user=self.admin,
        )
        self.cash.refresh_from_db()
        self.assertEqual(self.cash.balance, Decimal("999950"))

        delete_cash_adjustment(pk=adj.pk, user=self.admin)
        self.cash.refresh_from_db()
        self.assertEqual(self.cash.balance, Decimal("1000000"))
        self.assertFalse(
            PaymentAllocation.objects.filter(
                source_model="cash_management.cashadjustment", source_id=adj.id, is_deleted=False,
            ).exists(),
        )

    def test_investor_transaction_without_method_allocations_rejected(self):
        investor = create_investor(name="Bilal", user=self.admin)
        with self.assertRaises(ValidationError):
            create_investor_transaction(
                investor_id=investor.id, transaction_type="investment",
                amount=Decimal("100"), transaction_date=timezone.now().date(), user=self.admin,
            )

    def test_investor_transaction_is_data_entry_skips_method_requirement(self):
        investor = create_investor(name="Bilal", user=self.admin)
        txn = create_investor_transaction(
            investor_id=investor.id, transaction_type="investment",
            amount=Decimal("100"), transaction_date=timezone.now().date(),
            user=self.admin, is_data_entry=True,
        )
        self.cash.refresh_from_db()
        self.assertEqual(self.cash.balance, Decimal("1000000"))  # untouched
        self.assertFalse(
            PaymentAllocation.objects.filter(
                source_model="cash_management.investortransaction", source_id=txn.id,
            ).exists(),
        )

    def test_investor_transaction_round_trip_moves_and_restores_balance(self):
        investor = create_investor(name="Bilal", user=self.admin)
        txn = create_investor_transaction(
            investor_id=investor.id, transaction_type="investment",
            amount=Decimal("100"), transaction_date=timezone.now().date(),
            method_allocations=self.cash_split("100"), user=self.admin,
        )
        self.cash.refresh_from_db()
        self.assertEqual(self.cash.balance, Decimal("1000100"))

        delete_investor_transaction(pk=txn.pk, user=self.admin)
        self.cash.refresh_from_db()
        self.assertEqual(self.cash.balance, Decimal("1000000"))

    def test_owner_transaction_without_method_allocations_rejected(self):
        with self.assertRaises(ValidationError):
            create_owner_transaction(
                transaction_type="contribution", amount=Decimal("100"),
                transaction_date=timezone.now().date(), method_allocations=None, user=self.admin,
            )

    def test_owner_transaction_round_trip_moves_and_restores_balance(self):
        txn = create_owner_transaction(
            transaction_type="drawing", amount=Decimal("100"), transaction_date=timezone.now().date(),
            method_allocations=self.cash_split("100"), user=self.admin,
        )
        self.cash.refresh_from_db()
        self.assertEqual(self.cash.balance, Decimal("999900"))

        delete_owner_transaction(pk=txn.pk, user=self.admin)
        self.cash.refresh_from_db()
        self.assertEqual(self.cash.balance, Decimal("1000000"))


class CashManagementAllocationQueryCountTests(TestCase):
    """architecture.md's STRICT O(1)-per-page rule — the allocations field
    on each list view must not N+1 as row count grows."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.admin = make_admin()
        self.cash = PaymentMethod.objects.get_or_create(name="Cash", defaults={"balance": Decimal("1000000")})[0]

    def cash_split(self, amount):
        return [(self.cash, Decimal(amount))]

    def count_queries(self, view, url):
        request = self.factory.get(url)
        force_authenticate(request, user=self.admin)
        with CaptureQueriesContext(connection) as ctx:
            response = view(request)
            response.render()
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries)

    def test_cash_adjustment_list_query_count_flat(self):
        view = CashAdjustmentListCreateView.as_view()
        create_cash_adjustment(
            amount=Decimal("10"), adjustment_type="lost", adjustment_date=timezone.now().date(),
            method_allocations=self.cash_split("10"), user=self.admin,
        )
        baseline = self.count_queries(view, "/cash-management/adjustments/")

        for _ in range(4):
            create_cash_adjustment(
                amount=Decimal("10"), adjustment_type="lost", adjustment_date=timezone.now().date(),
                method_allocations=self.cash_split("10"), user=self.admin,
            )
        grown = self.count_queries(view, "/cash-management/adjustments/")
        self.assertEqual(baseline, grown)

    def test_investor_transaction_list_query_count_flat(self):
        view = InvestorTransactionListCreateView.as_view()
        investor = create_investor(name="Bilal", user=self.admin)
        create_investor_transaction(
            investor_id=investor.id, transaction_type="investment", amount=Decimal("10"),
            transaction_date=timezone.now().date(), method_allocations=self.cash_split("10"), user=self.admin,
        )
        baseline = self.count_queries(view, "/cash-management/investor-transactions/")

        for _ in range(4):
            create_investor_transaction(
                investor_id=investor.id, transaction_type="investment", amount=Decimal("10"),
                transaction_date=timezone.now().date(), method_allocations=self.cash_split("10"), user=self.admin,
            )
        grown = self.count_queries(view, "/cash-management/investor-transactions/")
        self.assertEqual(baseline, grown)

    def test_owner_transaction_list_query_count_flat(self):
        view = OwnerTransactionListCreateView.as_view()
        create_owner_transaction(
            transaction_type="contribution", amount=Decimal("10"), transaction_date=timezone.now().date(),
            method_allocations=self.cash_split("10"), user=self.admin,
        )
        baseline = self.count_queries(view, "/cash-management/owner-transactions/")

        for _ in range(4):
            create_owner_transaction(
                transaction_type="contribution", amount=Decimal("10"), transaction_date=timezone.now().date(),
                method_allocations=self.cash_split("10"), user=self.admin,
            )
        grown = self.count_queries(view, "/cash-management/owner-transactions/")
        self.assertEqual(baseline, grown)
