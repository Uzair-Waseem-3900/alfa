from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from billing.models import Invoice, Payment
from billing.services import create_customer, update_customer
from purchases.models import PurchaseOrder, SupplierPayment
from purchases.services import create_supplier, update_supplier
from users.models import User

from .models import CustomerLedgerSnapshot, SupplierLedgerSnapshot
from .services import (
    add_customer_payment_entry, add_payment_entry, add_purchase_entry,
    add_sale_entry, remove_customer_ledger_entry_for_payment,
    remove_ledger_entry_for_payment,
)
from .views import (
    CustomerLedgerDetailView, CustomerLedgerListView,
    SupplierLedgerDetailView, SupplierLedgerListView,
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


class LedgerTestBase(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.admin = make_admin()
        # Through the service so the ledger is auto-created.
        self.supplier = create_supplier(name="Ali Traders", code="ALI", user=self.admin)
        self.ledger = self.supplier.ledger

    def add_purchase(self, amount, on_date, order_number="PO-2026-0001"):
        order = PurchaseOrder.objects.create(order_number=order_number, supplier=self.supplier)
        return add_purchase_entry(
            supplier=self.supplier, purchase_order=order,
            amount=Decimal(amount), date=on_date, user=self.admin,
        )

    def add_payment(self, amount, on_date, reference="SPY-2026-0001", order_number="PO-2026-0900"):
        order = PurchaseOrder.objects.create(order_number=order_number, supplier=self.supplier)
        payment = SupplierPayment.objects.create(
            order=order, reference_number=reference,
            amount=Decimal(amount), method="cash", payment_date=on_date,
        )
        return add_payment_entry(
            supplier=self.supplier, supplier_payment=payment,
            amount=Decimal(amount), date=on_date, user=self.admin,
        )

    def snapshot(self, year_month):
        return SupplierLedgerSnapshot.objects.get(ledger=self.ledger, year_month=year_month)


class SnapshotCorrectnessTests(LedgerTestBase):
    def test_single_month_snapshot(self):
        self.add_purchase("1000", date(2026, 6, 5))
        self.add_payment("400", date(2026, 6, 20))
        self.assertEqual(self.snapshot("2026-06").closing_balance, Decimal("600"))

    def test_backdated_entry_recalculates_later_months(self):
        self.add_purchase("1000", date(2026, 6, 5))
        self.add_payment("400", date(2026, 7, 10))
        self.assertEqual(self.snapshot("2026-06").closing_balance, Decimal("1000"))
        self.assertEqual(self.snapshot("2026-07").closing_balance, Decimal("600"))

        # Backdated June payment must ripple through July's snapshot too.
        self.add_payment("200", date(2026, 6, 25), reference="SPY-2026-0002", order_number="PO-2026-0901")
        self.assertEqual(self.snapshot("2026-06").closing_balance, Decimal("800"))
        self.assertEqual(self.snapshot("2026-07").closing_balance, Decimal("400"))

    def test_month_boundaries_land_in_correct_snapshots(self):
        # date__startswith → range rewrite must keep exact month boundaries:
        # Aug 31 belongs to August, Sep 1 to September.
        self.add_purchase("100", date(2026, 8, 31))
        self.add_purchase("50", date(2026, 9, 1), order_number="PO-2026-0002")
        self.assertEqual(self.snapshot("2026-08").closing_balance, Decimal("100"))
        self.assertEqual(self.snapshot("2026-09").closing_balance, Decimal("150"))

    def test_removing_payment_entry_recalculates(self):
        self.add_purchase("1000", date(2026, 6, 5))
        entry = self.add_payment("400", date(2026, 6, 20))
        remove_ledger_entry_for_payment(supplier_payment=entry.supplier_payment)
        self.assertEqual(self.snapshot("2026-06").closing_balance, Decimal("1000"))


class LedgerSnapshotSyncTests(LedgerTestBase):
    """update_supplier must keep SupplierLedger's name/code snapshot live
    while the supplier is active — found 2026-08-31: renaming/re-coding a
    supplier left its ledger showing the old name/code, and unreachable by
    ledger search (get_all_ledgers filters on the snapshot fields)."""

    def test_rename_propagates_to_ledger(self):
        update_supplier(pk=self.supplier.id, name="Renamed Traders", user=self.admin)
        self.ledger.refresh_from_db()
        self.assertEqual(self.ledger.supplier_name, "Renamed Traders")
        self.assertEqual(self.ledger.supplier_code, "ALI")

    def test_recode_propagates_to_ledger(self):
        update_supplier(pk=self.supplier.id, code="ALI2", user=self.admin)
        self.ledger.refresh_from_db()
        self.assertEqual(self.ledger.supplier_code, "ALI2")
        self.assertEqual(self.ledger.supplier_name, "Ali Traders")

    def test_renamed_supplier_findable_by_new_name_in_ledger_search(self):
        from .selectors import get_all_ledgers
        update_supplier(pk=self.supplier.id, name="Findable Traders", user=self.admin)
        self.assertTrue(get_all_ledgers(search="Findable").filter(pk=self.ledger.pk).exists())
        self.assertFalse(get_all_ledgers(search="Ali Traders").filter(pk=self.ledger.pk).exists())


class LedgerDetailViewTests(LedgerTestBase):
    def get_detail(self, **params):
        request = self.factory.get(f"/ledger/{self.ledger.pk}/", params)
        force_authenticate(request, user=self.admin)
        return SupplierLedgerDetailView.as_view()(request, pk=self.ledger.pk)

    def test_running_balance_full_history(self):
        self.add_purchase("1000", date(2026, 6, 5))
        self.add_payment("400", date(2026, 7, 10))

        response = self.get_detail()
        self.assertEqual(response.status_code, 200)
        balances = [r["balance"] for r in response.data["results"]]
        self.assertEqual(balances, ["1000.0000", "600.0000"])
        self.assertEqual(response.data["closing_balance"], Decimal("600"))

    def test_date_from_string_param_uses_snapshot_opening_balance(self):
        # date_from arrives as a raw query-param STRING — this path used to
        # crash on .strftime before reaching the snapshot logic.
        self.add_purchase("1000", date(2026, 6, 5))
        self.add_payment("400", date(2026, 7, 10))

        response = self.get_detail(date_from="2026-07-01")
        self.assertEqual(response.status_code, 200)
        # Only July's payment is shown, with the June closing balance
        # (1000) carried in — so its running balance is 600.
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["balance"], "600.0000")
        self.assertEqual(response.data["closing_balance"], Decimal("600"))

    def test_entry_type_filter_keeps_full_history_balances(self):
        self.add_purchase("1000", date(2026, 6, 5))
        self.add_payment("400", date(2026, 7, 10))

        response = self.get_detail(entry_type="payment")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)
        # The payment's balance still reflects the full history (1000 - 400).
        self.assertEqual(response.data["results"][0]["balance"], "600.0000")


class LedgerPermissionTests(LedgerTestBase):
    def test_normal_user_cannot_list_ledgers(self):
        request = self.factory.get("/ledger/")
        force_authenticate(request, user=make_normal_user())
        response = SupplierLedgerListView.as_view()(request)
        self.assertEqual(response.status_code, 403)

    def test_search_by_name_still_works(self):
        request = self.factory.get("/ledger/", {"search": "ali"})
        force_authenticate(request, user=self.admin)
        response = SupplierLedgerListView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["supplier_code"], "ALI")


# ---------------------------------------------------------------------------
# Customer ledger — mirrors the supplier ledger coverage above, direction
# flipped (sale=debit, payment=credit).
# ---------------------------------------------------------------------------

class CustomerLedgerTestBase(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.admin = make_admin()
        # Through the service so the ledger is auto-created.
        self.customer = create_customer(
            name="Bilal Stationers", code="BLS", address="Lahore", user=self.admin,
        )
        self.ledger = self.customer.ledger

    def add_sale(self, amount, on_date, bill_number="BILL-2026-0001"):
        invoice = Invoice.objects.create(
            bill_number=bill_number, customer=self.customer,
            status=Invoice.Status.CONFIRMED, grand_total=Decimal(amount),
            confirmed_at=None,
        )
        return add_sale_entry(
            customer=self.customer, invoice=invoice,
            amount=Decimal(amount), date=on_date, user=self.admin,
        )

    def add_payment(self, amount, on_date, reference="PAY-2026-0001", bill_number="BILL-2026-0900"):
        invoice = Invoice.objects.create(
            bill_number=bill_number, customer=self.customer,
            status=Invoice.Status.CONFIRMED, grand_total=Decimal(amount),
        )
        payment = Payment.objects.create(
            invoice=invoice, reference_number=reference,
            amount=Decimal(amount), method="cash", payment_date=on_date,
        )
        return add_customer_payment_entry(
            customer=self.customer, payment=payment,
            amount=Decimal(amount), date=on_date, user=self.admin,
        )

    def snapshot(self, year_month):
        return CustomerLedgerSnapshot.objects.get(ledger=self.ledger, year_month=year_month)


class CustomerLedgerDirectionTests(CustomerLedgerTestBase):
    def test_sale_is_a_debit_not_a_credit(self):
        entry = self.add_sale("1000", date(2026, 6, 5))
        self.assertEqual(entry.debit, Decimal("1000"))
        self.assertEqual(entry.credit, Decimal("0"))
        self.assertEqual(entry.entry_type, "sale")

    def test_payment_is_a_credit_not_a_debit(self):
        entry = self.add_payment("400", date(2026, 6, 20))
        self.assertEqual(entry.credit, Decimal("400"))
        self.assertEqual(entry.debit, Decimal("0"))
        self.assertEqual(entry.entry_type, "payment")


class CustomerLedgerSnapshotSyncTests(CustomerLedgerTestBase):
    """Mirrors LedgerSnapshotSyncTests — same bug, same fix, customer side."""

    def test_rename_propagates_to_ledger(self):
        update_customer(pk=self.customer.id, name="Renamed Stationers", user=self.admin)
        self.ledger.refresh_from_db()
        self.assertEqual(self.ledger.customer_name, "Renamed Stationers")
        self.assertEqual(self.ledger.customer_code, "BLS")

    def test_recode_propagates_to_ledger(self):
        update_customer(pk=self.customer.id, code="BLS2", user=self.admin)
        self.ledger.refresh_from_db()
        self.assertEqual(self.ledger.customer_code, "BLS2")

    def test_renamed_customer_findable_by_new_name_in_ledger_search(self):
        from .selectors import get_all_customer_ledgers
        update_customer(pk=self.customer.id, name="Findable Stationers", user=self.admin)
        self.assertTrue(get_all_customer_ledgers(search="Findable").filter(pk=self.ledger.pk).exists())
        self.assertFalse(get_all_customer_ledgers(search="Bilal Stationers").filter(pk=self.ledger.pk).exists())


class CustomerSnapshotCorrectnessTests(CustomerLedgerTestBase):
    def test_single_month_snapshot(self):
        self.add_sale("1000", date(2026, 6, 5))
        self.add_payment("400", date(2026, 6, 20))
        # Debit (sale) increases the balance, credit (payment) decreases it —
        # opposite of the supplier ledger's credit/debit roles.
        self.assertEqual(self.snapshot("2026-06").closing_balance, Decimal("600"))

    def test_backdated_entry_recalculates_later_months(self):
        self.add_sale("1000", date(2026, 6, 5))
        self.add_payment("400", date(2026, 7, 10))
        self.assertEqual(self.snapshot("2026-06").closing_balance, Decimal("1000"))
        self.assertEqual(self.snapshot("2026-07").closing_balance, Decimal("600"))

        self.add_payment("200", date(2026, 6, 25), reference="PAY-2026-0002", bill_number="BILL-2026-0901")
        self.assertEqual(self.snapshot("2026-06").closing_balance, Decimal("800"))
        self.assertEqual(self.snapshot("2026-07").closing_balance, Decimal("400"))

    def test_removing_payment_entry_recalculates(self):
        self.add_sale("1000", date(2026, 6, 5))
        entry = self.add_payment("400", date(2026, 6, 20))
        remove_customer_ledger_entry_for_payment(payment=entry.payment)
        self.assertEqual(self.snapshot("2026-06").closing_balance, Decimal("1000"))

    def test_removing_entry_for_a_payment_that_never_had_one_is_a_noop(self):
        # Mirrors the accept_return credit-note payment, which is never
        # given a payment-linked ledger entry (it's tracked via the Return
        # instead) — deleting it must not raise.
        invoice = Invoice.objects.create(
            bill_number="BILL-2026-0777", customer=self.customer,
            status=Invoice.Status.RETURNED, grand_total=Decimal("100"),
        )
        credit_note = Payment.objects.create(
            invoice=invoice, reference_number="PAY-2026-0777",
            amount=Decimal("-100"), method="cash", payment_date=date(2026, 6, 1),
        )
        remove_customer_ledger_entry_for_payment(payment=credit_note)  # must not raise


class CustomerLedgerDetailViewTests(CustomerLedgerTestBase):
    def get_detail(self, **params):
        request = self.factory.get(f"/ledger/customers/{self.ledger.pk}/", params)
        force_authenticate(request, user=self.admin)
        return CustomerLedgerDetailView.as_view()(request, pk=self.ledger.pk)

    def test_running_balance_full_history(self):
        self.add_sale("1000", date(2026, 6, 5))
        self.add_payment("400", date(2026, 7, 10))

        response = self.get_detail()
        self.assertEqual(response.status_code, 200)
        balances = [r["balance"] for r in response.data["results"]]
        self.assertEqual(balances, ["1000.0000", "600.0000"])
        self.assertEqual(response.data["closing_balance"], Decimal("600"))


class CustomerLedgerPermissionTests(CustomerLedgerTestBase):
    def test_normal_user_cannot_list_ledgers(self):
        request = self.factory.get("/ledger/customers/")
        force_authenticate(request, user=make_normal_user())
        response = CustomerLedgerListView.as_view()(request)
        self.assertEqual(response.status_code, 403)

    def test_search_by_name_still_works(self):
        request = self.factory.get("/ledger/customers/", {"search": "bilal"})
        force_authenticate(request, user=self.admin)
        response = CustomerLedgerListView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["customer_code"], "BLS")
