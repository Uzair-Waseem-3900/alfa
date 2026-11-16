"""Owner decisions on bulk invoices: unique ids only, the customer ladder, per-user active-row limit, @0."""
import asyncio
import json
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.exceptions import ValidationError

from billing.models import Invoice
from billing.services import create_customer

from ai_agent import tasks, views
from ai_agent.models import BulkBatch, BulkItem
from ai_agent.my_tool import ALL_TOOLS
from ai_agent.schemas.invoice import InvoiceLineIn
from ai_agent.selectors import invoicing as sel
from ai_agent.services import bulk, invoicing

from .helpers import make_admin
from .test_api import call
from .test_bulk import BulkWorld


class UniqueIdsOnlyInBulkTests(BulkWorld, TransactionTestCase):
    def setUp(self):
        self.build_world()
        self.pen = self.stocked_product("PEN-B", "Pen Blue", stock=100, selling_price="100")
        self.pen2 = self.stocked_product("PEN-R", "Pen Red", stock=100, selling_price="100")
        create_customer(name="Ali Traders", code="ALI-1", address="Lahore", user=self.admin)
        create_customer(name="Ali Books", code="ALI-2", address="Karachi", user=self.admin)
        self.tools = {t.name: t for t in ALL_TOOLS}

    def call(self, name, args, ctx):
        from agents.tool_context import ToolContext
        tc = ToolContext(context=ctx, tool_name=name, tool_call_id="c", tool_arguments=json.dumps(args))
        return asyncio.run(self.tools[name].on_invoke_tool(tc, json.dumps(args)))

    def test_bulk_a_several_matches_lookup_does_not_unlock_any_of_them(self):
        ctx = self.agent_context(looked_up=False, source="bulk")
        found = json.loads(self.call("find_customer_for_invoice", {"search": "ali"}, ctx))
        self.assertEqual(found["match"], "multiple")
        picked = found["candidates"][0]["customer_id"]
        prod = json.loads(self.call("find_product_for_invoice", {"search": "pen blue"}, ctx))["product"]["product_id"]
        out = self.call("create_draft_invoice", {"customer_id": picked, "lines": [{"product_id": prod, "quantity": 1}]}, ctx)
        self.assertTrue(out.startswith("Cannot do that:"), out)
        self.assertEqual(Invoice.objects.count(), 0)

    def test_bulk_several_matching_products_do_not_unlock_either(self):
        ctx = self.agent_context(looked_up=False, source="bulk")
        self.call("find_customer_for_invoice", {"code": "SKG"}, ctx)
        several = json.loads(self.call("find_product_for_invoice", {"search": "pen"}, ctx))
        self.assertEqual(several["match"], "multiple")
        out = self.call("create_draft_invoice", {"customer_id": self.customer.id,
                                                  "lines": [{"product_id": several["candidates"][0]["product_id"], "quantity": 1}]}, ctx)
        self.assertIn("find_product_for_invoice", out)
        self.assertEqual(Invoice.objects.count(), 0)

    def test_bulk_a_unique_match_still_unlocks_and_the_chat_behaviour_is_unchanged(self):
        ctx = self.agent_context(looked_up=False, source="bulk")
        self.call("find_customer_for_invoice", {"search": "sultan"}, ctx)
        self.call("find_product_for_invoice", {"search": "pen blue"}, ctx)
        ok = json.loads(self.call("create_draft_invoice", {"customer_id": self.customer.id,
                                                            "lines": [{"product_id": self.pen.id, "quantity": 1}]}, ctx))
        self.assertEqual(ok["result"], "draft_created")
        chat_ctx = self.agent_context(self.new_run(), looked_up=False)          # chat: the user answers the question next turn
        self.call("find_customer_for_invoice", {"search": "ali"}, chat_ctx)
        self.assertEqual(len(chat_ctx.lookups.customers), 2)

    def test_a_rate_of_zero_means_use_the_rate_list_not_free(self):
        made = invoicing.create_draft(**self.ctx_kwargs(), customer_id=self.customer.id,
                                      lines=[InvoiceLineIn(product_id=self.pen.id, quantity=2, unit_rate=0)],
                                      invoice_discount=None, invoice_discount_type="percent", due_date=None)
        item = Invoice.objects.get(pk=made["invoice_id"]).items.get()
        self.assertEqual(item.discount, Decimal("0"))
        self.assertIn("Grand total: Rs 200.00", made["summary_markdown"])


class CustomerLadderTests(BulkWorld, TestCase):
    """name (a partial match is fine) -> link name (already applied) -> address -> only then ask."""

    def setUp(self):
        self.build_world()
        create_customer(name="Uzair Khan", code="U1", address="Satiana Road, Faisalabad", user=self.admin)
        create_customer(name="Uzair Ali", code="U2", address="Model Town, Lahore", user=self.admin)

    def test_a_single_partial_name_match_is_used_with_no_question(self):
        unique, _ = sel.find_customers(search="sultan kit", code=None)
        self.assertEqual(unique.code, "SKG")

    def test_several_name_matches_are_narrowed_by_the_address(self):
        unique, _ = sel.find_customers(search="uzair", code=None, area="model town")
        self.assertEqual(unique.code, "U2")

    def test_an_address_that_matches_nobody_does_not_hide_a_clear_name_match(self):
        unique, _ = sel.find_customers(search="sultan", code=None, area="the moon")
        self.assertEqual(unique.code, "SKG")                                    # the address is optional

    def test_several_name_matches_and_a_useless_address_means_ask(self):
        unique, candidates = sel.find_customers(search="uzair", code=None, area="the moon")
        self.assertIsNone(unique)
        self.assertEqual({c.code for c in candidates}, {"U1", "U2"})            # shown with their addresses, not "not found"

    def test_an_address_matching_several_still_means_ask(self):
        create_customer(name="Uzair Raza", code="U3", address="Model Town, Karachi", user=self.admin)
        unique, candidates = sel.find_customers(search="uzair", code=None, area="model town")
        self.assertIsNone(unique)
        self.assertEqual({c.code for c in candidates}, {"U2", "U3"})


class ActiveRowLimitTests(BulkWorld, TestCase):
    def setUp(self):
        cache.clear()
        self.build_world()
        self.other = make_admin("admin2@example.com")
        patcher = mock.patch.object(tasks.run_bulk_item_task, "delay")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_default_is_two_full_batches(self):
        from django.conf import settings
        self.assertEqual(settings.AGENT_BULK_MAX_ACTIVE_ROWS, 200)

    @override_settings(AGENT_BULK_MAX_ACTIVE_ROWS=5)
    def test_rows_still_waiting_count_against_the_limit_and_the_message_says_how_many_fit(self):
        bulk.create_batch(user=self.admin, prompts=["a", "b", "c"], link_name_id=None)
        with self.assertRaises(ValidationError) as cm:
            bulk.create_batch(user=self.admin, prompts=["d", "e", "f"], link_name_id=None)
        text = str(cm.exception.detail["detail"])
        self.assertIn("3 invoices waiting", text)
        self.assertIn("limit is 5", text)
        self.assertIn("up to 2 more", text)
        self.assertEqual(BulkBatch.objects.count(), 1)                          # nothing half-created
        bulk.create_batch(user=self.admin, prompts=["d", "e"], link_name_id=None)    # exactly fits

    @override_settings(AGENT_BULK_MAX_ACTIVE_ROWS=5)
    def test_the_limit_is_per_user(self):
        bulk.create_batch(user=self.admin, prompts=["a"] * 5, link_name_id=None)
        bulk.create_batch(user=self.other, prompts=["a"] * 5, link_name_id=None)     # another user is unaffected

    @override_settings(AGENT_BULK_MAX_ACTIVE_ROWS=3)
    def test_finished_cancelled_and_answered_rows_do_not_count_and_room_comes_back(self):
        first = bulk.create_batch(user=self.admin, prompts=["a", "b", "c"], link_name_id=None)
        with self.assertRaises(ValidationError):
            bulk.create_batch(user=self.admin, prompts=["d"], link_name_id=None)
        bulk.cancel_batch(batch=first)                                               # stop the rest
        bulk.create_batch(user=self.admin, prompts=["d", "e", "f"], link_name_id=None)
        BulkItem.objects.filter(batch=first).update(status="done")                   # history never counts
        self.assertEqual(BulkBatch.objects.filter(user=self.admin).count(), 2)

    @override_settings(AGENT_BULK_MAX_ACTIVE_ROWS=2)
    def test_the_api_answers_400_with_a_readable_detail(self):
        listing = views.BulkBatchListCreateView.as_view()
        self.assertEqual(call(listing, "post", "/b/", self.admin, {"prompts": ["a", "b"]}).status_code, 201)
        r = call(listing, "post", "/b/", self.admin, {"prompts": ["c"]})
        self.assertEqual(r.status_code, 400)
        self.assertIn("limit is 2", r.data["detail"])
