"""A created bulk row shows what was created: each line (qty, rate charged, line total) and the grand total,
taken from billing's own print context and snapshotted when the row becomes done."""
from decimal import Decimal
from unittest import mock

from asgiref.sync import sync_to_async
from django.core.cache import cache

from billing.models import Invoice
from billing.services import delete_invoice
from billing.utils import get_invoice_print_context

from ai_agent import tasks, views
from ai_agent.models import BulkItem, ChatRun
from ai_agent.schemas.invoice import InvoiceLineIn
from ai_agent.services import bulk, invoicing

from .test_api import call
from .test_bulk import WorkerCase, creates_a_draft


def drive_with(world, *, lines, invoice_discount=None):
    async def drive(ctx, text):
        await sync_to_async(invoicing.create_draft)(
            user=ctx.user, run_id=ctx.run_id, chat_id=None, customer_id=world.customer.id, lines=lines,
            invoice_discount=invoice_discount, invoice_discount_type="percent", due_date=None, source="bulk")
        return ""
    return drive


class BulkRowSummaryTests(WorkerCase):
    def test_lines_rates_and_grand_total_are_stored_and_equal_billings_numbers(self):
        item = self.work(self.batch(), drive_with(self, lines=[InvoiceLineIn(product_id=self.pen.id, quantity=5, unit_rate=228)]))
        self.assertEqual(item.status, "done")
        line = item.summary["lines"][0]
        self.assertEqual((line["product"], line["quantity"], line["rate"], line["list_rate"], line["line_total"]),
                         ("Pen Blue", 5, "228.00", "230.00", "1140.00"))              # 5 x (230 - 2)
        invoice = Invoice.objects.get(pk=item.invoice_id)
        self.assertEqual(Decimal(item.summary["grand_total"]), get_invoice_print_context(invoice)["grand_total"])
        self.assertEqual(item.summary["grand_total"], "1140.00")
        self.assertIsNone(item.summary["invoice_discount"])

    def test_a_surcharge_shows_the_higher_rate_and_an_invoice_discount_is_listed(self):
        item = self.work(self.batch(), drive_with(
            self, lines=[InvoiceLineIn(product_id=self.pen.id, quantity=10, discount_amount=-2)], invoice_discount=1))
        line = item.summary["lines"][0]
        self.assertEqual((line["rate"], line["list_rate"], line["line_total"]), ("232.00", "230.00", "2320.00"))
        self.assertEqual((item.summary["invoice_discount"], item.summary["invoice_discount_percent"]), ("23.20", "1"))
        self.assertEqual(item.summary["grand_total"], "2296.80")                          # 2320 less 1%

    def test_the_live_event_carries_the_summary_so_the_page_needs_no_reload(self):
        batch = self.batch()
        self.work(batch, creates_a_draft(self))
        done = [d for k, d in self.events(batch) if k == "item" and d["status"] == "done"][0]
        self.assertEqual(done["summary"]["lines"][0]["quantity"], 5)
        self.assertTrue(done["summary"]["grand_total"])

    def test_non_created_rows_have_no_summary(self):
        async def asks(ctx, text):
            ctx.outcome.question = "Which?"
            return ""
        self.assertEqual(self.work(self.batch(), asks).summary, {})

    def test_the_detail_api_returns_it(self):
        cache.clear()
        batch = self.batch()
        self.work(batch, creates_a_draft(self))
        r = call(views.BulkBatchDetailView.as_view(), "get", "/b/x/", self.admin, batch_id=batch.id)
        self.assertEqual(r.data["items"][0]["summary"]["lines"][0]["product"], "Pen Blue")

    def test_a_draft_deleted_before_the_summary_could_be_read_still_ends_done_without_one(self):
        batch = self.batch()
        item = self.item(batch)
        run = ChatRun.objects.create(chat=None, bulk_item=item, user_message="x", status="error")
        made = invoicing.create_draft(**{**self.ctx_kwargs(run), "chat_id": None}, customer_id=self.customer.id,
                                      lines=[InvoiceLineIn(product_id=self.pen.id, quantity=1)], invoice_discount=None,
                                      invoice_discount_type="percent", due_date=None, source="bulk")
        BulkItem.objects.filter(pk=item.pk).update(status="failed", attempts=1)
        delete_invoice(invoice_id=made["invoice_id"], user=self.admin)
        with mock.patch.object(tasks.run_bulk_item_task, "delay"):
            out = bulk.retry_item(item=BulkItem.objects.select_related("batch").get(pk=item.pk))
        self.assertEqual((out.status, out.bill_number, out.summary), ("done", made["bill_number"], {}))
