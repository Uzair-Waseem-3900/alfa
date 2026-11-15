"""Fixes from the independent audit of the invoice write tools."""
import re
from decimal import Decimal
from unittest import mock

from django.db import IntegrityError, connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from pydantic import ValidationError as PydanticValidationError

from billing.models import Invoice, InvoiceItemShelfAllocation
from billing.services import create_customer

from ai_agent.exceptions import ToolInputError
from ai_agent.models import AgentAction
from ai_agent.schemas.invoice import InvoiceLineIn
from ai_agent.services import invoicing

from .test_invoice_services import WorldTestCase, line


class BudgetHardeningTests(WorldTestCase):
    @override_settings(AGENT_WRITES_PER_RUN=2)
    def test_per_run_cap_stops_a_flood_of_calls_in_one_question(self):
        self.create([line(self.pen, 1)])
        self.create([line(self.pen, 2)])
        with self.assertRaises(ToolInputError) as cm:
            self.create([line(self.pen, 3)])
        self.assertIn("per request", str(cm.exception))
        self.create([line(self.pen, 3)], run=self.new_run())           # a new question has its own allowance
        self.assertEqual(Invoice.objects.count(), 3)

    def test_the_budget_is_re_counted_under_the_lock_before_writing(self):
        """Parallel calls all pass the unlocked pre-check; the locked re-count must still stop the late ones."""
        with mock.patch.object(invoicing.sel, "count_writes_since", side_effect=[0, 99]):
            with self.assertRaises(ToolInputError) as cm:
                self.create([line(self.pen, 1)])
        self.assertIn("hourly limit", str(cm.exception))
        self.assertEqual((Invoice.objects.count(), AgentAction.objects.count()), (0, 0))   # nothing half-written

    def test_the_user_row_is_locked_for_the_whole_write(self):
        with mock.patch.object(invoicing, "get_user_model") as get_model:
            get_model.return_value.objects.select_for_update.return_value.get.return_value = self.admin
            self.create([line(self.pen, 1)])
        get_model.return_value.objects.select_for_update.assert_called()


class QueryEfficiencyTests(WorldTestCase):
    def test_products_are_loaded_in_one_query_with_their_price(self):
        with CaptureQueriesContext(connection) as q:
            products = invoicing._load_products([self.pen.id, self.book.id])
            _ = [p.rate.selling_price for p in products.values()]      # the price must not cost extra queries
        self.assertEqual(len(q), 1, [x["sql"][:80] for x in q.captured_queries])

    def test_an_unknown_product_id_is_a_plain_error(self):
        with self.assertRaises(ToolInputError) as cm:
            invoicing._load_products([self.pen.id, 999999])
        self.assertIn("#999999", str(cm.exception))


class MarkdownSafetyTests(WorldTestCase):
    def test_hostile_names_cannot_break_the_table_or_plant_links_and_images(self):
        evil_customer = create_customer(name="Evil | ![x](http://evil.test/p.png?d=1) [click](http://evil.test)\nSecond line",
                                        code="EV|IL", address="a", user=self.admin)
        evil_product = self.stocked_product("P|9", "Pen | ![img](http://evil.test/i.png)", stock=10, selling_price="10")
        result = self.create([line(evil_product, 2)], customer_id=evil_customer.id)
        md = result["summary_markdown"]

        self.assertNotIn("\n", md.split("**Customer:**")[1].split("\n")[0].replace("Second line", ""))   # one line
        self.assertNotIn("![x](", md)
        self.assertNotIn("![img](", md)
        self.assertNotIn("[click](", md)
        self.assertIn(r"\!\[x\]\(http://evil.test/p.png?d=1\)", md)                    # shown as harmless text
        row = next(r for r in md.split("\n") if r.startswith("| Pen"))
        self.assertEqual(len(re.findall(r"(?<!\\)\|", row)), 8)                       # 7 cells, nothing broke out
        self.assertIn("[Open this draft in the app](/billing/invoices/", md)         # our own link is untouched

    def test_md_helper(self):
        self.assertEqual(invoicing._md("a|b *c* _d_ `e`"), r"a\|b \*c\* \_d\_ \`e\`")
        self.assertEqual(invoicing._md("line1\n\n  line2"), "line1 line2")
        self.assertEqual(invoicing._md(None), "")


class ReplayAndDiscardHardeningTests(WorldTestCase):
    def test_replaying_a_call_whose_invoice_was_since_discarded_says_so_plainly(self):
        run_a = self.new_run()
        made = self.create([line(self.pen, 2)], run=run_a)
        self.discard(made["bill_number"], run=self.new_run())
        with self.assertRaises(ToolInputError) as cm:
            self.create([line(self.pen, 2)], run=run_a)                # same run, same args -> replay of a gone invoice
        self.assertIn("no longer exists", str(cm.exception))

    def test_a_real_integrity_error_during_discard_is_not_reported_as_success(self):
        made = self.create([line(self.pen, 2)])
        with mock.patch.object(invoicing, "delete_invoice", side_effect=IntegrityError("something else broke")):
            with self.assertRaises(IntegrityError):
                self.discard(made["bill_number"], run=self.new_run())
        self.assertTrue(Invoice.objects.filter(pk=made["invoice_id"]).exists())          # still there, and we did not claim otherwise

    def test_losing_the_discard_race_returns_the_winners_result(self):
        made = self.create([line(self.pen, 2)])
        run = self.new_run()
        self.discard(made["bill_number"], run=run)
        winner = AgentAction.objects.get(tool="discard_draft_invoice")
        # the pre-check misses, billing then raises IntegrityError, the re-check finds the winner
        invoice = Invoice.all_objects.get(pk=made["invoice_id"])
        with mock.patch.object(invoicing.sel, "get_invoice_by_bill", return_value=invoice), \
             mock.patch.object(invoicing, "_repeat_of", side_effect=[None, winner]), \
             mock.patch.object(invoicing, "delete_invoice", side_effect=IntegrityError("dup")):
            result = self.discard(made["bill_number"], run=run)
        self.assertTrue(result["already_done_earlier_in_this_request"])


class InputHardeningTests(WorldTestCase):
    @override_settings(AGENT_INVOICE_MAX_LINES=2)
    def test_update_sizes_are_checked_before_any_lookup_work(self):
        bill = self.create([line(self.pen, 1)])["bill_number"]
        three = [InvoiceLineIn(product_id=self.pen.id, quantity=1)] * 3
        with CaptureQueriesContext(connection) as q:
            with self.assertRaises(ToolInputError):
                self.update(bill, set_lines=three, run=self.new_run())
        self.assertLessEqual(len(q), 3)                                # budget pre-check only, no per-line work
        with self.assertRaises(ToolInputError):
            self.update(bill, remove_product_ids=[1, 2, 3], run=self.new_run())

    def test_odd_numbers_are_refused_or_rounded_explicitly(self):
        with self.assertRaises(ToolInputError):
            self.create([line(self.pen, 1)], invoice_discount=float("nan"), run=self.new_run())
        with self.assertRaises(ToolInputError):
            self.create([line(self.pen, 1)], invoice_discount=float("inf"), run=self.new_run())
        for bad in (float("nan"), float("inf")):
            with self.assertRaises(PydanticValidationError):
                InvoiceLineIn(product_id=1, quantity=1, gst=bad)
        item = self.invoice_of(self.create([line(self.pen, 1, gst=7.555)], run=self.new_run())).items.get()
        self.assertEqual(item.gst, Decimal("7.56"))                    # rounded by us, half-up, not silently by the database

    def test_unknown_line_fields_are_refused_not_ignored(self):
        for extra in ({"price": 5}, {"advance": 100}, {"status": "confirmed"}):
            with self.assertRaises(PydanticValidationError, msg=str(extra)):
                InvoiceLineIn(product_id=1, quantity=1, **extra)


class HeadsUpTests(WorldTestCase):
    def test_a_free_line_is_called_out(self):
        result = self.create([line(self.pen, 2, discount_percent=100)])
        self.assertIn("Heads-up:", result["summary_markdown"])
        self.assertIn("is free", result["summary_markdown"])

    def test_an_edit_that_clears_shelf_choices_says_so(self):
        made = self.create([line(self.pen, 4)])
        inv = self.invoice_of(made)
        self.allocate_invoice(inv)
        self.assertEqual(InvoiceItemShelfAllocation.objects.count(), 1)

        edited = self.update(made["bill_number"], set_lines=[line(self.pen, 5)], run=self.new_run())
        self.assertEqual(InvoiceItemShelfAllocation.objects.count(), 0)               # billing replaced the lines
        self.assertIn("shelf choices", edited["summary_markdown"])
        self.assertIn("set them again in the Billing page", edited["summary_markdown"])

    def test_no_shelf_note_when_there_were_no_shelf_choices(self):
        made = self.create([line(self.pen, 4)])
        edited = self.update(made["bill_number"], set_lines=[line(self.pen, 5)], run=self.new_run())
        self.assertNotIn("Heads-up", edited["summary_markdown"])
