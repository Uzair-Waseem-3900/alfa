"""Regressions for the independent audit of the bulk-invoice feature."""
import asyncio
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.db import IntegrityError, transaction
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from billing.models import Invoice

from ai_agent import tasks
from ai_agent.exceptions import ToolInputError
from ai_agent.models import BulkBatch, BulkItem, ChatRun
from ai_agent.schemas.invoice import InvoiceLineIn
from ai_agent.services import bulk, bulk_runner, invoicing

from .test_bulk import BulkWorld, WorkerCase, creates_a_draft


def draft(world, run, qty=1, source="bulk", **line):
    return invoicing.create_draft(
        **{**world.ctx_kwargs(run), "chat_id": None}, customer_id=world.customer.id,
        lines=[InvoiceLineIn(product_id=world.pen.id, quantity=qty, **line)],
        invoice_discount=None, invoice_discount_type="percent", due_date=None, source=source)


class OneInvoicePerBulkRowTests(WorkerCase):
    def test_a_bulk_run_cannot_create_a_second_draft_but_chat_keeps_its_own_limit(self):
        run = self.new_run()
        draft(self, run)
        with self.assertRaises(ToolInputError) as cm:
            draft(self, run, qty=2)                                   # e.g. a row naming two customers
        self.assertIn("only one invoice", str(cm.exception))
        self.assertEqual(Invoice.objects.count(), 1)
        for n in range(3):                                            # chat: several changes per request are fine
            draft(self, self.new_run() if n else run, qty=1, source="chat")


class SkipAndRetryNeverHideADraftTests(WorkerCase):
    def test_skip_after_a_timed_out_run_whose_tool_thread_still_committed_reports_done(self):
        batch = self.batch()
        item = self.item(batch)
        run = ChatRun.objects.create(chat=None, bulk_item=item, user_message="x", status="error")
        made = draft(self, run)
        BulkItem.objects.filter(pk=item.pk).update(status="failed", message="That took too long", attempts=1)
        out = bulk.skip_item(item=self.item(batch))
        self.assertEqual((out.status, out.bill_number), ("done", made["bill_number"]))

    def test_answer_and_retry_are_refused_in_a_cancelled_batch(self):
        batch = self.batch()
        BulkItem.objects.filter(batch=batch).update(status="needs_attention", question="q", attempts=1)
        BulkBatch.objects.filter(pk=batch.pk).update(status="cancelled")
        item = BulkItem.objects.select_related("batch").get(batch=batch)
        with self.assertRaises(ValidationError):
            bulk.answer_item(item=item, answer="yes")
        BulkItem.objects.filter(pk=item.pk).update(status="failed")
        with self.assertRaises(ValidationError):
            bulk.retry_item(item=BulkItem.objects.select_related("batch").get(pk=item.pk))


class LostTaskTests(WorkerCase):
    def test_queued_rows_whose_tasks_were_lost_are_queued_again_once_in_a_while(self):
        batch = self.batch(["a", "b"])
        old = timezone.now() - timedelta(seconds=bulk.QUEUE_LOST_AFTER_SECONDS + 5)
        BulkItem.objects.filter(batch=batch).update(updated_at=old)
        with mock.patch.object(tasks.run_bulk_item_task, "delay") as delay:
            bulk.resolve_stale_rows(batch.id)
            self.assertEqual([c.args[0] for c in delay.call_args_list], list(BulkItem.objects.order_by("position").values_list("id", flat=True)))
            bulk.resolve_stale_rows(batch.id)                          # touched: not again within the window
            self.assertEqual(delay.call_count, 2)

    def test_rows_waiting_behind_a_processing_row_are_not_requeued(self):
        batch = self.batch(["a", "b"])
        old = timezone.now() - timedelta(hours=1)
        BulkItem.objects.filter(batch=batch).update(updated_at=old)
        BulkItem.objects.filter(batch=batch, position=1).update(status="processing", started_at=timezone.now())
        with mock.patch.object(tasks.run_bulk_item_task, "delay") as delay:
            bulk.resolve_stale_rows(batch.id)
        delay.assert_not_called()


class RedisBlipTests(WorkerCase):
    def test_redis_down_when_the_row_starts_does_not_fail_the_row(self):
        batch = self.batch()
        real = bulk_runner._publish_state

        async def flaky(publisher, item_id, batch_id, *, idle_check):
            if not idle_check:
                raise ConnectionError("redis down")
            return await real(publisher, item_id, batch_id, idle_check=idle_check)
        with mock.patch.object(bulk_runner, "_publish_state", flaky):
            item = self.work(batch, creates_a_draft(self))
        self.assertEqual(item.status, "done")
        self.assertEqual(item.attempts, 1)


class ConstraintTests(WorkerCase):
    def test_a_bulk_row_cannot_have_two_active_runs(self):
        item = self.item(self.batch())
        ChatRun.objects.create(chat=None, bulk_item=item, user_message="x", status="running")
        with self.assertRaises(IntegrityError), transaction.atomic():
            ChatRun.objects.create(chat=None, bulk_item=item, user_message="y", status="queued")
        ChatRun.objects.filter(bulk_item=item).update(status="done")
        ChatRun.objects.create(chat=None, bulk_item=item, user_message="z", status="running")   # a later attempt is fine


class QtyAtRateEdgeTests(BulkWorld, TransactionTestCase):
    def setUp(self):
        self.build_world()
        self.pen = self.stocked_product("PEN-B", "Pen Blue", stock=500, selling_price="230")

    def create(self, **line):
        return invoicing.create_draft(**self.ctx_kwargs(), customer_id=self.customer.id,
                                      lines=[InvoiceLineIn(product_id=self.pen.id, quantity=1, **line)],
                                      invoice_discount=None, invoice_discount_type="percent", due_date=None)

    def test_the_boundaries_exactly_double_is_allowed_and_one_rupee_more_is_not(self):
        ok = self.create(unit_rate=460)                                # list Rs 230 -> a Rs 230 surcharge, the maximum
        self.assertEqual(Invoice.objects.get(pk=ok["invoice_id"]).items.get().discount, Decimal("-230"))
        with self.assertRaises(ToolInputError):
            invoicing.create_draft(**self.ctx_kwargs(self.new_run()), customer_id=self.customer.id,
                                   lines=[InvoiceLineIn(product_id=self.pen.id, quantity=1, unit_rate=461)],
                                   invoice_discount=None, invoice_discount_type="percent", due_date=None)

    def test_a_rate_below_one_paisa_is_refused_by_the_schema(self):
        for bad in (0.001, 0.004):
            with self.assertRaises(Exception):
                InvoiceLineIn(product_id=1, quantity=1, unit_rate=bad)

    def test_the_note_states_the_rate_that_was_actually_stored(self):
        result = self.create(unit_rate=228.555)
        stored_discount = Invoice.objects.get(pk=result["invoice_id"]).items.get().discount
        self.assertIn(f"Rs {Decimal('230') - stored_discount:,.2f}", result["summary_markdown"])
