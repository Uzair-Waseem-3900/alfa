"""The lean invoice selector must return exactly what the full one does."""
from decimal import Decimal

from django.test import TestCase

from billing.models import Customer, Invoice
from billing.selectors import get_filtered_invoices, get_filtered_invoices_lean


class LeanInvoiceSelectorParityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ali = Customer.objects.create(name="Ali Traders", code="C-ALI", mobile="0300")
        cls.sara = Customer.objects.create(name="Sara Stores", code="C-SARA", mobile="0301")
        spec = [
            ("BILL-2026-0001", cls.ali, "confirmed", "unpaid", 1000, 1000),
            ("BILL-2026-0002", cls.ali, "confirmed", "paid", 500, 0),
            ("BILL-2026-0003", cls.sara, "partial", "partial", 700, 200),
            ("BILL-2026-0004", cls.sara, "draft", "unpaid", 300, 300),
            ("BILL-2026-0005", cls.sara, "returned", "paid", 900, 0),
        ]
        for bill, cust, status, pay, total, owed in spec:
            Invoice.objects.create(
                bill_number=bill, customer=cust, status=status, payment_status=pay,
                grand_total=Decimal(total), credit_outstanding=Decimal(owed),
            )
        Invoice.objects.create(bill_number="BILL-2026-0006", customer=cls.ali, status="confirmed", is_deleted=True)

    def test_same_rows_same_order_for_many_filter_combinations(self):
        combos = [
            {}, {"customer_name": "ali"}, {"customer_name": "SARA"}, {"status": "confirmed"},
            {"payment_status": "paid"}, {"bill_number": "0003"}, {"outstanding_only": True},
            {"outstanding_only": True, "customer_name": "sara"}, {"status": "draft", "payment_status": "unpaid"},
            {"min_amount": "600"}, {"date_from": "2020-01-01", "date_to": "2099-12-31"},
        ]
        for filters in combos:
            full = [i.pk for i in get_filtered_invoices(**filters)]
            lean = [i.pk for i in get_filtered_invoices_lean(**filters)]
            self.assertEqual(lean, full, f"mismatch for {filters}")
        self.assertEqual(len(list(get_filtered_invoices_lean())), 5)   # soft-deleted excluded

    def test_lean_does_not_load_item_prefetches(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as q:
            rows = list(get_filtered_invoices_lean()[:25])
            _ = [r.customer.name for r in rows]
        self.assertEqual(len(q), 1)
        with CaptureQueriesContext(connection) as q:
            list(get_filtered_invoices()[:25])
        self.assertGreater(len(q), 1)      # the full selector prefetches items etc.
