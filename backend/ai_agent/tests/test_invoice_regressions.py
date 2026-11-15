"""
Regressions from a real chat: the model sent `discount_percent: 0` AND `discount_amount: 0` (and gst 0, wht 0,
invoice_discount 0) on every line -> the schema rejected "both discount forms" -> three failed tool calls -> the
model then told the user the draft had been created. Nothing had been written.
"""
import asyncio
import json
from decimal import Decimal
from unittest import mock

from agents.tool_context import ToolContext
from django.test import TransactionTestCase

from billing.models import Invoice

from ai_agent.models import AgentAction
from ai_agent.my_tool import ALL_TOOLS
from ai_agent.schemas.context import AgentContext
from ai_agent.schemas.invoice import InvoiceLineIn
from ai_agent.services import invoicing

from .invoice_fixtures import InvoiceWorld
from .test_invoice_services import WorldTestCase


class ZeroMeansNotGivenTests(WorldTestCase):
    def test_the_exact_line_from_the_failing_chat_is_valid_and_all_unset(self):
        ln = InvoiceLineIn(**{"discount_percent": 0, "gst": 0, "discount_amount": 0, "quantity": 5, "product_id": 1, "wht": 0})
        self.assertEqual((ln.quantity, ln.discount_percent, ln.discount_amount, ln.gst, ln.wht), (5, None, None, None, None))

    def test_blank_strings_and_zero_quantity_are_not_given_either(self):
        ln = InvoiceLineIn(product_id=1, quantity=0, gst="", wht="0", discount_percent=0.0)
        self.assertEqual((ln.quantity, ln.gst, ln.wht, ln.discount_percent), (None, None, None, None))

    def test_two_REAL_discount_forms_are_still_refused(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            InvoiceLineIn(product_id=1, quantity=1, discount_percent=5, discount_amount=5)

    def test_create_with_zero_noise_makes_a_plain_draft_with_defaults(self):
        line = InvoiceLineIn(product_id=self.pen.id, quantity=5, discount_percent=0, discount_amount=0, gst=0, wht=0)
        result = self.create([line], invoice_discount=0 or None)
        item = self.invoice_of(result).items.get()
        self.assertEqual((item.quantity, item.discount, item.gst, item.wht), (5, 0, 0, 0))
        self.assertIn("Defaults used: GST 0%, WHT 0%, no discount", result["summary_markdown"])


class EditsDoNotResetThingsByAccidentTests(WorldTestCase):
    """If the model fills every optional field with 0 on an edit, existing GST/discount must survive."""

    def setUp(self):
        super().setUp()
        made = self.create([line_ for line_ in [InvoiceLineIn(product_id=self.pen.id, quantity=10, gst=18, discount_amount=5)]],
                           invoice_discount=10)
        self.bill = made["bill_number"]
        self.inv_id = made["invoice_id"]

    def item(self):
        return Invoice.objects.get(pk=self.inv_id).items.get()

    def test_zero_noise_on_an_edit_changes_nothing_but_the_given_field(self):
        noisy = InvoiceLineIn(product_id=self.pen.id, quantity=3, discount_percent=0, discount_amount=0, gst=0, wht=0)
        self.update(self.bill, set_lines=[noisy], invoice_discount=0 or None, run=self.new_run())
        item = self.item()
        self.assertEqual((item.quantity, item.gst, item.discount), (3, Decimal("18"), Decimal("5")))     # kept
        inv = Invoice.objects.get(pk=self.inv_id)
        self.assertEqual(inv.invoice_discount_value, Decimal("10"))                                        # kept

    def test_reset_is_the_explicit_way_to_remove_a_value(self):
        self.update(self.bill, set_lines=[InvoiceLineIn(product_id=self.pen.id, reset=["gst", "discount"])], run=self.new_run())
        item = self.item()
        self.assertEqual((item.gst, item.discount, item.quantity), (Decimal("0"), Decimal("0"), 10))

    def test_a_new_value_wins_over_reset_for_the_same_field(self):
        self.update(self.bill, set_lines=[InvoiceLineIn(product_id=self.pen.id, gst=5, reset=["gst"])], run=self.new_run())
        self.assertEqual(self.item().gst, Decimal("5"))

    def test_clear_invoice_discount_is_explicit(self):
        self.update(self.bill, clear_invoice_discount=True, run=self.new_run())
        self.assertEqual(Invoice.objects.get(pk=self.inv_id).invoice_discount_value, Decimal("0"))

    def update(self, bill, *, run=None, clear_invoice_discount=False, **kw):       # adds the new flag to the shared helper
        args = dict(bill_number=bill, set_lines=None, remove_product_ids=None, invoice_discount=None,
                    invoice_discount_type="percent", due_date=None, clear_invoice_discount=clear_invoice_discount)
        args.update(kw)
        return invoicing.update_draft(**self.ctx_kwargs(run), **args)


class FailedWritesAreNeverReportedAsSuccessTests(InvoiceWorld, TransactionTestCase):
    def setUp(self):
        self.build_world()
        self.pen = self.stocked_product("PEN-B", "Pen Blue", stock=50, selling_price="100")
        self.tools = {t.name: t for t in ALL_TOOLS}

    def call(self, name, args):
        ctx = ToolContext(context=AgentContext(user=self.admin, run_id=str(self.run.id), chat_id=str(self.chat.id)),
                          tool_name=name, tool_call_id="c1", tool_arguments=json.dumps(args))
        return asyncio.run(self.tools[name].on_invoke_tool(ctx, json.dumps(args)))

    def test_the_payloads_from_the_failing_chat_now_create_the_draft(self):
        # exactly what Gemini sent (2nd/3rd attempts), key order and zeros included
        out = json.loads(self.call("create_draft_invoice", {
            "due_date": None,
            "lines": [{"quantity": 5, "product_id": self.pen.id, "gst": 0, "wht": 0, "discount_percent": 0, "discount_amount": 0}],
            "customer_id": self.customer.id, "invoice_discount": 0, "invoice_discount_type": "percent",
        }))
        self.assertEqual(out["result"], "draft_created")
        self.assertIn("DRAFT invoice", out["summary_markdown"])
        self.assertEqual(Invoice.objects.count(), 1)

    def test_invalid_arguments_say_what_is_wrong_so_the_model_can_fix_them(self):
        # the 1st failing call: customer_id was missing altogether
        out = self.call("create_draft_invoice", {
            "invoice_discount_type": "percent", "invoice_discount": 0, "due_date": None,
            "lines": [{"quantity": 5, "product_id": self.pen.id}],
        })
        self.assertTrue(out.startswith("Cannot do that: the arguments were not valid"), out)
        self.assertIn("customer_id", out)
        self.assertIn("Nothing was changed", out)
        self.assertNotIn("An error occurred while running the tool", out)       # the SDK's uninformative default
        self.assertEqual(Invoice.objects.count(), 0)

    def test_an_internal_failure_says_the_change_was_not_made(self):
        with mock.patch.object(invoicing, "create_draft", side_effect=RuntimeError("no such table: ai_agent_agentaction")):
            out = self.call("create_draft_invoice", {"customer_id": self.customer.id,
                                                      "lines": [{"product_id": self.pen.id, "quantity": 1}]})
        self.assertIn("NOT made", out)
        self.assertIn("Never say it was created", out)
        self.assertNotIn("no such table", out)                                   # internals never reach the model
        self.assertEqual(AgentAction.objects.count(), 0)

    def test_read_tools_keep_their_own_failure_text(self):
        with mock.patch("ai_agent.selectors.invoicing.find_customers", side_effect=RuntimeError("boom")):
            out = self.call("find_customer_for_invoice", {"search": "x"})
        self.assertIn("failed to read the data", out)
        self.assertNotIn("NOT made", out)
