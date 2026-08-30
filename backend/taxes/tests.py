from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from cash_flow.models import CashFlow
from payment_methods.models import PaymentMethod
from users.models import User

from .models import TaxFlow
from .services import (
    create_tax_payment, create_wht_payment, delete_tax_payment,
    delete_wht_payment, sync_invoice_tax, sync_purchase_tax,
)
from .views import TaxPaymentListCreateView, TaxStatsView, WHTPaymentListCreateView


def make_admin(email="admin@example.com"):
    return User.objects.create_user(
        email=email, password="Adm1n-secret!", first_name="Admin",
        last_name="User", is_staff=True,
    )


def make_normal_user(email="normal@example.com"):
    return User.objects.create_user(
        email=email, password="N0rmal-secret!", first_name="Normal", last_name="User",
    )


class TaxesTestBase(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.admin = make_admin()
        # Seed the tax position: input GST 1000, output GST 1500 → net 500;
        # WHT withheld from suppliers 200, by customers 300.
        sync_purchase_tax(gst_amount=Decimal("1000"), wht_amount=Decimal("200"), user=self.admin)
        sync_invoice_tax(gst_amount=Decimal("1500"), wht_amount=Decimal("300"), user=self.admin)
        # Seed cash in hand — cash_in_hand is floored at 0, so deductions
        # from an empty till would vanish and hide round-trip errors.
        from cash_flow.services import sync_invoice_payment_received
        sync_invoice_payment_received(amount=Decimal("1000"), user=self.admin)
        self.cash_method = PaymentMethod.objects.get_or_create(name="Cash", defaults={"balance": Decimal("1000000")})[0]

    def cash_split(self, amount):
        return [(self.cash_method, Decimal(amount))]

    def flow(self):
        return TaxFlow.get_instance()

    def cash(self):
        return CashFlow.get_instance().cash_in_hand


class TaxFlowRoundTripTests(TaxesTestBase):
    def test_seeded_position(self):
        tf = self.flow()
        self.assertEqual(tf.net_sales_tax_payable, Decimal("500"))
        self.assertEqual(tf.sales_tax_outstanding, Decimal("500"))
        self.assertEqual(tf.wht_outstanding, Decimal("200"))

    def test_tax_payment_create_and_delete_round_trip(self):
        cash_before = self.cash()

        payment = create_tax_payment(
            amount=Decimal("200"), payment_date=timezone.now().date(),
            method_allocations=self.cash_split("200"), user=self.admin,
        )
        tf = self.flow()
        self.assertEqual(tf.total_sales_tax_paid, Decimal("200"))
        self.assertEqual(tf.sales_tax_outstanding, Decimal("300"))
        self.assertEqual(self.cash(), cash_before - Decimal("200"))

        delete_tax_payment(pk=payment.pk, user=self.admin)
        tf = self.flow()
        self.assertEqual(tf.total_sales_tax_paid, Decimal("0"))
        self.assertEqual(tf.sales_tax_outstanding, Decimal("500"))
        self.assertEqual(self.cash(), cash_before)

    def test_wht_payment_create_and_delete_round_trip(self):
        cash_before = self.cash()

        payment = create_wht_payment(
            amount=Decimal("150"), payment_date=timezone.now().date(),
            method_allocations=self.cash_split("150"), user=self.admin,
        )
        tf = self.flow()
        self.assertEqual(tf.total_wht_paid, Decimal("150"))
        self.assertEqual(tf.wht_outstanding, Decimal("50"))
        self.assertEqual(self.cash(), cash_before - Decimal("150"))

        delete_wht_payment(pk=payment.pk, user=self.admin)
        tf = self.flow()
        self.assertEqual(tf.total_wht_paid, Decimal("0"))
        self.assertEqual(tf.wht_outstanding, Decimal("200"))
        self.assertEqual(self.cash(), cash_before)


class TaxSearchTests(TaxesTestBase):
    def test_note_search_returns_matching_payments_only(self):
        create_tax_payment(amount=Decimal("100"), payment_date=timezone.now().date(),
                           method_allocations=self.cash_split("100"), note="FBR quarterly filing", user=self.admin)
        create_tax_payment(amount=Decimal("50"), payment_date=timezone.now().date(),
                           method_allocations=self.cash_split("50"), note="monthly deposit", user=self.admin)

        request = self.factory.get("/taxes/payments/", {"search": "QUARTER"})
        force_authenticate(request, user=self.admin)
        response = TaxPaymentListCreateView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([r["note"] for r in response.data["results"]], ["FBR quarterly filing"])

    def test_wht_note_search(self):
        create_wht_payment(amount=Decimal("60"), payment_date=timezone.now().date(),
                           method_allocations=self.cash_split("60"), note="supplier WHT deposit", user=self.admin)

        request = self.factory.get("/taxes/wht-payments/", {"search": "supplier"})
        force_authenticate(request, user=self.admin)
        response = WHTPaymentListCreateView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)


class TaxStatsEndpointTests(TaxesTestBase):
    def test_stats_read_off_singleton(self):
        request = self.factory.get("/taxes/stats/")
        force_authenticate(request, user=self.admin)
        response = TaxStatsView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["net_sales_tax_payable"], "500.0000")
        self.assertEqual(response.data["wht_outstanding"], "200.0000")

    def test_normal_user_gets_403(self):
        request = self.factory.get("/taxes/stats/")
        force_authenticate(request, user=make_normal_user())
        response = TaxStatsView.as_view()(request)
        self.assertEqual(response.status_code, 403)


class TaxPaymentAllocationQueryCountTests(TaxesTestBase):
    """architecture.md's STRICT O(1)-per-page rule — the allocations field
    on each list view must not N+1 as row count grows."""

    def count_queries(self, view, url):
        request = self.factory.get(url)
        force_authenticate(request, user=self.admin)
        with CaptureQueriesContext(connection) as ctx:
            response = view(request)
            response.render()
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries)

    def test_tax_payment_list_query_count_flat(self):
        view = TaxPaymentListCreateView.as_view()
        create_tax_payment(
            amount=Decimal("10"), payment_date=timezone.now().date(),
            method_allocations=self.cash_split("10"), user=self.admin,
        )
        baseline = self.count_queries(view, "/taxes/payments/")

        for _ in range(4):
            create_tax_payment(
                amount=Decimal("10"), payment_date=timezone.now().date(),
                method_allocations=self.cash_split("10"), user=self.admin,
            )
        grown = self.count_queries(view, "/taxes/payments/")
        self.assertEqual(baseline, grown)

    def test_wht_payment_list_query_count_flat(self):
        view = WHTPaymentListCreateView.as_view()
        create_wht_payment(
            amount=Decimal("10"), payment_date=timezone.now().date(),
            method_allocations=self.cash_split("10"), user=self.admin,
        )
        baseline = self.count_queries(view, "/taxes/wht-payments/")

        for _ in range(4):
            create_wht_payment(
                amount=Decimal("10"), payment_date=timezone.now().date(),
                method_allocations=self.cash_split("10"), user=self.admin,
            )
        grown = self.count_queries(view, "/taxes/wht-payments/")
        self.assertEqual(baseline, grown)
