from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.exceptions import ValidationError
from rest_framework.test import force_authenticate

from purchases.models import Inventory
from rates.models import ProductRate

from .models import Invoice, Payment
from .services import (
    accept_return, confirm_invoice, create_invoice, create_return, update_invoice_items,
)
from .tests import BillingTestBase
from .views import InvoiceListCreateView


class InvoiceDiscountTests(BillingTestBase):
    """Whole-invoice discount: reduces grand_total / gross_profit, never the
    line prices. Product: cost 50, price 100 -> 4 units = 400 sale, 200 cogs,
    200 gross profit before the invoice discount."""

    def setUp(self):
        super().setUp()
        self.product = self.make_stocked_product(stock=20, unit_cost="50", selling_price="100")

    def draft(self, *, qty=4, dtype="flat", dvalue="0", item_discount="0"):
        return create_invoice(
            customer_id=self.customer.id,
            items=[{"product_id": self.product.id, "quantity": qty, "discount": Decimal(item_discount)}],
            invoice_discount_type=dtype, invoice_discount_value=Decimal(dvalue),
            user=self.admin,
        )

    def confirm(self, invoice):
        self.allocate_invoice_items(invoice)
        return confirm_invoice(invoice_id=invoice.id, user=self.admin)

    # -- math -------------------------------------------------------------
    def test_percent_reduces_grand_total_and_profit_not_line_price(self):
        invoice = self.confirm(self.draft(dtype="percent", dvalue="3"))
        item = invoice.items.get()
        self.assertEqual(invoice.invoice_discount_amount, Decimal("12"))
        self.assertEqual(invoice.grand_total, Decimal("388"))
        self.assertEqual(invoice.total_cogs, Decimal("200"))
        self.assertEqual(invoice.gross_profit, Decimal("188"))
        self.assertEqual(invoice.credit_outstanding, Decimal("388"))
        self.assertEqual(item.selling_price, Decimal("100"))
        self.assertEqual(item.effective_price, Decimal("100"))
        self.assertEqual(item.line_total, Decimal("400"))

    def test_flat_discount(self):
        invoice = self.confirm(self.draft(dtype="flat", dvalue="100"))
        self.assertEqual(invoice.grand_total, Decimal("300"))
        self.assertEqual(invoice.gross_profit, Decimal("100"))

    def test_stacks_with_item_level_discount(self):
        # item discount 10 -> line 360, profit 160; flat 50 -> 310 / 110
        invoice = self.confirm(self.draft(dtype="flat", dvalue="50", item_discount="10"))
        self.assertEqual(invoice.items.get().line_total, Decimal("360"))
        self.assertEqual(invoice.grand_total, Decimal("310"))
        self.assertEqual(invoice.gross_profit, Decimal("110"))

    def test_zero_discount_is_unchanged(self):
        invoice = self.confirm(self.draft())
        self.assertEqual(invoice.invoice_discount_amount, Decimal("0"))
        self.assertEqual(invoice.grand_total, Decimal("400"))
        self.assertEqual(invoice.gross_profit, Decimal("200"))

    # -- validation -------------------------------------------------------
    def test_discount_equal_to_profit_is_allowed(self):
        invoice = self.confirm(self.draft(dtype="flat", dvalue="200"))
        self.assertEqual(invoice.gross_profit, Decimal("0"))
        self.assertEqual(invoice.grand_total, Decimal("200"))

    def test_percent_to_exact_profit_is_allowed(self):
        invoice = self.confirm(self.draft(dtype="percent", dvalue="50"))
        self.assertEqual(invoice.gross_profit, Decimal("0"))

    def test_discount_above_profit_rejected_with_clear_error(self):
        with self.assertRaises(ValidationError) as ctx:
            self.draft(dtype="flat", dvalue="200.01")
        msg = str(ctx.exception.detail["invoice_discount_value"])
        self.assertIn("exceeds this invoice's gross profit", msg)
        self.assertIn("200.00", msg)
        self.assertFalse(Invoice.objects.exists())

    def test_percent_above_profit_rejected(self):
        with self.assertRaises(ValidationError):
            self.draft(dtype="percent", dvalue="60")

    def test_item_discount_shrinks_the_limit(self):
        # item discount 40 -> line 240, profit 40: a flat 50 is now too much
        with self.assertRaises(ValidationError):
            self.draft(dtype="flat", dvalue="50", item_discount="40")
        self.draft(dtype="flat", dvalue="40", item_discount="40")

    def test_update_revalidates_against_new_items(self):
        invoice = self.draft(qty=4, dtype="flat", dvalue="150")
        with self.assertRaises(ValidationError):
            # qty 1 -> profit 50, existing 150 discount no longer valid
            update_invoice_items(
                invoice_id=invoice.id,
                items=[{"product_id": self.product.id, "quantity": 1}], user=self.admin,
            )
        invoice.refresh_from_db()
        self.assertEqual(invoice.items.get().quantity, 4)  # nothing replaced

    def test_update_changes_discount_and_omitted_fields_are_kept(self):
        invoice = self.draft(dtype="percent", dvalue="3")
        update_invoice_items(
            invoice_id=invoice.id, items=[{"product_id": self.product.id, "quantity": 4}],
            invoice_discount_value=Decimal("5"), user=self.admin,
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.invoice_discount_type, "percent")
        self.assertEqual(invoice.invoice_discount_value, Decimal("5"))
        update_invoice_items(
            invoice_id=invoice.id, items=[{"product_id": self.product.id, "quantity": 4}], user=self.admin,
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.invoice_discount_value, Decimal("5"))
        self.assertEqual(self.confirm(invoice).grand_total, Decimal("380"))

    def test_confirm_rechecks_and_rolls_back_when_profit_dropped(self):
        invoice = self.draft(dtype="flat", dvalue="150")
        # Rate falls after the draft: profit becomes 4*(60-50) = 40 < 150
        ProductRate.objects.filter(product=self.product).update(selling_price=Decimal("60"))
        stock_before = Inventory.objects.get(product=self.product).quantity
        self.allocate_invoice_items(invoice)
        with self.assertRaises(ValidationError) as ctx:
            confirm_invoice(invoice_id=invoice.id, user=self.admin)
        self.assertIn("invoice_discount_value", ctx.exception.detail)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.DRAFT)
        self.assertEqual(Inventory.objects.get(product=self.product).quantity, stock_before)

    def test_locked_after_confirm(self):
        invoice = self.confirm(self.draft(dtype="flat", dvalue="10"))
        with self.assertRaises(ValidationError):
            update_invoice_items(
                invoice_id=invoice.id, items=[{"product_id": self.product.id, "quantity": 4}],
                invoice_discount_value=Decimal("20"), user=self.admin,
            )

    # -- API ----------------------------------------------------------------
    def post(self, **body):
        payload = {
            "customer_id": self.customer.id,
            "items": [{"product_id": self.product.id, "quantity": 4}],
            **body,
        }
        request = self.factory.post("/billing/invoices/", payload, format="json")
        force_authenticate(request, user=self.admin)
        return InvoiceListCreateView.as_view()(request)

    def test_api_creates_and_exposes_fields_and_print_preview(self):
        response = self.post(invoice_discount_type="percent", invoice_discount_value="3")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["invoice_discount_type"], "percent")
        self.assertEqual(Decimal(str(response.data["invoice_discount_value"])), Decimal("3"))
        self.assertEqual(Decimal(response.data["print_preview"]["grand_total"]), Decimal("388"))
        self.assertEqual(Decimal(response.data["print_preview"]["invoice_discount_amount"]), Decimal("12"))

    def test_api_rejects_bad_input(self):
        for body in (
            {"invoice_discount_type": "percent", "invoice_discount_value": "101"},
            {"invoice_discount_type": "flat", "invoice_discount_value": "-1"},
            {"invoice_discount_type": "bogus", "invoice_discount_value": "1"},
        ):
            self.assertEqual(self.post(**body).status_code, 400, body)

    def test_api_error_for_discount_over_profit(self):
        response = self.post(invoice_discount_type="flat", invoice_discount_value="500")
        self.assertEqual(response.status_code, 400)
        self.assertIn("invoice_discount_value", response.data)

    def test_normal_user_can_set_discount(self):
        from .tests import make_normal_user
        request = self.factory.post("/billing/invoices/", {
            "customer_id": self.customer.id,
            "items": [{"product_id": self.product.id, "quantity": 4}],
            "invoice_discount_type": "flat", "invoice_discount_value": "10",
        }, format="json")
        force_authenticate(request, user=make_normal_user())
        self.assertEqual(InvoiceListCreateView.as_view()(request).status_code, 201)

    # -- returns ------------------------------------------------------------
    def return_qty(self, invoice, qty):
        ret = create_return(
            invoice_id=invoice.id,
            items=[{"invoice_item_id": invoice.items.get().id, "quantity": qty}], user=self.admin,
        )
        self.allocate_return_items(ret)
        accept_return(return_id=ret.id, user=self.admin)
        ret.refresh_from_db()
        return ret

    def test_full_return_credits_what_was_paid(self):
        invoice = self.confirm(self.draft(dtype="percent", dvalue="3"))  # 388
        ret = self.return_qty(invoice, 4)
        invoice.refresh_from_db()
        self.assertEqual(ret.total_return_amount, Decimal("388"))
        self.assertEqual(Payment.objects.get(note__endswith=ret.reference_number).amount, Decimal("-388"))
        self.assertEqual(invoice.credit_outstanding, Decimal("0"))
        self.assertEqual(invoice.grand_total, Decimal("388"))          # untouched by return
        self.assertEqual(invoice.invoice_discount_amount, Decimal("12"))  # not reset by recalculation

    def test_partial_returns_add_up_to_grand_total(self):
        invoice = self.confirm(self.draft(dtype="flat", dvalue="100"))  # 300
        first = self.return_qty(invoice, 1)
        second = self.return_qty(invoice, 3)
        self.assertEqual(first.total_return_amount, Decimal("75"))
        self.assertEqual(first.total_return_amount + second.total_return_amount, Decimal("300"))
        invoice.refresh_from_db()
        self.assertEqual(invoice.credit_outstanding, Decimal("0"))

    def test_pending_return_shows_prorated_value(self):
        invoice = self.confirm(self.draft(dtype="flat", dvalue="100"))
        ret = create_return(
            invoice_id=invoice.id,
            items=[{"invoice_item_id": invoice.items.get().id, "quantity": 2}], user=self.admin,
        )
        self.assertEqual(ret.items.get().line_total, Decimal("150"))

    # -- backfills ------------------------------------------------------------
    def test_backfill_invoices_keeps_discount(self):
        from django.core.management import call_command
        from io import StringIO
        invoice = self.confirm(self.draft(dtype="percent", dvalue="3"))
        call_command("backfill_invoices", stdout=StringIO())
        invoice.refresh_from_db()
        self.assertEqual(invoice.grand_total, Decimal("388"))
        self.assertEqual(invoice.gross_profit, Decimal("188"))

    # -- performance ----------------------------------------------------------
    def test_discount_validation_adds_at_most_one_query_regardless_of_items(self):
        products = [
            self.make_stocked_product(code=f"Q{i}", name=f"Q{i}", stock=10) for i in range(4)
        ]
        items = [{"product_id": p.id, "quantity": 1} for p in products]

        def run(**kw):
            with CaptureQueriesContext(connection) as ctx:
                create_invoice(customer_id=self.customer.id, items=items, user=self.admin, **kw)
            return len(ctx)

        base = run()
        with_discount = run(invoice_discount_type="flat", invoice_discount_value=Decimal("1"))
        self.assertLessEqual(with_discount - base, 1)


class InvoiceDiscountRoundingTests(BillingTestBase):
    """3 lines of 10 with a flat 1 discount -> grand 29. Each prorated line
    is 9.6667, so naive per-line rounding would credit 29.0001 on a full
    return; the final line must absorb the residue."""

    def test_full_return_credits_exactly_grand_total(self):
        specs = []
        for code in ("R1", "R2", "R3"):
            p = self.make_stocked_product(code=code, name=code, stock=5, unit_cost="1", selling_price="10")
            specs.append({"product_id": p.id, "quantity": 1})
        invoice = create_invoice(
            customer_id=self.customer.id, items=specs,
            invoice_discount_type="flat", invoice_discount_value=Decimal("1"), user=self.admin,
        )
        self.allocate_invoice_items(invoice)
        invoice = confirm_invoice(invoice_id=invoice.id, user=self.admin)
        self.assertEqual(invoice.grand_total, Decimal("29"))

        ret = create_return(
            invoice_id=invoice.id,
            items=[{"invoice_item_id": i.id, "quantity": 1} for i in invoice.items.all()],
            user=self.admin,
        )
        self.allocate_return_items(ret)
        accept_return(return_id=ret.id, user=self.admin)
        ret.refresh_from_db()
        invoice.refresh_from_db()
        self.assertEqual(ret.total_return_amount, Decimal("29"))
        self.assertEqual(sum(i.line_total for i in ret.items.all()), Decimal("29"))
        self.assertEqual(Payment.objects.get(note__endswith=ret.reference_number).amount, Decimal("-29"))
        self.assertEqual(invoice.credit_outstanding, Decimal("0"))
        self.assertEqual(invoice.payment_status, Invoice.PaymentStatus.PAID)


class InvoiceDiscountPercentDisplayTests(BillingTestBase):
    """invoice_discount_percent: typed value for percent, derived for flat."""

    def setUp(self):
        super().setUp()
        self.product = self.make_stocked_product(stock=20, unit_cost="50", selling_price="100")

    def draft(self, dtype, dvalue):
        return create_invoice(
            customer_id=self.customer.id,
            items=[{"product_id": self.product.id, "quantity": 4}],
            invoice_discount_type=dtype, invoice_discount_value=Decimal(dvalue), user=self.admin,
        )

    def detail(self, invoice):
        from .serializers import InvoiceReadSerializer
        from .selectors import get_invoice_by_id
        return InvoiceReadSerializer(
            get_invoice_by_id(invoice.id),
            context={"request": type("FakeRequest", (), {"user": self.admin})()},
        ).data

    def test_percent_type_shows_typed_value_confirmed_and_draft(self):
        invoice = self.draft("percent", "3")
        data = self.detail(invoice)
        self.assertIsNone(data["invoice_discount_percent"])  # drafts use print_preview
        self.assertEqual(data["print_preview"]["invoice_discount_percent"], "3")
        self.assertEqual(data["print_preview"]["invoice_discount_amount"], "12.0000")
        self.allocate_invoice_items(invoice)
        confirm_invoice(invoice_id=invoice.id, user=self.admin)
        self.assertEqual(self.detail(invoice)["invoice_discount_percent"], "3")

    def test_flat_type_derives_percent_confirmed_and_draft(self):
        invoice = self.draft("flat", "100")  # 100 off a 400 bill = 25%
        self.assertEqual(self.detail(invoice)["print_preview"]["invoice_discount_percent"], "25")
        self.allocate_invoice_items(invoice)
        confirm_invoice(invoice_id=invoice.id, user=self.admin)
        self.assertEqual(self.detail(invoice)["invoice_discount_percent"], "25")

    def test_fractional_percent_and_no_discount(self):
        from .utils import invoice_discount_percent
        self.assertEqual(
            invoice_discount_percent(discount_type="flat", discount_value=10, amount=Decimal("10"), grand_total=Decimal("290")),
            "3.33",
        )
        self.assertEqual(
            invoice_discount_percent(discount_type="percent", discount_value=Decimal("3.5"), amount=Decimal("14"), grand_total=Decimal("386")),
            "3.5",
        )
        self.assertIsNone(self.detail(self.draft("flat", "0"))["print_preview"]["invoice_discount_percent"])
