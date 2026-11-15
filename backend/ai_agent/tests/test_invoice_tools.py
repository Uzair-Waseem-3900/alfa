"""The invoice tools through the REAL SDK path: JSON arguments -> schema validation -> worker thread -> service."""
import asyncio
import json

from unittest import mock

from agents.tool_context import ToolContext
from django.test import TransactionTestCase

from billing.models import Invoice
from billing.services import create_customer

from ai_agent.models import AgentAction
from ai_agent.my_tool import ALL_TOOLS, WRITE_TOOL_NAMES
from ai_agent.schemas.context import AgentContext

from .helpers import make_plain_user
from .invoice_fixtures import InvoiceWorld


class InvoiceToolTests(InvoiceWorld, TransactionTestCase):
    """TransactionTestCase: tools run in a worker thread, which can't see a TestCase's uncommitted data."""

    def setUp(self):
        self.build_world()
        self.pen = self.stocked_product("PEN-B", "Pen Blue", stock=50, selling_price="100")
        self.tools = {t.name: t for t in ALL_TOOLS}

    def call(self, name, args, *, user=None, run=None):
        run = run or self.run
        ctx = ToolContext(
            context=AgentContext(user=user or self.admin, run_id=str(run.id), chat_id=str(self.chat.id)),
            tool_name=name, tool_call_id="call_1", tool_arguments=json.dumps(args),
        )
        return asyncio.run(self.tools[name].on_invoke_tool(ctx, json.dumps(args)))

    def test_write_tools_are_exactly_the_three_draft_tools(self):
        self.assertEqual(WRITE_TOOL_NAMES, {"create_draft_invoice", "update_draft_invoice", "discard_draft_invoice"})
        banned = {"confirm_invoice", "create_payment", "record_payment", "set_advance", "set_price"}
        self.assertFalse(banned & set(self.tools))                       # no confirm / payment / price tool exists

    def test_create_through_the_sdk_with_nested_line_arguments(self):
        out = json.loads(self.call("create_draft_invoice", {
            "customer_id": self.customer.id,
            "lines": [{"product_id": self.pen.id, "quantity": 4, "discount_percent": 10}],
        }))
        self.assertEqual(out["result"], "draft_created")
        inv = Invoice.objects.get(pk=out["invoice_id"])
        self.assertEqual(inv.status, "draft")
        self.assertEqual(inv.items.get().discount, 10)                    # 10% of Rs 100

    def test_the_model_cannot_send_what_the_schema_does_not_allow(self):
        for bad in (
            {"customer_id": self.customer.id, "lines": [{"product_id": self.pen.id, "quantity": 0}]},
            {"customer_id": self.customer.id, "lines": [{"product_id": self.pen.id, "quantity": 1, "discount_percent": 5, "discount_amount": 5}]},
            {"customer_id": self.customer.id, "lines": [{"product_id": self.pen.id, "quantity": 1}], "invoice_discount_type": "bribe"},
            {"customer_id": self.customer.id, "lines": [{"product_id": self.pen.id, "quantity": 1, "price": 1}]},   # price is not settable
        ):
            self.call("create_draft_invoice", bad, run=self.new_run())
        self.assertEqual(Invoice.objects.count(), 0)

    def test_an_undeclared_argument_is_refused_not_silently_dropped(self):
        for extra in ({"advance_amount": 500}, {"payment_type": "advance"}, {"status": "confirmed"}):
            out = self.call("create_draft_invoice", {
                "customer_id": self.customer.id, "lines": [{"product_id": self.pen.id, "quantity": 1}], **extra,
            }, run=self.new_run())
            self.assertTrue(out.startswith("Cannot do that: unknown argument(s)"), out)
            self.assertIn("Nothing was changed", out)
        self.assertEqual(Invoice.objects.count(), 0)
        self.assertEqual(AgentAction.objects.count(), 0)

    def test_refusals_reach_the_model_as_plain_sentences(self):
        out = self.call("create_draft_invoice", {"customer_id": self.customer.id,
                                                  "lines": [{"product_id": self.pen.id, "quantity": 500}]})
        self.assertTrue(out.startswith("Cannot do that:"))
        self.assertIn("Insufficient stock", out)

    def test_a_non_admin_is_refused_inside_the_tool(self):
        out = self.call("create_draft_invoice", {"customer_id": self.customer.id,
                                                  "lines": [{"product_id": self.pen.id, "quantity": 1}]},
                        user=make_plain_user())
        self.assertIn("Only admins", out)
        self.assertEqual(Invoice.objects.count(), 0)

    def test_full_conversation_flow_create_edit_show_discard(self):
        created = json.loads(self.call("create_draft_invoice", {
            "customer_id": self.customer.id, "lines": [{"product_id": self.pen.id, "quantity": 5}]}))
        bill = created["bill_number"]
        edited = json.loads(self.call("update_draft_invoice", {
            "bill_number": bill, "set_lines": [{"product_id": self.pen.id, "gst": 18}]}, run=self.new_run()))
        self.assertIn("Grand total: Rs 590.00", edited["summary_markdown"])          # 5 x 100 + 18%
        shown = json.loads(self.call("show_draft_invoice", {"bill_number": bill}))
        self.assertIn("Rs 590.00", shown["summary_markdown"])
        gone = json.loads(self.call("discard_draft_invoice", {"bill_number": bill}, run=self.new_run()))
        self.assertEqual(gone["result"], "discarded")
        self.assertEqual(AgentAction.objects.count(), 3)

    def test_lookup_tools_report_unique_multiple_and_none(self):
        create_customer(name="Waseem Stationers", code="WS", address="a", user=self.admin)
        create_customer(name="Waseem Books", code="WB", address="a", user=self.admin)
        self.stocked_product("PEN-R", "Pen Red", stock=10, selling_price="110")

        one = json.loads(self.call("find_customer_for_invoice", {"search": "sultan"}))
        self.assertEqual((one["match"], one["customer"]["customer_id"]), ("unique", self.customer.id))
        many = json.loads(self.call("find_customer_for_invoice", {"search": "waseem"}))
        self.assertEqual((many["match"], len(many["candidates"])), ("multiple", 2))
        self.assertEqual(json.loads(self.call("find_customer_for_invoice", {"search": "nobody"}))["match"], "none")

        prod = json.loads(self.call("find_product_for_invoice", {"code": "pen-b"}))
        self.assertEqual((prod["match"], prod["product"]["name"], prod["product"]["price"]), ("unique", "Pen Blue", "100.00"))
        self.assertEqual(prod["product"]["stock_available_for_new_drafts"], 50)
        self.assertEqual(json.loads(self.call("find_product_for_invoice", {"search": "pen"}))["match"], "multiple")

    def test_product_lookup_query_counts_are_small_and_fixed(self):
        from django.db.backends import utils as dbu
        self.stocked_product("PEN-R", "Pen Red", stock=10, selling_price="110")
        counter = {"n": 0}
        original = dbu.CursorWrapper.execute

        def counting(self_, sql, params=None):
            counter["n"] += 1
            return original(self_, sql, params)

        with mock.patch.object(dbu.CursorWrapper, "execute", counting):
            counter["n"] = 0
            many = json.loads(self.call("find_product_for_invoice", {"search": "pen"}))      # 2 products match
            multiple_queries = counter["n"]
            counter["n"] = 0
            one = json.loads(self.call("find_product_for_invoice", {"code": "pen-b"}))
            unique_queries = counter["n"]
        self.assertEqual(many["match"], "multiple")
        self.assertNotIn("stock_available_for_new_drafts", many["candidates"][0])            # stock only for a unique match
        self.assertEqual((one["match"], one["product"]["stock_available_for_new_drafts"]), ("unique", 50))
        self.assertEqual(multiple_queries, 1)                                                # was 1 + 3 per candidate
        self.assertLessEqual(unique_queries, 3)                                              # product(+price) + stock + reserved
