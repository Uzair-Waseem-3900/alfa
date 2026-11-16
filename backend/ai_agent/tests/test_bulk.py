"""
Bulk invoices: API rules, the row state machine, the worker (agent faked, DB + Redis real), live events, the
"only ids the model looked up" guard, qty@rate, separate budgets and the customer area / link-name narrowing.
Local SQLite only. The model is faked; nothing here calls Gemini.
"""
import asyncio
import json
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import redis
from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from billing.models import Invoice
from billing.services import create_customer
from sales_man.services import create_link_name, create_sales_man

from ai_agent import tasks, views
from ai_agent.config.gemini_compat import IncompleteStreamError
from ai_agent.exceptions import ToolInputError
from ai_agent.models import AgentAction, BulkBatch, BulkItem, ChatRun
from ai_agent.my_tool.bulk_tool import needs_attention, not_an_invoice
from ai_agent.schemas.context import AgentContext, BulkOutcome, LookupLog
from ai_agent.schemas.invoice import InvoiceLineIn
from ai_agent.selectors import invoicing as sel
from ai_agent.services import bulk, bulk_runner, invoicing, streaming

from .helpers import make_admin, make_plain_user, tool_ctx
from .invoice_fixtures import InvoiceWorld
from .test_api import call


class BulkWorld(InvoiceWorld):
    """A batch with N rows (status queued) owned by self.admin."""

    def make_batch(self, prompts=("Sultan Kitab Ghar\nPen Blue 5",), user=None, link_name=None):
        batch = BulkBatch.objects.create(user=user or self.admin, link_name=link_name,
                                         link_name_label=link_name.name if link_name else "")
        for n, text in enumerate(prompts, start=1):
            BulkItem.objects.create(batch=batch, position=n, prompt=text)
        return batch

    def item(self, batch, position=1):
        return BulkItem.objects.get(batch=batch, position=position)


# =============================================================================== API


class BulkApiTests(BulkWorld, TestCase):
    def setUp(self):
        cache.clear()
        self.build_world()
        self.other = make_admin("admin2@example.com")
        self.plain = make_plain_user()
        patcher = mock.patch.object(tasks.run_bulk_item_task, "delay")
        self.delay = patcher.start()
        self.addCleanup(patcher.stop)

    def post_batch(self, prompts, user=None, **extra):
        return call(views.BulkBatchListCreateView.as_view(), "post", "/b/", user or self.admin,
                   {"prompts": prompts, **extra})

    def test_create_makes_one_queued_row_per_prompt_and_queues_them_in_order(self):
        r = self.post_batch(["A\nPen 1", "  B\nPen 2  ", "C\nPen 3"])
        self.assertEqual(r.status_code, 201)
        self.assertEqual([i["status"] for i in r.data["items"]], ["queued"] * 3)
        self.assertEqual([i["prompt"] for i in r.data["items"]], ["A\nPen 1", "B\nPen 2", "C\nPen 3"])
        ids = [c.args[0] for c in self.delay.call_args_list]
        self.assertEqual(ids, list(BulkItem.objects.order_by("position").values_list("id", flat=True)))

    def test_invalid_input_is_refused_and_nothing_is_created(self):
        for bad in ([], [""], ["ok", "   "], ["x" * (settings.AGENT_MAX_INPUT_CHARS + 1)]):
            self.assertEqual(self.post_batch(bad).status_code, 400, bad)
        with override_settings(AGENT_BULK_MAX_ROWS=2):
            self.assertEqual(self.post_batch(["a", "b", "c"]).status_code, 400)
        self.assertEqual(self.post_batch(["a"], link_name_id=99999).status_code, 400)
        self.assertEqual(BulkBatch.objects.count(), 0)

    def test_permissions_and_isolation(self):
        listing = views.BulkBatchListCreateView.as_view()
        self.assertEqual(call(listing, "get", "/b/", None).status_code, 401)
        self.assertEqual(call(listing, "get", "/b/", self.plain).status_code, 403)
        batch = self.make_batch()
        item = self.item(batch)
        detail = call(views.BulkBatchDetailView.as_view(), "get", "/b/x/", self.other, batch_id=batch.id)
        self.assertEqual(detail.status_code, 404)
        for view in (views.BulkAnswerView, views.BulkSkipView, views.BulkRetryView):
            self.assertEqual(call(view.as_view(), "post", "/i/", self.other, {"answer": "x"}, item_id=item.id).status_code, 404)
        self.assertEqual(call(views.BulkCancelView.as_view(), "post", "/b/", self.other, {}, batch_id=batch.id).status_code, 404)
        self.assertEqual(call(listing, "get", "/b/", self.other).data["count"], 0)

    def test_list_has_counts_in_one_grouped_query(self):
        batch = self.make_batch(["a", "b", "c", "d"])
        BulkItem.objects.filter(batch=batch, position=1).update(status="done")
        BulkItem.objects.filter(batch=batch, position=2).update(status="needs_attention")
        BulkItem.objects.filter(batch=batch, position=3).update(status="failed")
        self.make_batch(["z"])
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as q:
            r = call(views.BulkBatchListCreateView.as_view(), "get", "/b/", self.admin)
        row = next(x for x in r.data["results"] if x["id"] == str(batch.id))
        self.assertEqual((row["total"], row["done"], row["attention"], row["failed"], row["working"]), (4, 1, 1, 1, 1))
        self.assertLessEqual(len(q), 3)

    def test_detail_is_two_queries_whatever_the_row_count(self):
        batch = self.make_batch([f"p{n}" for n in range(30)])
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as q:
            r = call(views.BulkBatchDetailView.as_view(), "get", "/b/x/", self.admin, batch_id=batch.id)
        self.assertEqual(len(r.data["items"]), 30)
        self.assertLessEqual(len(q), 6)       # batch, stale sweep, batch+items (2), auth

    def test_answer_requeues_only_that_row_with_the_answer_in_its_prompt(self):
        batch = self.make_batch(["Uzair\nPen 1", "Ali\nPen 2"])
        BulkItem.objects.filter(batch=batch, position=1).update(status="needs_attention", question="Which Uzair?", options=["A", "B"], attempts=1)
        BulkBatch.objects.filter(pk=batch.pk).update(status="waiting")
        item = self.item(batch)
        r = call(views.BulkAnswerView.as_view(), "post", "/i/", self.admin, {"answer": "The one in Lahore"}, item_id=item.id)
        self.assertEqual((r.status_code, r.data["status"], r.data["question"]), (200, "queued", ""))
        self.delay.assert_called_once_with(item.id)
        item.refresh_from_db()
        self.assertEqual(item.answers, [{"question": "Which Uzair?", "answer": "The one in Lahore"}])
        self.assertIn("Q: Which Uzair?\nA: The one in Lahore", bulk.compose_prompt(item))
        self.assertEqual(self.item(batch, 2).status, "queued")                  # untouched
        batch.refresh_from_db()
        self.assertEqual(batch.status, "active")

    def test_answer_rules(self):
        batch = self.make_batch(["x"])
        item = self.item(batch)
        ask = lambda: call(views.BulkAnswerView.as_view(), "post", "/i/", self.admin, {"answer": "yes"}, item_id=item.id)
        self.assertEqual(ask().status_code, 400)                                # not waiting for an answer
        BulkItem.objects.filter(pk=item.pk).update(status="needs_attention", question="q", attempts=settings.AGENT_BULK_MAX_ATTEMPTS)
        self.assertEqual(ask().status_code, 400)                                # too many tries
        BulkItem.objects.filter(pk=item.pk).update(attempts=1)
        self.assertEqual(call(views.BulkAnswerView.as_view(), "post", "/i/", self.admin, {"answer": "  "}, item_id=item.id).status_code, 400)
        self.assertEqual(ask().status_code, 200)
        self.assertEqual(ask().status_code, 400)                                # double click: already queued

    def test_skip_retry_cancel_delete(self):
        batch = self.make_batch(["a", "b", "c"])
        BulkItem.objects.filter(batch=batch, position=1).update(status="needs_attention", question="q")
        BulkItem.objects.filter(batch=batch, position=2).update(status="failed", message="boom", attempts=1)
        r = call(views.BulkSkipView.as_view(), "post", "/i/", self.admin, {}, item_id=self.item(batch, 1).id)
        self.assertEqual(r.data["status"], "skipped")
        r = call(views.BulkRetryView.as_view(), "post", "/i/", self.admin, {}, item_id=self.item(batch, 2).id)
        self.assertEqual(r.data["status"], "queued")
        self.assertEqual(call(views.BulkRetryView.as_view(), "post", "/i/", self.admin, {}, item_id=self.item(batch, 1).id).status_code, 400)
        self.assertEqual(call(views.BulkBatchDetailView.as_view(), "delete", "/b/x/", self.admin, batch_id=batch.id).status_code, 400)  # still working
        r = call(views.BulkCancelView.as_view(), "post", "/b/", self.admin, {}, batch_id=batch.id)
        self.assertEqual(r.data["status"], "cancelled")
        self.assertEqual([i["status"] for i in r.data["items"]], ["skipped", "cancelled", "cancelled"])
        self.assertEqual(call(views.BulkBatchDetailView.as_view(), "delete", "/b/x/", self.admin, batch_id=batch.id).status_code, 204)
        self.assertEqual(BulkBatch.objects.count(), 0)
        self.assertEqual(BulkBatch.all_objects.count(), 1)                       # soft delete

    def test_retry_never_creates_a_second_draft_when_an_earlier_attempt_already_did(self):
        pen = self.stocked_product("PEN-B", "Pen Blue", stock=50)
        batch = self.make_batch(["Sultan\nPen 1"])
        item = self.item(batch)
        run = ChatRun.objects.create(chat=None, bulk_item=item, user_message="x", status="error")
        made = invoicing.create_draft(
            **{**self.ctx_kwargs(run), "chat_id": None}, customer_id=self.customer.id,
            lines=[InvoiceLineIn(product_id=pen.id, quantity=1)], invoice_discount=None,
            invoice_discount_type="percent", due_date=None, source="bulk")
        BulkItem.objects.filter(pk=item.pk).update(status="failed", message="crashed afterwards", attempts=1)
        r = call(views.BulkRetryView.as_view(), "post", "/i/", self.admin, {}, item_id=item.id)
        self.assertEqual((r.data["status"], r.data["bill_number"]), ("done", made["bill_number"]))
        self.delay.assert_not_called()
        self.assertEqual(Invoice.objects.count(), 1)

    def test_a_row_whose_worker_died_is_resolved_on_read(self):
        batch = self.make_batch(["a", "b"])
        old = timezone.now() - timedelta(seconds=settings.AGENT_BULK_ITEM_TIMEOUT_SECONDS + 600)
        BulkItem.objects.filter(batch=batch, position=1).update(status="processing", started_at=old)
        r = call(views.BulkBatchDetailView.as_view(), "get", "/b/x/", self.admin, batch_id=batch.id)
        first = r.data["items"][0]
        self.assertEqual(first["status"], "failed")
        self.assertIn("Retry", first["message"])

    def test_broker_down_fails_the_rows_honestly(self):
        self.delay.side_effect = ConnectionError("redis down")
        r = self.post_batch(["a", "b"])
        self.assertEqual(r.status_code, 201)
        self.assertEqual({i.status for i in BulkItem.objects.all()}, {"failed"})
        self.assertEqual(BulkBatch.objects.get().status, "finished")

    def test_link_names_for_the_dropdown(self):
        man = create_sales_man(name="Ahmed", code="AH", user=self.admin)
        create_link_name(sales_man_id=man.id, name="fsd", user=self.admin)
        r = call(views.BulkLinkNamesView.as_view(), "get", "/l/", self.admin)
        self.assertEqual([(x["name"], x["sales_man"]) for x in r.data["results"]], [("FSD", "Ahmed")])


# =============================================================================== guard, qty@rate, budgets, narrowing


class GuardAndRateTests(BulkWorld, TransactionTestCase):
    def setUp(self):
        self.build_world()
        self.pen = self.stocked_product("PEN-B", "Pen Blue", stock=500, selling_price="230")
        from ai_agent.my_tool import ALL_TOOLS
        self.tools = {t.name: t for t in ALL_TOOLS}

    def call(self, name, args, ctx):
        from agents.tool_context import ToolContext
        tc = ToolContext(context=ctx, tool_name=name, tool_call_id="c", tool_arguments=json.dumps(args))
        return asyncio.run(self.tools[name].on_invoke_tool(tc, json.dumps(args)))

    def test_an_id_the_model_never_looked_up_is_refused_the_azeem_to_mian_flower_bug(self):
        ctx = self.agent_context(looked_up=False)
        out = self.call("create_draft_invoice", {"customer_id": self.customer.id,
                                                  "lines": [{"product_id": self.pen.id, "quantity": 1}]}, ctx)
        self.assertTrue(out.startswith("Cannot do that:"), out)
        self.assertIn("find_customer_for_invoice", out)
        self.assertEqual(Invoice.objects.count(), 0)

    def test_a_product_id_the_model_never_looked_up_is_refused(self):
        ctx = self.agent_context(looked_up=False)
        ctx.lookups.customers.add(self.customer.id)
        out = self.call("create_draft_invoice", {"customer_id": self.customer.id,
                                                  "lines": [{"product_id": self.pen.id, "quantity": 1}]}, ctx)
        self.assertIn("find_product_for_invoice", out)
        self.assertEqual(Invoice.objects.count(), 0)

    def test_looking_up_through_the_find_tools_unlocks_exactly_those_ids(self):
        ctx = self.agent_context(looked_up=False)
        self.call("find_customer_for_invoice", {"search": "sultan"}, ctx)
        self.call("find_product_for_invoice", {"search": "pen blue"}, ctx)
        out = json.loads(self.call("create_draft_invoice", {"customer_id": self.customer.id,
                                                             "lines": [{"product_id": self.pen.id, "quantity": 2}]}, ctx))
        self.assertEqual(out["result"], "draft_created")

    def test_a_new_run_must_look_up_again_but_editing_an_existing_line_needs_no_lookup(self):
        made = invoicing.create_draft(**self.ctx_kwargs(), customer_id=self.customer.id,
                                      lines=[InvoiceLineIn(product_id=self.pen.id, quantity=2)],
                                      invoice_discount=None, invoice_discount_type="percent", due_date=None)
        other = self.stocked_product("BK", "Book", stock=50)
        ctx = self.agent_context(self.new_run(), looked_up=False)
        edit_existing = self.call("update_draft_invoice", {"bill_number": made["bill_number"],
                                                           "set_lines": [{"product_id": self.pen.id, "quantity": 3}]}, ctx)
        self.assertEqual(json.loads(edit_existing)["result"], "draft_updated")
        add_new = self.call("update_draft_invoice", {"bill_number": made["bill_number"],
                                                     "set_lines": [{"product_id": other.id, "quantity": 1}]}, self.agent_context(self.new_run(), looked_up=False))
        self.assertIn("find_product_for_invoice", add_new)

    def test_customer_rows_carry_the_address_so_same_name_customers_can_be_told_apart(self):
        create_customer(name="Uzair", code="U-FSD", address="Satiana Road, Faisalabad", user=self.admin)
        create_customer(name="Uzair", code="U-LHR", address="Model Town, Lahore", user=self.admin)
        out = json.loads(self.call("find_customer_for_invoice", {"search": "uzair"}, self.agent_context(looked_up=False)))
        self.assertEqual(out["match"], "multiple")
        self.assertEqual({c["address"] for c in out["candidates"]}, {"Satiana Road, Faisalabad", "Model Town, Lahore"})
        unique = json.loads(self.call("find_customer_for_invoice", {"search": "uzair", "area": "lahore"}, self.agent_context(looked_up=False)))
        self.assertEqual((unique["match"], unique["customer"]["code"]), ("unique", "U-LHR"))

    def test_link_name_limits_the_customer_search_and_the_model_cannot_change_it(self):
        man = create_sales_man(name="Ahmed", code="AH", user=self.admin)
        fsd = create_link_name(sales_man_id=man.id, name="fsd", user=self.admin)
        lhr = create_link_name(sales_man_id=man.id, name="lhr", user=self.admin)
        create_customer(name="Uzair", sales_man_link_name_id=fsd.id, code_suffix="1", address="A", user=self.admin)
        create_customer(name="Uzair", sales_man_link_name_id=lhr.id, code_suffix="2", address="B", user=self.admin)
        out = json.loads(self.call("find_customer_for_invoice", {"search": "uzair"}, self.agent_context(looked_up=False, link_name_id=fsd.id)))
        self.assertEqual((out["match"], out["customer"]["code"].split("-")[1]), ("unique", "FSD"))
        none = json.loads(self.call("find_customer_for_invoice", {"search": "sultan"}, self.agent_context(looked_up=False, link_name_id=fsd.id)))
        self.assertEqual(none["match"], "none")
        self.assertTrue(none["searched_only_in_link_name"])
        everyone = json.loads(self.call("find_customer_for_invoice", {"search": "uzair"}, self.agent_context(looked_up=False)))
        self.assertEqual(everyone["match"], "multiple")

    # --- qty@rate -----------------------------------------------------------
    def create(self, **line):
        return invoicing.create_draft(**self.ctx_kwargs(), customer_id=self.customer.id,
                                      lines=[InvoiceLineIn(product_id=self.pen.id, quantity=300, **line)],
                                      invoice_discount=None, invoice_discount_type="percent", due_date=None)

    def test_a_lower_rate_becomes_a_line_discount_the_users_example(self):
        result = self.create(unit_rate=228)
        item = Invoice.objects.get(pk=result["invoice_id"]).items.get()
        self.assertEqual(item.discount, Decimal("2"))
        self.assertIn("Grand total: Rs 68,400.00", result["summary_markdown"])             # 300 x 228
        self.assertIn("a discount of Rs 2.00 per unit", result["summary_markdown"])
        self.assertNotIn("no discount", result["summary_markdown"])

    def test_a_higher_rate_becomes_a_surcharge(self):
        result = self.create(unit_rate=235)
        self.assertEqual(Invoice.objects.get(pk=result["invoice_id"]).items.get().discount, Decimal("-5"))
        self.assertIn("a surcharge of Rs 5.00 per unit", result["summary_markdown"])

    def test_the_list_rate_means_no_discount(self):
        result = self.create(unit_rate=230)
        self.assertEqual(Invoice.objects.get(pk=result["invoice_id"]).items.get().discount, Decimal("0"))

    def test_an_absurd_rate_is_refused_not_adjusted(self):
        for rate in (1000.5, 461):          # more than double the Rs 230 list price
            with self.assertRaises(ToolInputError):
                self.create(unit_rate=rate)
        self.assertEqual(Invoice.objects.count(), 0)

    def test_a_rate_and_a_discount_together_are_refused_and_zero_means_not_given(self):
        with self.assertRaises(Exception):
            InvoiceLineIn(product_id=1, quantity=1, unit_rate=228, discount_amount=2)
        self.assertIsNone(InvoiceLineIn(product_id=1, quantity=1, unit_rate=0).unit_rate)

    def test_a_rate_never_touches_the_invoice_discount(self):
        result = self.create(unit_rate=228)
        inv = Invoice.objects.get(pk=result["invoice_id"])
        self.assertEqual(inv.invoice_discount_value, Decimal("0"))

    # --- budgets ------------------------------------------------------------
    def test_bulk_and_chat_have_separate_hourly_budgets(self):
        with override_settings(AGENT_WRITES_PER_HOUR=1, AGENT_BULK_WRITES_PER_HOUR=2):
            self.create(unit_rate=228)                                                    # chat: 1 of 1 used
            with self.assertRaises(ToolInputError):
                invoicing.create_draft(**self.ctx_kwargs(self.new_run()), customer_id=self.customer.id,
                                       lines=[InvoiceLineIn(product_id=self.pen.id, quantity=1)],
                                       invoice_discount=None, invoice_discount_type="percent", due_date=None)
            for _ in range(2):                                                            # bulk: its own 2
                invoicing.create_draft(**self.ctx_kwargs(self.new_run()), customer_id=self.customer.id,
                                       lines=[InvoiceLineIn(product_id=self.pen.id, quantity=1)],
                                       invoice_discount=None, invoice_discount_type="percent", due_date=None, source="bulk")
            with self.assertRaises(ToolInputError):
                invoicing.create_draft(**self.ctx_kwargs(self.new_run()), customer_id=self.customer.id,
                                       lines=[InvoiceLineIn(product_id=self.pen.id, quantity=1)],
                                       invoice_discount=None, invoice_discount_type="percent", due_date=None, source="bulk")
        self.assertEqual(set(AgentAction.objects.values_list("source", flat=True)), {"chat", "bulk"})


class BulkStopToolTests(BulkWorld, TransactionTestCase):
    def setUp(self):
        self.build_world()

    def run_tool(self, tool, args):
        ctx = AgentContext(user=self.admin, run_id=str(self.run.id), source="bulk")
        asyncio.run(tool.on_invoke_tool(tool_ctx(ctx, tool.name), json.dumps(args)))
        return ctx.outcome

    def test_needs_attention_records_the_question_and_caps_the_options(self):
        out = self.run_tool(needs_attention, {"question": "Which one?", "options": [f"opt {n}" for n in range(20)] + ["   "]})
        self.assertEqual(out.question, "Which one?")
        self.assertEqual(len(out.options), 8)

    def test_not_an_invoice_records_the_reason(self):
        self.assertEqual(self.run_tool(not_an_invoice, {"reason": "A question about sales"}).not_invoice, "A question about sales")


# =============================================================================== worker


class WorkerCase(BulkWorld, TransactionTestCase):
    def setUp(self):
        self.build_world()
        self.pen = self.stocked_product("PEN-B", "Pen Blue", stock=500, selling_price="230")
        self.r = redis.Redis.from_url(settings.AGENT_REDIS_URL, decode_responses=True)
        self.r.ping()
        self.keys = []

    def tearDown(self):
        for k in self.keys:
            self.r.delete(k)

    def batch(self, prompts=("Sultan Kitab Ghar\nPen Blue 5@228",)):
        batch = self.make_batch(prompts)
        self.keys.append(streaming.batch_key(batch.id))
        return batch

    def work(self, batch, drive, position=1):
        item = self.item(batch, position)
        with mock.patch.object(bulk_runner, "_drive", side_effect=drive):
            asyncio.run(bulk_runner.execute_bulk_item(item.id))
        return self.item(batch, position)

    def events(self, batch):
        return [(f["event"], json.loads(f["data"])) for _i, f in self.r.xrange(streaming.batch_key(batch.id))]


def creates_a_draft(world, **line):
    async def drive(ctx, text):
        await sync_to_async(invoicing.create_draft)(
            user=ctx.user, run_id=ctx.run_id, chat_id=None, customer_id=world.customer.id,
            lines=[InvoiceLineIn(product_id=world.pen.id, quantity=5, **line)],
            invoice_discount=None, invoice_discount_type="percent", due_date=None, source="bulk")
        return "done"
    return drive


class BulkWorkerTests(WorkerCase):
    def test_a_created_draft_makes_the_row_done_and_names_the_customer(self):
        batch = self.batch()
        item = self.work(batch, creates_a_draft(self, unit_rate=228))
        self.assertEqual(item.status, "done")
        self.assertTrue(item.bill_number.startswith("BILL-"))
        self.assertEqual(item.customer_label, "Sultan Kitab Ghar (SKG)")
        self.assertEqual(Invoice.objects.get(pk=item.invoice_id).items.get().discount, Decimal("2"))
        self.assertEqual(item.attempts, 1)
        batch.refresh_from_db()
        self.assertEqual(batch.status, "finished")
        run = ChatRun.objects.get(bulk_item=item)
        self.assertEqual((run.status, run.chat_id), ("done", None))
        self.assertEqual(AgentAction.objects.get().source, "bulk")

    def test_the_model_saying_it_is_done_without_a_draft_is_a_failure_not_a_success(self):
        async def liar(ctx, text):
            return "Done! I created the invoice."
        item = self.work(self.batch(), liar)
        self.assertEqual(item.status, "failed")
        self.assertEqual(item.bill_number, "")
        self.assertIn("did not say why", item.message)
        self.assertEqual(Invoice.objects.count(), 0)

    def test_a_question_marks_the_row_needs_attention_and_the_batch_waiting(self):
        async def asks(ctx, text):
            ctx.outcome.question = "Which Uzair?"
            ctx.outcome.options = ["Uzair - FSD", "Uzair - LHR"]
            return ""
        batch = self.batch()
        item = self.work(batch, asks)
        self.assertEqual((item.status, item.question, item.options), ("needs_attention", "Which Uzair?", ["Uzair - FSD", "Uzair - LHR"]))
        batch.refresh_from_db()
        self.assertEqual(batch.status, "waiting")

    def test_not_an_invoice_request(self):
        async def chatter(ctx, text):
            ctx.outcome.not_invoice = "A question about sales"
            return ""
        item = self.work(self.batch(["what are my sales?"]), chatter)
        self.assertEqual((item.status, item.message), ("not_invoice", "A question about sales"))

    def test_a_crash_after_the_draft_was_created_still_ends_done(self):
        inner = creates_a_draft(self)

        async def create_then_crash(ctx, text):
            await inner(ctx, text)
            raise RuntimeError("boom after the write")
        item = self.work(self.batch(), create_then_crash)
        self.assertEqual(item.status, "done")
        self.assertEqual(Invoice.objects.count(), 1)

    def test_a_failure_before_any_write_is_a_failed_row_with_a_plain_message(self):
        async def slow(ctx, text):
            raise TimeoutError()
        item = self.work(self.batch(), slow)
        self.assertEqual(item.status, "failed")
        self.assertIn("too long", item.message)
        self.assertEqual(ChatRun.objects.get(bulk_item=item).status, "error")

    def test_a_cut_off_stream_is_retried_once_with_a_clean_context_when_nothing_was_written(self):
        calls = []

        async def cut_then_ask(ctx, text):
            calls.append(ctx)
            if len(calls) == 1:
                ctx.outcome.question = "stale partial question"
                raise IncompleteStreamError("cut off")
            ctx.outcome.question = "Which one?"
            return ""
        item = self.work(self.batch(), cut_then_ask)
        self.assertEqual(len(calls), 2)
        self.assertIsNot(calls[0], calls[1])
        self.assertEqual((item.status, item.question), ("needs_attention", "Which one?"))

    def test_a_cut_off_after_a_write_is_never_retried(self):
        calls = []
        inner = creates_a_draft(self)

        async def write_then_cut(ctx, text):
            calls.append(1)
            await inner(ctx, text)
            raise IncompleteStreamError("cut off")
        item = self.work(self.batch(), write_then_cut)
        self.assertEqual(len(calls), 1)
        self.assertEqual((item.status, Invoice.objects.count()), ("done", 1))

    def test_a_duplicate_delivery_does_nothing(self):
        batch = self.batch()
        item = self.item(batch)
        self.assertIsNotNone(bulk.claim_item(item.id))
        self.assertIsNone(bulk.claim_item(item.id))                               # second delivery
        asyncio.run(bulk_runner.execute_bulk_item(item.id))                         # a whole second worker: no agent run
        self.assertEqual(ChatRun.objects.filter(bulk_item=item).count(), 0)

    def test_a_cancelled_batch_skips_rows_that_had_not_started(self):
        batch = self.batch(["a", "b"])
        BulkBatch.objects.filter(pk=batch.pk).update(status="cancelled")
        drive = mock.AsyncMock()
        item = self.work(batch, drive)
        self.assertEqual(item.status, "cancelled")
        drive.assert_not_called()

    def test_the_agent_only_gets_the_prompt_plus_earlier_answers_and_no_history(self):
        batch = self.batch(["Uzair\nPen 5"])
        BulkItem.objects.filter(batch=batch).update(answers=[{"question": "Which Uzair?", "answer": "Lahore one"}])
        seen = []

        async def spy(ctx, text):
            seen.append((text, ctx.source, ctx.chat_id))
            return ""
        self.work(batch, spy)
        text, source, chat_id = seen[0]
        self.assertTrue(text.startswith("Uzair\nPen 5"))
        self.assertIn("Q: Which Uzair?\nA: Lahore one", text)
        self.assertEqual((source, chat_id), ("bulk", None))

    def test_the_answer_round_finishes_the_job(self):
        async def asks(ctx, text):
            ctx.outcome.question = "Which Uzair?"
            return ""
        batch = self.batch()
        self.work(batch, asks)
        with mock.patch.object(tasks.run_bulk_item_task, "delay"):
            bulk.answer_item(item=self.item(batch), answer="Lahore")
        item = self.work(batch, creates_a_draft(self))
        self.assertEqual((item.status, item.attempts), ("done", 2))
        self.assertEqual(ChatRun.objects.filter(bulk_item=item).count(), 2)

    # --- live events ------------------------------------------------------------
    def test_events_follow_each_row_and_the_batch_goes_idle_only_after_the_last_row(self):
        async def asks(ctx, text):
            ctx.outcome.question = "Which?"
            return ""
        batch = self.batch(["a", "b"])
        self.work(batch, asks, position=1)
        mid = [k for k, _ in self.events(batch)]
        self.assertEqual(mid, ["item", "item"])                                    # processing, needs_attention; row 2 still queued
        self.work(batch, creates_a_draft(self), position=2)
        events = self.events(batch)
        kinds = [k for k, _ in events]
        self.assertEqual(kinds, ["item", "item", "item", "item", "batch_idle"])
        self.assertEqual([d["status"] for k, d in events if k == "item"], ["processing", "needs_attention", "processing", "done"])
        self.assertEqual(events[-1][1], {"status": "waiting"})
        done = events[-2][1]
        self.assertEqual((done["position"], done["bill_number"][:5]), (2, "BILL-"))
        self.assertGreater(self.r.ttl(streaming.batch_key(batch.id)), 0)

    def test_a_stale_idle_event_does_not_close_a_stream_whose_next_round_already_started(self):
        batch = self.batch()
        key = streaming.batch_key(batch.id)
        self.r.xadd(key, {"event": "batch_idle", "data": '{"status":"waiting"}'})
        self.r.xadd(key, {"event": "item", "data": json.dumps({"item_id": 1, "position": 1, "status": "queued"})})

        async def collect(active, limit=4):
            async def is_active():
                return active
            frames = []
            with mock.patch.object(streaming, "BLOCK_MS", 150):
                async for frame in streaming.read_events(
                    batch.id, None, is_active, key=key, terminal=frozenset({"batch_idle"}), terminal_needs_idle=True,
                ):
                    frames.append(frame)
                    if len(frames) >= limit:
                        break
            return frames

        running = asyncio.run(collect(True))
        self.assertIn("event: batch_idle", running[0])
        self.assertIn("event: item", running[1])
        self.assertTrue(running[2].startswith(": ping"))                           # still open: waiting for the next round
        finished = asyncio.run(collect(False))
        self.assertEqual(len(finished), 1)                                         # idle really means idle: the stream closes
        self.assertIn("event: batch_idle", finished[0])

    def test_the_stream_of_an_empty_idle_batch_ends_with_batch_idle_not_an_error(self):
        batch = self.batch()

        async def collect():
            async def is_active():
                return False
            with mock.patch.object(streaming, "BLOCK_MS", 100):
                return [f async for f in streaming.read_events(
                    batch.id, None, is_active, key=streaming.batch_key(batch.id),
                    terminal=frozenset({"batch_idle"}), terminal_needs_idle=True)]
        frames = asyncio.run(collect())
        self.assertEqual(len(frames), 1)
        self.assertIn("event: batch_idle", frames[0])

    def test_rows_run_in_order_and_later_rows_see_the_stock_earlier_drafts_reserved(self):
        small = self.stocked_product("SMALL", "Small Item", stock=10, selling_price="100")
        batch = self.batch(["x", "y"])

        def drive_for(qty):
            async def drive(ctx, text):
                try:
                    await sync_to_async(invoicing.create_draft)(
                        user=ctx.user, run_id=ctx.run_id, chat_id=None, customer_id=self.customer.id,
                        lines=[InvoiceLineIn(product_id=small.id, quantity=qty)], invoice_discount=None,
                        invoice_discount_type="percent", due_date=None, source="bulk")
                except ToolInputError as exc:
                    ctx.outcome.question = str(exc)[:200]
                return ""
            return drive
        first = self.work(batch, drive_for(8), position=1)
        second = self.work(batch, drive_for(8), position=2)       # only 2 left after the first draft reserved 8
        self.assertEqual((first.status, second.status), ("done", "needs_attention"))
        self.assertIn("Insufficient stock", second.question)


class BulkSelectorTests(BulkWorld, TestCase):
    def setUp(self):
        self.build_world()

    def test_area_narrows_same_name_customers_by_address(self):
        create_customer(name="Uzair", code="U1", address="Satiana Road, Faisalabad", user=self.admin)
        create_customer(name="Uzair", code="U2", address="Model Town, Lahore", user=self.admin)
        unique, _ = sel.find_customers(search="uzair", code=None)
        self.assertIsNone(unique)
        unique, _ = sel.find_customers(search="uzair", code=None, area="lahore")
        self.assertEqual(unique.code, "U2")
        unique, candidates = sel.find_customers(search="uzair", code=None, area="  ")        # blank area: ignored
        self.assertEqual(len(candidates), 2)
