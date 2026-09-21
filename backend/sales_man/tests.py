from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory, force_authenticate

from users.models import User

from billing.models import Customer, Invoice, Payment
from billing.services import (
    _sync_invoice_payment_summary,
    create_customer,
    delete_customer,
    update_customer,
)
from .models import SalesMan, SalesManLinkName
from .services import (
    _adjust_sales_man_stats,
    create_link_name,
    create_sales_man,
    delete_link_name,
    delete_sales_man,
)
from .views import SalesManListCreateView, SalesManRetrieveUpdateDestroyView


def make_admin(email="admin@example.com"):
    return User.objects.create_user(
        email=email, password="Adm1n-secret!", first_name="Admin",
        last_name="User", is_staff=True,
    )


def make_user(email="user@example.com"):
    return User.objects.create_user(
        email=email, password="Us3r-secret!", first_name="Normal",
        last_name="User", is_staff=False,
    )


class SalesManCoreTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.sm1 = create_sales_man(name="sale_man_1", code="SM1", user=self.admin)
        self.link_fsd = create_link_name(sales_man_id=self.sm1.id, name="FSD", user=self.admin)

    def test_link_name_and_sales_man_created(self):
        self.sm1.refresh_from_db()
        self.assertEqual(self.link_fsd.sales_man_id, self.sm1.id)
        self.assertEqual(self.link_fsd.name, "FSD")

    def test_adjust_sales_man_stats_is_additive(self):
        _adjust_sales_man_stats(sales_man_id=self.sm1.id, customer_delta=3, outstanding_delta=Decimal("150"))
        _adjust_sales_man_stats(sales_man_id=self.sm1.id, customer_delta=-1, outstanding_delta=Decimal("-50"))
        self.sm1.refresh_from_db()
        self.assertEqual(self.sm1.total_customers, 2)
        self.assertEqual(self.sm1.total_outstanding, Decimal("100"))

    def test_delete_link_name_blocked_when_customers_assigned(self):
        create_customer(
            name="Cust A", sales_man_link_name_id=self.link_fsd.id, code_suffix="001",
            address="addr", user=self.admin,
        )
        with self.assertRaises(ValidationError):
            delete_link_name(pk=self.link_fsd.id, user=self.admin)

    def test_delete_link_name_allowed_when_empty(self):
        delete_link_name(pk=self.link_fsd.id, user=self.admin)
        self.link_fsd.refresh_from_db()
        self.assertTrue(self.link_fsd.is_deleted)

    def test_delete_sales_man_blocked_with_customers(self):
        create_customer(
            name="Cust A", sales_man_link_name_id=self.link_fsd.id, code_suffix="001",
            address="addr", user=self.admin,
        )
        with self.assertRaises(ValidationError):
            delete_sales_man(pk=self.sm1.id, user=self.admin)

    def test_delete_sales_man_cascades_link_names_when_empty(self):
        link2 = create_link_name(sales_man_id=self.sm1.id, name="XYZ", user=self.admin)
        delete_sales_man(pk=self.sm1.id, user=self.admin)
        self.sm1.refresh_from_db()
        self.link_fsd.refresh_from_db()
        link2.refresh_from_db()
        self.assertTrue(self.sm1.is_deleted)
        self.assertTrue(self.link_fsd.is_deleted)
        self.assertTrue(link2.is_deleted)


class CustomerCodeAndStatsWiringTests(TestCase):
    """
    Verifies billing.services' hooks into sales_man's O(1) stat counters —
    the cross-app wiring this feature depends on, not billing's own FIFO/
    payment machinery (out of scope here).
    """

    def setUp(self):
        self.admin = make_admin()
        self.sm1 = create_sales_man(name="sale_man_1", code="SM1", user=self.admin)
        self.sm2 = create_sales_man(name="sale_man_2", code="SM2", user=self.admin)
        self.link_fsd = create_link_name(sales_man_id=self.sm1.id, name="FSD", user=self.admin)
        self.link_os = create_link_name(sales_man_id=self.sm2.id, name="OS", user=self.admin)

    def test_create_customer_composes_code_and_bumps_total_customers(self):
        customer = create_customer(
            name="Cust A", sales_man_link_name_id=self.link_fsd.id, code_suffix="001",
            address="addr", user=self.admin,
        )
        self.assertEqual(customer.code, "ALFA-FSD-001")
        self.assertEqual(customer.sales_man_id, self.sm1.id)
        self.sm1.refresh_from_db()
        self.assertEqual(self.sm1.total_customers, 1)

    def test_delete_customer_decrements_stats(self):
        customer = create_customer(
            name="Cust A", sales_man_link_name_id=self.link_fsd.id, code_suffix="001",
            address="addr", user=self.admin,
        )
        Invoice.objects.create(
            bill_number="BILL-TEST-0001", customer=customer, status=Invoice.Status.CONFIRMED,
            grand_total=Decimal("500"), credit_outstanding=Decimal("500"),
            remaining_amount=Decimal("500"),
        )
        self.sm1.refresh_from_db()
        self.assertEqual(self.sm1.total_customers, 1)  # from create_customer's own +1
        delete_customer(pk=customer.id, user=self.admin)
        self.sm1.refresh_from_db()
        self.assertEqual(self.sm1.total_customers, 0)
        self.assertEqual(self.sm1.total_outstanding, Decimal("-500"))  # decremented by the customer's outstanding at delete time

    def test_reassign_link_name_regenerates_code_and_moves_stats(self):
        customer = create_customer(
            name="Cust A", sales_man_link_name_id=self.link_fsd.id, code_suffix="001",
            address="addr", user=self.admin,
        )
        Invoice.objects.create(
            bill_number="BILL-TEST-0002", customer=customer, status=Invoice.Status.CONFIRMED,
            grand_total=Decimal("300"), credit_outstanding=Decimal("300"),
            remaining_amount=Decimal("300"),
        )
        updated = update_customer(pk=customer.id, sales_man_link_name_id=self.link_os.id, user=self.admin)
        self.assertEqual(updated.code, "ALFA-OS-001")
        self.assertEqual(updated.sales_man_id, self.sm2.id)

        self.sm1.refresh_from_db()
        self.sm2.refresh_from_db()
        self.assertEqual(self.sm1.total_customers, 0)
        self.assertEqual(self.sm1.total_outstanding, Decimal("-300"))
        self.assertEqual(self.sm2.total_customers, 1)
        self.assertEqual(self.sm2.total_outstanding, Decimal("300"))

    def test_sync_invoice_payment_summary_adjusts_outstanding(self):
        customer = create_customer(
            name="Cust A", sales_man_link_name_id=self.link_fsd.id, code_suffix="002",
            address="addr", user=self.admin,
        )
        invoice = Invoice.objects.create(
            bill_number="BILL-TEST-0003", customer=customer, status=Invoice.Status.CONFIRMED,
            grand_total=Decimal("1000"), credit_outstanding=Decimal("1000"),
            remaining_amount=Decimal("1000"),
        )
        Payment.objects.create(
            invoice=invoice, reference_number="PAY-TEST-0001", amount=Decimal("400"),
            method=Payment.Method.CASH, payment_date="2026-01-01",
        )
        _sync_invoice_payment_summary(invoice)
        invoice.refresh_from_db()
        self.assertEqual(invoice.credit_outstanding, Decimal("600"))
        self.sm1.refresh_from_db()
        self.assertEqual(self.sm1.total_outstanding, Decimal("-400"))  # dropped by the payment amount

    def test_duplicate_customer_code_rejected(self):
        create_customer(
            name="Cust A", sales_man_link_name_id=self.link_fsd.id, code_suffix="003",
            address="addr", user=self.admin,
        )
        with self.assertRaises(ValidationError):
            create_customer(
                name="Cust B", sales_man_link_name_id=self.link_fsd.id, code_suffix="003",
                address="addr", user=self.admin,
            )


class SalesManPermissionTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.admin = make_admin()
        self.user = make_user()

    def test_non_admin_gets_403(self):
        request = self.factory.get("/api/sales-man/sales-men/")
        force_authenticate(request, user=self.user)
        response = SalesManListCreateView.as_view()(request)
        self.assertEqual(response.status_code, 403)

    def test_admin_gets_200(self):
        request = self.factory.get("/api/sales-man/sales-men/")
        force_authenticate(request, user=self.admin)
        response = SalesManListCreateView.as_view()(request)
        self.assertEqual(response.status_code, 200)


class BackfillCommandTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        # Pre-existing customers created "manually" (no FK assigned yet),
        # simulating the legacy state the command is meant to fix.
        self.c_fsd_wrong_prefix = Customer.objects.create(
            name="Legacy FSD", code="OLD-FSD-777", address="addr",
            created_by=self.admin, updated_by=self.admin,
        )
        self.c_os_right_prefix = Customer.objects.create(
            name="Legacy OS", code="ALFA-OS-555", address="addr",
            created_by=self.admin, updated_by=self.admin,
        )
        self.c_malformed = Customer.objects.create(
            name="Malformed", code="RANDOMCODE", address="addr",
            created_by=self.admin, updated_by=self.admin,
        )

    def test_dry_run_makes_no_changes(self):
        call_command("backfill_sales_man", "--dry-run")
        self.assertFalse(SalesMan.objects.exists())
        self.c_fsd_wrong_prefix.refresh_from_db()
        self.assertEqual(self.c_fsd_wrong_prefix.code, "OLD-FSD-777")

    def test_dry_run_summary_counts(self):
        import io
        out = io.StringIO()
        call_command("backfill_sales_man", "--dry-run", stdout=out)
        output = out.getvalue()
        # 3 customers total: 2 match the pattern (convertible), 1 malformed.
        self.assertIn("Summary: 3 customer(s) scanned", output)
        self.assertIn("2 match the expected code structure", output)
        self.assertIn("1 malformed", output)
        self.assertIn("0 blocked by a code collision", output)

    def test_apply_fixes_prefix_and_assigns_and_is_idempotent(self):
        call_command("backfill_sales_man")

        self.c_fsd_wrong_prefix.refresh_from_db()
        self.c_os_right_prefix.refresh_from_db()
        self.c_malformed.refresh_from_db()

        self.assertEqual(self.c_fsd_wrong_prefix.code, "ALFA-FSD-777")
        self.assertEqual(self.c_os_right_prefix.code, "ALFA-OS-555")  # already correct, untouched
        self.assertEqual(self.c_malformed.code, "RANDOMCODE")  # never touched

        sm1 = SalesMan.objects.get(code="SM1")
        sm2 = SalesMan.objects.get(code="SM2")
        self.assertEqual(sm1.total_customers, 1)
        self.assertEqual(sm2.total_customers, 1)

        # Re-run: numbers must return to the same baseline (idempotency).
        call_command("backfill_sales_man")
        sm1.refresh_from_db()
        sm2.refresh_from_db()
        self.assertEqual(sm1.total_customers, 1)
        self.assertEqual(sm2.total_customers, 1)
        self.c_fsd_wrong_prefix.refresh_from_db()
        self.assertEqual(self.c_fsd_wrong_prefix.code, "ALFA-FSD-777")


class SalesManUpdateViewTests(TestCase):
    """
    Regression tests for the "PATCHing a sales man with its own unchanged
    code fails validation" bug — the view built its serializer without an
    instance, so DRF's UniqueValidator on `code` had no self to exclude.
    """

    def setUp(self):
        self.factory = APIRequestFactory()
        self.admin = make_admin()
        self.sm = create_sales_man(name="sale_man_1", code="SM1", address="old addr", phone="0300", user=self.admin)

    def _patch(self, data):
        request = self.factory.patch(f"/api/sales-man/sales-men/{self.sm.id}/", data)
        force_authenticate(request, user=self.admin)
        return SalesManRetrieveUpdateDestroyView.as_view()(request, pk=self.sm.id)

    def test_updating_name_only_does_not_trip_code_uniqueness(self):
        response = self._patch({"name": "sale_man_1_renamed"})
        self.assertEqual(response.status_code, 200)
        self.sm.refresh_from_db()
        self.assertEqual(self.sm.name, "sale_man_1_renamed")
        self.assertEqual(self.sm.code, "SM1")

    def test_updating_with_own_unchanged_code_succeeds(self):
        response = self._patch({"code": "SM1", "phone": "0311"})
        self.assertEqual(response.status_code, 200)
        self.sm.refresh_from_db()
        self.assertEqual(self.sm.phone, "0311")

    def test_updating_to_another_sales_man_s_code_still_rejected(self):
        create_sales_man(name="sale_man_2", code="SM2", user=self.admin)
        response = self._patch({"code": "SM2"})
        self.assertEqual(response.status_code, 400)


class BackfillCommandPrefixCollisionTests(TestCase):
    """
    Regression test for a real production-data shape: two DIFFERENT customer
    rows share the same link+suffix segment but differ only by prefix (e.g.
    a typo'd 'ALF-' vs the correct 'ALFA-'). Naively rewriting the wrong one
    to the correct prefix collides with the customer that already has that
    exact code — this must be caught and reported, not crash (and roll back)
    the whole batch.
    """

    def setUp(self):
        self.admin = make_admin()
        self.already_correct = Customer.objects.create(
            name="Already Correct", code="ALFA-FSD-7860310", address="x",
            created_by=self.admin, updated_by=self.admin,
        )
        self.colliding = Customer.objects.create(
            name="Typo Prefix", code="ALF-FSD-7860310", address="x",
            created_by=self.admin, updated_by=self.admin,
        )
        # A normal, non-colliding fix must still go through in the SAME run.
        self.normal_fix = Customer.objects.create(
            name="Normal Fix", code="OLD-OS-999", address="x",
            created_by=self.admin, updated_by=self.admin,
        )

    def test_apply_reports_collision_and_still_commits_the_rest(self):
        import io
        out = io.StringIO()
        call_command("backfill_sales_man", stdout=out)
        output = out.getvalue()

        self.assertIn("1 customer(s) whose fixed code would COLLIDE", output)
        self.assertIn("ALF-FSD-7860310", output)

        self.colliding.refresh_from_db()
        self.already_correct.refresh_from_db()
        self.normal_fix.refresh_from_db()
        # The colliding customer's code is untouched — no crash, no partial write.
        self.assertEqual(self.colliding.code, "ALF-FSD-7860310")
        self.assertEqual(self.already_correct.code, "ALFA-FSD-7860310")
        # The unrelated fix in the SAME run still committed — proves one
        # collision no longer rolls back the entire batch.
        self.assertEqual(self.normal_fix.code, "ALFA-OS-999")

        sm2 = SalesMan.objects.get(code="SM2")
        self.assertEqual(sm2.total_customers, 1)  # normal_fix only


class BackfillCommandSuffixHyphenTests(TestCase):
    """
    Real production data can have a stray hyphen inside the suffix segment
    itself (e.g. 'CUS-OS-786-155', originally meant as one code) — the
    regex's greedy suffix capture preserves it as '786-155'. Every hyphen
    inside the suffix must be stripped, and this must apply even to a
    customer whose prefix is ALREADY correct (re-normalizing on every run,
    not just when the prefix needs fixing) and even to one already assigned
    from an earlier, flawed run.
    """

    def setUp(self):
        self.admin = make_admin()

    def test_hyphen_in_suffix_is_stripped_even_with_correct_prefix(self):
        customer = Customer.objects.create(
            name="Hyphen Suffix", code="ALFA-OS-786-155", address="x",
            created_by=self.admin, updated_by=self.admin,
        )
        call_command("backfill_sales_man")
        customer.refresh_from_db()
        self.assertEqual(customer.code, "ALFA-OS-786155")
        self.assertEqual(customer.code_suffix, "786155")
        sm2 = SalesMan.objects.get(code="SM2")
        self.assertEqual(sm2.total_customers, 1)

    def test_already_assigned_customer_with_stale_hyphenated_suffix_gets_corrected_on_rerun(self):
        sm2 = create_sales_man(name="sale_man_2", code="SM2", user=self.admin)
        link_os = create_link_name(sales_man_id=sm2.id, name="OS", user=self.admin)
        customer = Customer.objects.create(
            name="Stale Assignment", code="ALFA-OS-786-155", address="x",
            sales_man_link_name=link_os, sales_man=sm2, code_suffix="786-155",
            created_by=self.admin, updated_by=self.admin,
        )
        call_command("backfill_sales_man")
        customer.refresh_from_db()
        self.assertEqual(customer.code, "ALFA-OS-786155")
        self.assertEqual(customer.code_suffix, "786155")
