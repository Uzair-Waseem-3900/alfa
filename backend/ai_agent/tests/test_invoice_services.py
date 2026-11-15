"""The assistant's invoice-draft writes (services layer), against the real billing services."""
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone
from pydantic import ValidationError as PydanticValidationError

from billing.models import Invoice, Payment
from billing.services import confirm_invoice, create_invoice
from billing.utils import get_invoice_print_context
from cash_flow.models import CashFlow

from ai_agent.exceptions import ToolInputError
from ai_agent.models import AgentAction
from ai_agent.schemas.invoice import InvoiceLineIn
from ai_agent.services import invoicing

from .helpers import make_plain_user
from .invoice_fixtures import InvoiceWorld


def line(product, quantity=1, **kw):
    return InvoiceLineIn(product_id=product.id, quantity=quantity, **kw)


class WorldTestCase(InvoiceWorld, TestCase):
    def setUp(self):
        self.build_world()
        self.pen = self.stocked_product("P001", "Pen Blue", stock=100, selling_price="100")
        self.book = self.stocked_product("P002", "Notebook", stock=50, selling_price="200")

    def create(self, lines, *, run=None, **kw):
        args = dict(customer_id=self.customer.id, lines=lines, invoice_discount=None,
                    invoice_discount_type="percent", due_date=None)
        args.update(kw)
        return invoicing.create_draft(**self.ctx_kwargs(run), **args)

    def update(self, bill, *, run=None, **kw):
        args = dict(bill_number=bill, set_lines=None, remove_product_ids=None, invoice_discount=None,
                    invoice_discount_type="percent", due_date=None)
        args.update(kw)
        return invoicing.update_draft(**self.ctx_kwargs(run), **args)

    def discard(self, bill, *, run=None):
        return invoicing.discard_draft(**self.ctx_kwargs(run), bill_number=bill)

    def invoice_of(self, result):
        return Invoice.objects.get(pk=result["invoice_id"])


# ======================================================================== create

class CreateDraftTests(WorldTestCase):
    def test_creates_a_draft_with_defaults_and_an_audit_row(self):
        result = self.create([line(self.pen, 10)])
        inv = self.invoice_of(result)

        self.assertEqual(result["result"], "draft_created")
        self.assertEqual(inv.status, Invoice.Status.DRAFT)
        self.assertEqual((inv.payment_type, inv.advance_amount), ("after_delivery", 0))
        self.assertEqual(inv.payment_due_date, timezone.localdate() + timedelta(days=7))
        self.assertEqual(inv.created_by, self.admin)                         # attributed to the asking admin
        item = inv.items.get()
        self.assertEqual((item.quantity, item.discount, item.gst, item.wht), (10, 0, 0, 0))
        self.assertEqual((inv.invoice_discount_type, inv.invoice_discount_value), ("percent", 0))

        action = AgentAction.objects.get()
        self.assertEqual((action.tool, action.result, action.bill_number, action.user_id, action.run_id),
                         ("create_draft_invoice", "created", inv.bill_number, self.admin.pk, self.run.pk))
        self.assertEqual(action.invoice_id, inv.id)

    def test_summary_uses_the_apps_own_numbers_and_says_it_is_a_draft(self):
        result = self.create([line(self.pen, 10)])
        md = result["summary_markdown"]
        self.assertIn(f"DRAFT invoice {result['bill_number']}", md)
        self.assertIn("not confirmed", md)
        self.assertIn("Stock is not deducted", md)
        self.assertIn("Sultan Kitab Ghar (SKG)", md)
        self.assertIn("Pen Blue (P001)", md)
        self.assertIn("Grand total: Rs 1,000.00", md)                        # 10 x 100, no tax/discount
        self.assertIn("Defaults used: GST 0%, WHT 0%, no discount, due in 7 days", md)
        self.assertIn(f"(/billing/invoices/{result['invoice_id']})", md)
        # and it is the SAME number billing computes:
        ctx = get_invoice_print_context(self.invoice_of(result))
        self.assertEqual(ctx["grand_total"], Decimal("1000"))
        self.assertEqual(result["link"], f"/billing/invoices/{result['invoice_id']}")

    def test_values_the_user_gave_are_used_and_not_listed_as_defaults(self):
        result = self.create([line(self.pen, 10, discount_amount=5, gst=18, wht=1)], due_date=str(timezone.localdate() + timedelta(days=30)))
        item = self.invoice_of(result).items.get()
        self.assertEqual((item.discount, item.gst, item.wht), (Decimal("5"), Decimal("18"), Decimal("1")))
        # (100-5) x 10 = 950; +18% = 1121; -1% = 9.5  ->  1111.50
        self.assertIn("Grand total: Rs 1,111.50", result["summary_markdown"])
        self.assertNotIn("Defaults used", result["summary_markdown"])

    def test_percent_line_discount_is_converted_to_rupees_per_unit_in_code(self):
        result = self.create([line(self.pen, 10, discount_percent=10), line(self.book, 1, discount_percent=12.5)])
        items = {i.product_id: i for i in self.invoice_of(result).items.all()}
        self.assertEqual(items[self.pen.id].discount, Decimal("10.0000"))     # 10% of Rs 100
        self.assertEqual(items[self.book.id].discount, Decimal("25.0000"))    # 12.5% of Rs 200

    def test_invoice_discount_defaults_to_percent_and_can_be_flat(self):
        pct = self.invoice_of(self.create([line(self.pen, 10)], invoice_discount=5))
        self.assertEqual((pct.invoice_discount_type, pct.invoice_discount_value), ("percent", Decimal("5")))
        flat = self.invoice_of(self.create([line(self.pen, 10)], invoice_discount=100, invoice_discount_type="flat", run=self.new_run()))
        self.assertEqual((flat.invoice_discount_type, flat.invoice_discount_value), ("flat", Decimal("100")))
        result = self.create([line(self.pen, 10)], invoice_discount=10, run=self.new_run())
        self.assertIn("Invoice discount:", result["summary_markdown"])
        self.assertIn("Grand total: Rs 900.00", result["summary_markdown"])

    def test_line_models_reject_impossible_input(self):
        for bad in (dict(discount_percent=5, discount_amount=5), dict(discount_percent=-1), dict(discount_percent=101),
                    dict(discount_amount=-5), dict(gst=-1), dict(gst=101), dict(wht=101), dict(quantity=0)):
            with self.assertRaises(PydanticValidationError, msg=str(bad)):
                InvoiceLineIn(product_id=1, **{"quantity": 1, **bad})
        with override_settings(AGENT_INVOICE_MAX_QTY=10):
            with self.assertRaises(PydanticValidationError):
                InvoiceLineIn(product_id=1, quantity=11)

    def test_plain_language_refusals(self):
        cases = [
            ([line(self.pen, 101)], "Insufficient stock"),
            ([line(self.pen, 1, discount_amount=150)], "more than its price"),
            ([line(self.pen, 1), line(self.pen, 2)], "twice"),
            ([InvoiceLineIn(product_id=self.pen.id)], "needs a quantity"),
            ([], "at least one product"),
        ]
        for lines, expected in cases:
            with self.assertRaises(ToolInputError) as cm:
                self.create(lines, run=self.new_run())
            self.assertIn(expected, str(cm.exception))
        self.assertEqual(Invoice.objects.count(), 0)                         # nothing half-created

    def test_unknown_product_unpriced_product_and_unknown_customer(self):
        unpriced = self.stocked_product("P003", "No Price")
        unpriced.rate.delete()
        for kwargs, expected in [
            (dict(lines=[InvoiceLineIn(product_id=999999, quantity=1)]), "was not found"),
            (dict(lines=[line(unpriced, 1)]), "no selling price"),
            (dict(lines=[line(self.pen, 1)], customer_id=999999), "customer was not found"),
        ]:
            with self.assertRaises(ToolInputError) as cm:
                self.create(run=self.new_run(), **kwargs)
            self.assertIn(expected, str(cm.exception))

    def test_due_date_rules(self):
        future = timezone.localdate() + timedelta(days=30)
        inv = self.invoice_of(self.create([line(self.pen, 1)], due_date=str(future)))
        self.assertEqual(inv.payment_due_date, future)
        for bad in ("2020-01-01", "not-a-date", "2026-13-40"):
            with self.assertRaises(ToolInputError, msg=bad):
                self.create([line(self.pen, 1)], due_date=bad, run=self.new_run())

    def test_too_many_lines(self):
        with override_settings(AGENT_INVOICE_MAX_LINES=1):
            with self.assertRaises(ToolInputError):
                self.create([line(self.pen, 1), line(self.book, 1)])

    def test_stock_is_not_deducted_by_a_draft(self):
        from purchases.models import Inventory
        before = Inventory.objects.get(product=self.pen).quantity
        self.create([line(self.pen, 10)])
        self.assertEqual(Inventory.objects.get(product=self.pen).quantity, before)

    def test_no_advance_and_no_cash_movement_is_possible(self):
        cash_before = CashFlow.get_instance().cash_in_hand
        self.create([line(self.pen, 10)])
        self.assertEqual(CashFlow.get_instance().cash_in_hand, cash_before)
        self.assertEqual(Payment.objects.count(), 0)


# ======================================================================== permissions / budget

class WriteGuardTests(WorldTestCase):
    def test_non_admin_cannot_write(self):
        plain = make_plain_user()
        with self.assertRaises(ToolInputError) as cm:
            invoicing.create_draft(user=plain, run_id=str(self.run.id), chat_id=str(self.chat.id),
                                   customer_id=self.customer.id, lines=[line(self.pen, 1)],
                                   invoice_discount=None, invoice_discount_type="percent", due_date=None)
        self.assertIn("Only admins", str(cm.exception))
        self.assertEqual(Invoice.objects.count(), 0)

    def test_inactive_admin_cannot_write(self):
        self.admin.is_active = False
        self.admin.save()
        with self.assertRaises(ToolInputError):
            self.create([line(self.pen, 1)])

    def test_a_write_needs_a_chat_request(self):
        with self.assertRaises(ToolInputError):
            invoicing.create_draft(user=self.admin, run_id=None, chat_id=None, customer_id=self.customer.id,
                                   lines=[line(self.pen, 1)], invoice_discount=None, invoice_discount_type="percent", due_date=None)

    @override_settings(AGENT_WRITES_PER_HOUR=2)
    def test_hourly_write_budget(self):
        self.create([line(self.pen, 1)], run=self.new_run())
        self.create([line(self.pen, 2)], run=self.new_run())
        with self.assertRaises(ToolInputError) as cm:
            self.create([line(self.pen, 3)], run=self.new_run())
        self.assertIn("hourly limit", str(cm.exception))
        self.assertEqual(Invoice.objects.count(), 2)

    @override_settings(AGENT_WRITES_PER_HOUR=1)
    def test_old_actions_do_not_count_against_the_budget(self):
        self.create([line(self.pen, 1)])
        AgentAction.objects.update(created_at=timezone.now() - timedelta(hours=2))
        self.create([line(self.pen, 2)], run=self.new_run())          # fresh hour: allowed


# ======================================================================== idempotency

class IdempotencyTests(WorldTestCase):
    def test_the_same_call_in_the_same_run_creates_one_invoice(self):
        """A cut-off model attempt is retried: the retry repeats the tool call. Chat-history rollback
        does not undo DB writes, so THIS is what prevents a second invoice."""
        first = self.create([line(self.pen, 5)])
        second = self.create([line(self.pen, 5)])
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertEqual(AgentAction.objects.count(), 1)
        self.assertEqual(second["bill_number"], first["bill_number"])
        self.assertTrue(second["already_done_earlier_in_this_request"])
        self.assertFalse(first["already_done_earlier_in_this_request"])

    def test_a_different_run_or_different_arguments_is_a_new_invoice(self):
        self.create([line(self.pen, 5)])
        self.create([line(self.pen, 5)], run=self.new_run())          # user asked again later
        self.create([line(self.pen, 6)])                              # different quantity
        self.assertEqual(Invoice.objects.count(), 3)

    def test_losing_a_race_rolls_the_invoice_back_and_returns_the_winner(self):
        first = self.create([line(self.pen, 5)])
        real = AgentAction.objects.get()
        # simulate: the "already done?" pre-check misses (race), the unique index then fires
        with mock.patch.object(invoicing, "_repeat_of", side_effect=[None, real]):
            second = self.create([line(self.pen, 5)])
        self.assertEqual(Invoice.objects.count(), 1)                  # the loser's invoice was rolled back
        self.assertEqual(second["bill_number"], first["bill_number"])

    def test_repeated_update_and_discard_are_idempotent_too(self):
        bill = self.create([line(self.pen, 5)])["bill_number"]
        run = self.new_run()
        self.update(bill, set_lines=[line(self.pen, 7)], run=run)
        again = self.update(bill, set_lines=[line(self.pen, 7)], run=run)
        self.assertTrue(again["already_done_earlier_in_this_request"])
        self.assertEqual(AgentAction.objects.filter(tool="update_draft_invoice").count(), 1)

        run2 = self.new_run()
        self.discard(bill, run=run2)
        second = self.discard(bill, run=run2)
        self.assertTrue(second["already_done_earlier_in_this_request"])
        self.assertEqual(AgentAction.objects.filter(tool="discard_draft_invoice").count(), 1)


# ======================================================================== update

class UpdateDraftTests(WorldTestCase):
    def setUp(self):
        super().setUp()
        made = self.create([line(self.pen, 10, gst=18, discount_amount=5), line(self.book, 4)])
        self.bill = made["bill_number"]
        self.inv = self.invoice_of(made)

    def items(self):
        return {i.product_id: i for i in Invoice.objects.get(pk=self.inv.pk).items.all()}

    def test_changing_one_line_keeps_every_other_line_and_untouched_fields(self):
        self.update(self.bill, set_lines=[line(self.pen, 3)], run=self.new_run())
        items = self.items()
        self.assertEqual(items[self.pen.id].quantity, 3)
        self.assertEqual((items[self.pen.id].discount, items[self.pen.id].gst), (Decimal("5"), Decimal("18")))   # kept
        self.assertEqual(items[self.book.id].quantity, 4)                                                       # untouched line

    def test_changing_only_the_discount_keeps_quantity_and_gst(self):
        self.update(self.bill, set_lines=[InvoiceLineIn(product_id=self.pen.id, discount_percent=10)], run=self.new_run())
        pen = self.items()[self.pen.id]
        self.assertEqual((pen.quantity, pen.gst, pen.discount), (10, Decimal("18"), Decimal("10.0000")))

    def test_gst_for_every_line(self):
        self.update(self.bill, set_lines=[InvoiceLineIn(product_id=self.pen.id, gst=17), InvoiceLineIn(product_id=self.book.id, gst=17)],
                    run=self.new_run())
        self.assertEqual({i.gst for i in self.items().values()}, {Decimal("17")})

    def test_adding_a_new_line_needs_a_quantity(self):
        third = self.stocked_product("P003", "Ruler", stock=20, selling_price="10")
        with self.assertRaises(ToolInputError) as cm:
            self.update(self.bill, set_lines=[InvoiceLineIn(product_id=third.id)], run=self.new_run())
        self.assertIn("needs a quantity", str(cm.exception))
        self.update(self.bill, set_lines=[line(third, 20)], run=self.new_run())
        self.assertEqual(len(self.items()), 3)

    def test_removing_lines(self):
        self.update(self.bill, remove_product_ids=[self.book.id], run=self.new_run())
        self.assertEqual(set(self.items()), {self.pen.id})
        with self.assertRaises(ToolInputError) as cm:                         # not on the invoice
            self.update(self.bill, remove_product_ids=[self.book.id], run=self.new_run())
        self.assertIn("not on", str(cm.exception))
        with self.assertRaises(ToolInputError) as cm:                         # would leave it empty
            self.update(self.bill, remove_product_ids=[self.pen.id], run=self.new_run())
        self.assertIn("every line", str(cm.exception))

    def test_invoice_discount_and_due_date(self):
        due = timezone.localdate() + timedelta(days=21)
        self.update(self.bill, invoice_discount=5, due_date=str(due), run=self.new_run())
        inv = Invoice.objects.get(pk=self.inv.pk)
        self.assertEqual((inv.invoice_discount_type, inv.invoice_discount_value, inv.payment_due_date),
                         ("percent", Decimal("5"), due))

    def test_nothing_to_change_is_refused(self):
        with self.assertRaises(ToolInputError):
            self.update(self.bill, run=self.new_run())

    def test_not_enough_stock_leaves_the_draft_exactly_as_it_was(self):
        with self.assertRaises(ToolInputError) as cm:
            self.update(self.bill, set_lines=[line(self.pen, 101)], run=self.new_run())
        self.assertIn("Insufficient stock", str(cm.exception))
        self.assertEqual(self.items()[self.pen.id].quantity, 10)

    def test_unknown_bill_number(self):
        with self.assertRaises(ToolInputError) as cm:
            self.update("BILL-0000-0000", set_lines=[line(self.pen, 1)], run=self.new_run())
        self.assertIn("No invoice", str(cm.exception))

    def test_a_confirmed_invoice_cannot_be_edited(self):
        self.allocate_invoice(self.inv)
        confirm_invoice(invoice_id=self.inv.id, user=self.admin)
        with self.assertRaises(ToolInputError) as cm:
            self.update(self.bill, set_lines=[line(self.pen, 1)], run=self.new_run())
        self.assertIn("already confirmed", str(cm.exception))

    def test_any_draft_by_bill_number_can_be_edited_not_only_ones_the_agent_made(self):
        manual = create_invoice(customer_id=self.customer.id, items=[{"product_id": self.pen.id, "quantity": 2}], user=self.admin)
        self.update(manual.bill_number, set_lines=[line(self.pen, 4)], run=self.new_run())
        self.assertEqual(manual.items.get().quantity, 4)

    def test_an_existing_advance_is_never_touched(self):
        advance = create_invoice(
            customer_id=self.customer.id, items=[{"product_id": self.pen.id, "quantity": 2}],
            payment_type="advance", advance_amount=Decimal("100"),
            method_allocations=[(self.cash, Decimal("100"))], user=self.admin,
        )
        cash_before, payments_before = CashFlow.get_instance().cash_in_hand, Payment.objects.count()
        self.update(advance.bill_number, set_lines=[line(self.pen, 3)], invoice_discount=1, run=self.new_run())
        advance.refresh_from_db()
        self.assertEqual((advance.payment_type, advance.advance_amount), ("advance", Decimal("100")))
        self.assertEqual(CashFlow.get_instance().cash_in_hand, cash_before)
        self.assertEqual(Payment.objects.count(), payments_before)


# ======================================================================== discard / show

class DiscardAndShowTests(WorldTestCase):
    def test_discarding_a_draft_hides_it_and_frees_its_stock_reservation(self):
        from billing.selectors import get_reserved_quantity_for_product
        made = self.create([line(self.pen, 10)])
        self.assertEqual(get_reserved_quantity_for_product(product_id=self.pen.id), 10)
        result = self.discard(made["bill_number"], run=self.new_run())
        self.assertEqual(result["result"], "discarded")
        self.assertEqual(Invoice.objects.count(), 0)                          # soft-deleted, hidden
        self.assertEqual(Invoice.all_objects.count(), 1)                      # never hard-deleted
        self.assertEqual(get_reserved_quantity_for_product(product_id=self.pen.id), 0)
        self.assertEqual(AgentAction.objects.filter(result="discarded").count(), 1)

    def test_discarding_what_is_already_gone_or_confirmed_is_refused(self):
        made = self.create([line(self.pen, 2)])
        self.discard(made["bill_number"], run=self.new_run())
        with self.assertRaises(ToolInputError) as cm:
            self.discard(made["bill_number"], run=self.new_run())
        self.assertIn("No invoice", str(cm.exception))

        inv = self.invoice_of(self.create([line(self.pen, 2)], run=self.new_run()))
        self.allocate_invoice(inv)
        confirm_invoice(invoice_id=inv.id, user=self.admin)
        with self.assertRaises(ToolInputError) as cm:
            self.discard(inv.bill_number, run=self.new_run())
        self.assertIn("confirmed", str(cm.exception))

    def test_a_draft_with_an_advance_is_not_discarded_because_that_would_refund_cash(self):
        advance = create_invoice(
            customer_id=self.customer.id, items=[{"product_id": self.pen.id, "quantity": 2}],
            payment_type="advance", advance_amount=Decimal("100"),
            method_allocations=[(self.cash, Decimal("100"))], user=self.admin,
        )
        cash_before = CashFlow.get_instance().cash_in_hand
        with self.assertRaises(ToolInputError) as cm:
            self.discard(advance.bill_number)
        self.assertIn("advance", str(cm.exception))
        self.assertEqual(CashFlow.get_instance().cash_in_hand, cash_before)
        self.assertTrue(Invoice.objects.filter(pk=advance.pk).exists())

    def test_show_draft(self):
        made = self.create([line(self.pen, 2)])
        shown = invoicing.show_draft(bill_number=made["bill_number"])
        self.assertIn("DRAFT invoice", shown["summary_markdown"])
        inv = self.invoice_of(made)
        self.allocate_invoice(inv)
        confirm_invoice(invoice_id=inv.id, user=self.admin)
        with self.assertRaises(ToolInputError) as cm:
            invoicing.show_draft(bill_number=made["bill_number"])
        self.assertIn("confirmed", str(cm.exception))
