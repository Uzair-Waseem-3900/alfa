from decimal import Decimal

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory, force_authenticate

from users.models import User

from .models import AccountTransfer, PaymentAllocation, PaymentMethod
from .services import (
    create_method, delete_account_transfer, record_allocations,
    refresh_allocations, reverse_allocations, soft_delete_method,
    transfer_between_methods, update_method,
)
from .views import (
    AccountTransferListCreateView, PaymentMethodListCreateView,
    PaymentMethodRetrieveUpdateDestroyView,
)


def make_admin(email="admin@example.com"):
    return User.objects.create_user(
        email=email, password="Adm1n-secret!", first_name="Admin",
        last_name="User", is_staff=True,
    )


def make_normal_user(email="normal@example.com"):
    return User.objects.create_user(
        email=email, password="N0rmal-secret!", first_name="Normal", last_name="User",
    )


# ---------------------------------------------------------------------------
# Model / service tests
# ---------------------------------------------------------------------------

class PaymentMethodServiceTests(TestCase):
    def setUp(self):
        self.admin = make_admin()

    def test_create_method(self):
        m = create_method(name="JazzCash", account_number="0300-1234567", user=self.admin)
        self.assertEqual(m.name, "JazzCash")
        self.assertEqual(m.balance, Decimal("0"))
        self.assertFalse(m.is_protected)

    def test_duplicate_name_rejected_case_insensitive(self):
        create_method(name="JazzCash", user=self.admin)
        with self.assertRaises(ValidationError):
            create_method(name="jazzcash", user=self.admin)

    def test_blank_name_rejected(self):
        with self.assertRaises(ValidationError):
            create_method(name="   ", user=self.admin)

    def test_update_method_renames(self):
        m = create_method(name="Easypaisa", user=self.admin)
        updated = update_method(pk=m.pk, name="EasyPaisa Business", user=self.admin)
        self.assertEqual(updated.name, "EasyPaisa Business")

    def test_update_rejects_duplicate_name(self):
        create_method(name="Bank A", user=self.admin)
        m2 = create_method(name="Bank B", user=self.admin)
        with self.assertRaises(ValidationError):
            update_method(pk=m2.pk, name="Bank A", user=self.admin)

    def test_protected_method_cannot_be_renamed(self):
        cash = PaymentMethod.objects.create(name="Cash", is_protected=True)
        with self.assertRaises(ValidationError):
            update_method(pk=cash.pk, name="Not Cash", user=self.admin)

    def test_protected_method_cannot_be_deleted(self):
        cash = PaymentMethod.objects.create(name="Cash", is_protected=True)
        with self.assertRaises(ValidationError):
            soft_delete_method(pk=cash.pk, user=self.admin)

    def test_delete_blocked_while_balance_nonzero(self):
        m = PaymentMethod.objects.create(name="JazzCash", balance=Decimal("500"))
        with self.assertRaises(ValidationError):
            soft_delete_method(pk=m.pk, user=self.admin)
        m.refresh_from_db()
        self.assertFalse(m.is_deleted)

    def test_delete_allowed_at_exactly_zero_balance(self):
        m = PaymentMethod.objects.create(name="JazzCash", balance=Decimal("0"))
        soft_delete_method(pk=m.pk, user=self.admin)
        m.refresh_from_db()
        self.assertTrue(m.is_deleted)

    def test_soft_deleted_method_excluded_from_default_manager(self):
        m = PaymentMethod.objects.create(name="JazzCash", balance=Decimal("0"))
        soft_delete_method(pk=m.pk, user=self.admin)
        self.assertFalse(PaymentMethod.objects.filter(pk=m.pk).exists())
        self.assertTrue(PaymentMethod.all_objects.filter(pk=m.pk).exists())


# ---------------------------------------------------------------------------
# Backfill command tests
# ---------------------------------------------------------------------------

class SeedAndBackfillCommandTests(TestCase):
    def setUp(self):
        self.admin = make_admin()

    def test_creates_protected_cash_row_with_matching_balance(self):
        from data_entry.services import create_opening_cash
        create_opening_cash(amount=Decimal("10000"), user=self.admin)

        call_command("seed_and_backfill_payment_methods")

        cash = PaymentMethod.objects.get(name="Cash")
        self.assertTrue(cash.is_protected)
        self.assertEqual(cash.balance, Decimal("10000.0000"))

        from cash_flow.models import CashFlow
        self.assertEqual(cash.balance, CashFlow.get_instance().cash_in_hand)

    def test_backfills_one_allocation_per_active_cash_movement(self):
        from cash_flow.models import CashMovement
        from data_entry.services import create_opening_cash

        create_opening_cash(amount=Decimal("5000"), user=self.admin)
        expected_movements = CashMovement.objects.filter(is_deleted=False).count()

        call_command("seed_and_backfill_payment_methods")

        cash = PaymentMethod.objects.get(name="Cash")
        self.assertEqual(
            PaymentAllocation.objects.filter(payment_method=cash, is_deleted=False).count(),
            expected_movements,
        )

    def test_rerun_is_idempotent(self):
        from data_entry.services import create_opening_cash
        create_opening_cash(amount=Decimal("5000"), user=self.admin)

        call_command("seed_and_backfill_payment_methods")
        first_count = PaymentAllocation.objects.count()
        first_method_count = PaymentMethod.objects.count()

        call_command("seed_and_backfill_payment_methods")

        self.assertEqual(PaymentMethod.objects.count(), first_method_count)
        self.assertEqual(PaymentAllocation.objects.count(), first_count)

    def test_three_way_balance_cross_check(self):
        from django.db.models import Sum

        from data_entry.services import create_opening_cash
        from cash_flow.models import CashFlow
        from cash_management.services import create_investor, create_investor_transaction

        create_opening_cash(amount=Decimal("20000"), user=self.admin)
        cash_method = PaymentMethod.objects.get_or_create(name="Cash")[0]
        investor = create_investor(name="Bilal", user=self.admin)
        create_investor_transaction(
            investor_id=investor.id, transaction_type="investment",
            amount=Decimal("3000"), transaction_date="2026-01-01",
            method_allocations=[(cash_method, Decimal("3000"))], user=self.admin,
        )

        call_command("seed_and_backfill_payment_methods")

        cash = PaymentMethod.objects.get(name="Cash")
        cash_in_hand = CashFlow.get_instance().cash_in_hand

        inflow = PaymentAllocation.objects.filter(
            payment_method=cash, is_deleted=False, direction=PaymentAllocation.Direction.INFLOW,
        ).aggregate(t=Sum("amount"))["t"] or Decimal("0")
        outflow = PaymentAllocation.objects.filter(
            payment_method=cash, is_deleted=False, direction=PaymentAllocation.Direction.OUTFLOW,
        ).aggregate(t=Sum("amount"))["t"] or Decimal("0")

        self.assertEqual(cash.balance, cash_in_hand)
        self.assertEqual(inflow - outflow, cash_in_hand)


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

class PaymentMethodAPITests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.admin = make_admin()
        self.normal = make_normal_user()

    def test_non_admin_gets_403_on_create(self):
        request = self.factory.post("/payment-methods/", {"name": "JazzCash"}, format="json")
        force_authenticate(request, user=self.normal)
        response = PaymentMethodListCreateView.as_view()(request)
        self.assertEqual(response.status_code, 403)

    def test_admin_can_create_list_and_update(self):
        create_request = self.factory.post("/payment-methods/", {"name": "JazzCash"}, format="json")
        force_authenticate(create_request, user=self.admin)
        create_response = PaymentMethodListCreateView.as_view()(create_request)
        self.assertEqual(create_response.status_code, 201)
        method_id = create_response.data["id"]

        list_request = self.factory.get("/payment-methods/")
        force_authenticate(list_request, user=self.admin)
        list_response = PaymentMethodListCreateView.as_view()(list_request)
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.data["count"], 1)
        self.assertEqual(len(list_response.data["results"]), 1)

        patch_request = self.factory.patch(
            f"/payment-methods/{method_id}/", {"name": "JazzCash Business"}, format="json",
        )
        force_authenticate(patch_request, user=self.admin)
        patch_response = PaymentMethodRetrieveUpdateDestroyView.as_view()(patch_request, pk=method_id)
        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(patch_response.data["name"], "JazzCash Business")

    def test_protected_row_edit_and_delete_return_clean_400_not_500(self):
        cash = PaymentMethod.objects.create(name="Cash", is_protected=True)

        patch_request = self.factory.patch(
            f"/payment-methods/{cash.pk}/", {"name": "Not Cash"}, format="json",
        )
        force_authenticate(patch_request, user=self.admin)
        patch_response = PaymentMethodRetrieveUpdateDestroyView.as_view()(patch_request, pk=cash.pk)
        self.assertEqual(patch_response.status_code, 400)

        delete_request = self.factory.delete(f"/payment-methods/{cash.pk}/")
        force_authenticate(delete_request, user=self.admin)
        delete_response = PaymentMethodRetrieveUpdateDestroyView.as_view()(delete_request, pk=cash.pk)
        self.assertEqual(delete_response.status_code, 400)

    def test_delete_blocked_while_balance_nonzero_returns_400(self):
        m = PaymentMethod.objects.create(name="JazzCash", balance=Decimal("100"))
        delete_request = self.factory.delete(f"/payment-methods/{m.pk}/")
        force_authenticate(delete_request, user=self.admin)
        response = PaymentMethodRetrieveUpdateDestroyView.as_view()(delete_request, pk=m.pk)
        self.assertEqual(response.status_code, 400)


# ---------------------------------------------------------------------------
# Phase 2 — allocation engine tests
# ---------------------------------------------------------------------------

def make_dummy_source(pk=1):
    """A stand-in "source" row — record_allocations only needs
    ._meta.app_label/.model_name and .pk, same as cash_flow's
    record_cash_movement(source). Reuses cash_flow.Expense's category-less
    shape isn't needed; a plain object with the right attributes is enough
    and keeps these tests independent of any other app's models."""
    class _Meta:
        app_label = "billing"
        model_name = "payment"

    class _Source:
        _meta = _Meta()

        def __init__(self, pk):
            self.pk = pk

    return _Source(pk)


class AllocationEngineTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.cash = PaymentMethod.objects.get_or_create(name="Cash", defaults={"balance": Decimal("1000")})[0]
        self.jazzcash = PaymentMethod.objects.create(name="JazzCash", balance=Decimal("1000"))

    def test_single_method_inflow(self):
        source = make_dummy_source(1)
        record_allocations(
            source, direction="inflow", splits=[(self.cash, Decimal("200"))],
            total_amount=Decimal("200"), date="2026-01-01", user=self.admin,
        )
        self.cash.refresh_from_db()
        self.assertEqual(self.cash.balance, Decimal("1200"))
        self.assertEqual(PaymentAllocation.objects.filter(source_id=1).count(), 1)

    def test_single_method_outflow(self):
        source = make_dummy_source(2)
        record_allocations(
            source, direction="outflow", splits=[(self.cash, Decimal("300"))],
            total_amount=Decimal("300"), date="2026-01-01", user=self.admin,
        )
        self.cash.refresh_from_db()
        self.assertEqual(self.cash.balance, Decimal("700"))

    def test_split_inflow_updates_each_method_by_its_own_leg(self):
        source = make_dummy_source(3)
        record_allocations(
            source, direction="inflow",
            splits=[(self.cash, Decimal("400")), (self.jazzcash, Decimal("600"))],
            total_amount=Decimal("1000"), date="2026-01-01", user=self.admin,
        )
        self.cash.refresh_from_db()
        self.jazzcash.refresh_from_db()
        self.assertEqual(self.cash.balance, Decimal("1400"))
        self.assertEqual(self.jazzcash.balance, Decimal("1600"))
        self.assertEqual(PaymentAllocation.objects.filter(source_id=3).count(), 2)

    def test_split_outflow_one_leg_short_aborts_everything(self):
        source = make_dummy_source(4)
        with self.assertRaises(ValidationError) as ctx:
            record_allocations(
                source, direction="outflow",
                splits=[(self.cash, Decimal("300")), (self.jazzcash, Decimal("1600"))],
                total_amount=Decimal("1900"), date="2026-01-01", user=self.admin,
            )
        self.assertIn("JazzCash", str(ctx.exception.detail))

        self.cash.refresh_from_db()
        self.jazzcash.refresh_from_db()
        self.assertEqual(self.cash.balance, Decimal("1000"))
        self.assertEqual(self.jazzcash.balance, Decimal("1000"))
        self.assertEqual(PaymentAllocation.objects.filter(source_id=4).count(), 0)

    def test_split_outflow_two_legs_short_both_named(self):
        source = make_dummy_source(5)
        with self.assertRaises(ValidationError) as ctx:
            record_allocations(
                source, direction="outflow",
                splits=[(self.cash, Decimal("2000")), (self.jazzcash, Decimal("1600"))],
                total_amount=Decimal("3600"), date="2026-01-01", user=self.admin,
            )
        detail = str(ctx.exception.detail)
        self.assertIn("Cash", detail)
        self.assertIn("JazzCash", detail)

    def test_split_total_mismatch_rejected(self):
        source = make_dummy_source(6)
        with self.assertRaises(ValidationError):
            record_allocations(
                source, direction="inflow",
                splits=[(self.cash, Decimal("400")), (self.jazzcash, Decimal("600"))],
                total_amount=Decimal("999"), date="2026-01-01", user=self.admin,
            )

    def test_duplicate_method_in_splits_rejected(self):
        source = make_dummy_source(7)
        with self.assertRaises(ValidationError):
            record_allocations(
                source, direction="inflow",
                splits=[(self.cash, Decimal("100")), (self.cash, Decimal("100"))],
                total_amount=Decimal("200"), date="2026-01-01", user=self.admin,
            )

    def test_reverse_allocations_undoes_split(self):
        source = make_dummy_source(8)
        record_allocations(
            source, direction="inflow",
            splits=[(self.cash, Decimal("400")), (self.jazzcash, Decimal("600"))],
            total_amount=Decimal("1000"), date="2026-01-01", user=self.admin,
        )
        reverse_allocations(source)

        self.cash.refresh_from_db()
        self.jazzcash.refresh_from_db()
        self.assertEqual(self.cash.balance, Decimal("1000"))
        self.assertEqual(self.jazzcash.balance, Decimal("1000"))
        self.assertFalse(PaymentAllocation.objects.filter(source_id=8, is_deleted=False).exists())

    def test_reverse_allocations_of_inflow_can_go_negative(self):
        # Spend the money elsewhere first, then delete the original inflow.
        source_in = make_dummy_source(9)
        record_allocations(
            source_in, direction="inflow", splits=[(self.cash, Decimal("100"))],
            total_amount=Decimal("100"), date="2026-01-01", user=self.admin,
        )
        source_out = make_dummy_source(10)
        record_allocations(
            source_out, direction="outflow", splits=[(self.cash, Decimal("1050"))],
            total_amount=Decimal("1050"), date="2026-01-01", user=self.admin,
        )
        self.cash.refresh_from_db()
        self.assertEqual(self.cash.balance, Decimal("50"))

        # Now delete the original inflow — allowed to go negative, not blocked.
        reverse_allocations(source_in)
        self.cash.refresh_from_db()
        self.assertEqual(self.cash.balance, Decimal("-50"))

    def test_reverse_allocations_noop_when_nothing_to_reverse(self):
        source = make_dummy_source(11)
        reverse_allocations(source)  # must not raise
        self.cash.refresh_from_db()
        self.assertEqual(self.cash.balance, Decimal("1000"))

    def test_refresh_allocations_moves_split_to_new_amounts(self):
        source = make_dummy_source(12)
        record_allocations(
            source, direction="outflow",
            splits=[(self.cash, Decimal("400")), (self.jazzcash, Decimal("600"))],
            total_amount=Decimal("1000"), date="2026-01-01", user=self.admin,
        )
        refresh_allocations(
            source, direction="outflow",
            splits=[(self.cash, Decimal("300")), (self.jazzcash, Decimal("700"))],
            total_amount=Decimal("1000"), date="2026-01-02", user=self.admin,
        )
        self.cash.refresh_from_db()
        self.jazzcash.refresh_from_db()
        # Both started at 1000; old split (400/600) is fully reversed before
        # the new split (300/700) is applied, so the net effect is just the
        # final split subtracted from the original balances.
        self.assertEqual(self.cash.balance, Decimal("700"))
        self.assertEqual(self.jazzcash.balance, Decimal("300"))
        self.assertEqual(
            PaymentAllocation.objects.filter(source_id=12, is_deleted=False).count(), 2,
        )

    def test_refresh_allocations_enforces_balance_check_on_new_split(self):
        source = make_dummy_source(13)
        record_allocations(
            source, direction="outflow", splits=[(self.cash, Decimal("100"))],
            total_amount=Decimal("100"), date="2026-01-01", user=self.admin,
        )
        with self.assertRaises(ValidationError):
            refresh_allocations(
                source, direction="outflow",
                splits=[(self.jazzcash, Decimal("999999"))],
                total_amount=Decimal("999999"), date="2026-01-02", user=self.admin,
            )
        # Old split's reversal must not have stuck since the whole call rolled back.
        self.cash.refresh_from_db()
        self.assertEqual(self.cash.balance, Decimal("900"))
        self.assertTrue(PaymentAllocation.objects.filter(source_id=13, is_deleted=False).exists())

    def test_lock_order_matches_pk_order_regardless_of_splits_order(self):
        from .services import _lock_methods
        locked = _lock_methods([self.jazzcash.pk, self.cash.pk])
        self.assertEqual(list(locked.keys()), sorted([self.jazzcash.pk, self.cash.pk]))


# ---------------------------------------------------------------------------
# Phase 6 — Transfers
# ---------------------------------------------------------------------------

class AccountTransferServiceTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.cash = PaymentMethod.objects.get_or_create(name="Cash", defaults={"balance": Decimal("1000")})[0]
        self.jazzcash = PaymentMethod.objects.create(name="JazzCash", balance=Decimal("500"))

    def test_transfer_moves_both_balances_and_writes_two_allocations(self):
        transfer = transfer_between_methods(
            from_method_id=self.cash.id, to_method_id=self.jazzcash.id,
            amount=Decimal("300"), date="2026-01-01", user=self.admin,
        )
        self.cash.refresh_from_db()
        self.jazzcash.refresh_from_db()
        self.assertEqual(self.cash.balance, Decimal("700"))
        self.assertEqual(self.jazzcash.balance, Decimal("800"))

        allocations = PaymentAllocation.objects.filter(
            source_model="payment_methods.accounttransfer", source_id=transfer.id, is_deleted=False,
        )
        self.assertEqual(allocations.count(), 2)
        self.assertEqual(
            {(a.payment_method_id, a.direction) for a in allocations},
            {(self.cash.id, "outflow"), (self.jazzcash.id, "inflow")},
        )

    def test_self_transfer_rejected(self):
        with self.assertRaises(ValidationError):
            transfer_between_methods(
                from_method_id=self.cash.id, to_method_id=self.cash.id,
                amount=Decimal("100"), date="2026-01-01", user=self.admin,
            )

    def test_insufficient_balance_rejected_and_nothing_changes(self):
        with self.assertRaises(ValidationError) as ctx:
            transfer_between_methods(
                from_method_id=self.jazzcash.id, to_method_id=self.cash.id,
                amount=Decimal("999999"), date="2026-01-01", user=self.admin,
            )
        self.assertIn("JazzCash", str(ctx.exception.detail))

        self.cash.refresh_from_db()
        self.jazzcash.refresh_from_db()
        self.assertEqual(self.cash.balance, Decimal("1000"))
        self.assertEqual(self.jazzcash.balance, Decimal("500"))
        self.assertFalse(AccountTransfer.objects.exists())

    def test_transfer_never_touches_cash_in_hand(self):
        from cash_flow.models import CashFlow
        before = CashFlow.get_instance().cash_in_hand
        transfer_between_methods(
            from_method_id=self.cash.id, to_method_id=self.jazzcash.id,
            amount=Decimal("100"), date="2026-01-01", user=self.admin,
        )
        self.assertEqual(CashFlow.get_instance().cash_in_hand, before)

    def test_delete_reverses_both_balances(self):
        transfer = transfer_between_methods(
            from_method_id=self.cash.id, to_method_id=self.jazzcash.id,
            amount=Decimal("300"), date="2026-01-01", user=self.admin,
        )
        delete_account_transfer(pk=transfer.pk, user=self.admin)

        self.cash.refresh_from_db()
        self.jazzcash.refresh_from_db()
        self.assertEqual(self.cash.balance, Decimal("1000"))
        self.assertEqual(self.jazzcash.balance, Decimal("500"))
        self.assertFalse(
            PaymentAllocation.objects.filter(
                source_model="payment_methods.accounttransfer", source_id=transfer.id, is_deleted=False,
            ).exists(),
        )

    def test_lock_order_is_sorted_regardless_of_transfer_direction(self):
        # Guards the deadlock fix specifically: A→B and B→A must both lock
        # in the SAME order ([min(pk), max(pk)]), not the order the two
        # method ids happen to appear in the call.
        lo, hi = sorted([self.cash.id, self.jazzcash.id])

        from unittest.mock import patch
        from . import services as pm_services

        original = pm_services._lock_methods
        captured = []

        def spy(ids):
            captured.append(list(ids))
            return original(ids)

        with patch.object(pm_services, "_lock_methods", side_effect=spy):
            transfer_between_methods(
                from_method_id=self.jazzcash.id, to_method_id=self.cash.id,
                amount=Decimal("50"), date="2026-01-01", user=self.admin,
            )
        # The pre-lock call (first) must be sorted [lo, hi] even though this
        # transfer runs JazzCash→Cash (the "wrong" order if unsorted).
        self.assertEqual(captured[0], [lo, hi])


class AccountTransferAPITests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.admin = make_admin()
        self.cash = PaymentMethod.objects.get_or_create(name="Cash", defaults={"balance": Decimal("1000")})[0]
        self.jazzcash = PaymentMethod.objects.create(name="JazzCash", balance=Decimal("500"))

    def test_create_transfer_via_api(self):
        request = self.factory.post("/payment-methods/transfers/", {
            "from_method": self.cash.id, "to_method": self.jazzcash.id,
            "amount": "200", "date": "2026-01-01",
        }, format="json")
        force_authenticate(request, user=self.admin)
        response = AccountTransferListCreateView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.data["allocations"]), 2)

        self.cash.refresh_from_db()
        self.jazzcash.refresh_from_db()
        self.assertEqual(self.cash.balance, Decimal("800"))
        self.assertEqual(self.jazzcash.balance, Decimal("700"))

    def test_self_transfer_returns_400(self):
        request = self.factory.post("/payment-methods/transfers/", {
            "from_method": self.cash.id, "to_method": self.cash.id,
            "amount": "200", "date": "2026-01-01",
        }, format="json")
        force_authenticate(request, user=self.admin)
        response = AccountTransferListCreateView.as_view()(request)
        self.assertEqual(response.status_code, 400)

    def test_insufficient_balance_returns_400_not_500(self):
        request = self.factory.post("/payment-methods/transfers/", {
            "from_method": self.jazzcash.id, "to_method": self.cash.id,
            "amount": "999999", "date": "2026-01-01",
        }, format="json")
        force_authenticate(request, user=self.admin)
        response = AccountTransferListCreateView.as_view()(request)
        self.assertEqual(response.status_code, 400)


class AccountTransferQueryCountTests(TestCase):
    """architecture.md's STRICT O(1)-per-page rule — the allocations field
    on the transfer list view must not N+1 as row count grows."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.admin = make_admin()
        self.cash = PaymentMethod.objects.get_or_create(name="Cash", defaults={"balance": Decimal("100000")})[0]
        self.jazzcash = PaymentMethod.objects.create(name="JazzCash", balance=Decimal("100000"))

    def count_queries(self, view, url):
        request = self.factory.get(url)
        force_authenticate(request, user=self.admin)
        with CaptureQueriesContext(connection) as ctx:
            response = view(request)
            response.render()
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries)

    def test_transfer_list_query_count_flat(self):
        view = AccountTransferListCreateView.as_view()
        transfer_between_methods(
            from_method_id=self.cash.id, to_method_id=self.jazzcash.id,
            amount=Decimal("10"), date="2026-01-01", user=self.admin,
        )
        baseline = self.count_queries(view, "/payment-methods/transfers/")

        for _ in range(4):
            transfer_between_methods(
                from_method_id=self.cash.id, to_method_id=self.jazzcash.id,
                amount=Decimal("10"), date="2026-01-01", user=self.admin,
            )
        grown = self.count_queries(view, "/payment-methods/transfers/")
        self.assertEqual(baseline, grown)
