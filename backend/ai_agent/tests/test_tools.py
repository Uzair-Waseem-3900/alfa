import json
from datetime import date
from unittest import mock

from agents import RunContextWrapper
from django.test import SimpleTestCase, TransactionTestCase
from django.utils import timezone

from ai_agent.instructions.base import build_instructions
from ai_agent.my_tool import ALL_TOOLS, STEP_LABELS
from ai_agent.my_tool.base import MAX_TOOL_CHARS, ToolInputError, agent_tool, to_text
from ai_agent.my_tool.guide_tool import TOPICS
from ai_agent.my_tool.periods import resolve_period
from ai_agent.schemas.context import AgentContext

from .helpers import make_admin, tool_ctx


class PeriodTests(SimpleTestCase):
    def test_named_periods_use_local_calendar_day(self):
        fake_today = date(2026, 11, 12)   # a Thursday
        with mock.patch("ai_agent.my_tool.periods.timezone.localdate", return_value=fake_today):
            self.assertEqual(resolve_period("today").date_from, fake_today)
            self.assertEqual(resolve_period("yesterday").date_from, date(2026, 11, 11))
            self.assertEqual(resolve_period("this_week").date_from, date(2026, 11, 9))
            m = resolve_period("this_month")
            self.assertEqual((m.date_from, m.date_to), (date(2026, 11, 1), fake_today))
            lm = resolve_period("last_month")
            self.assertEqual((lm.date_from, lm.date_to), (date(2026, 10, 1), date(2026, 10, 31)))
            ly = resolve_period("last_year")
            self.assertEqual((ly.date_from, ly.date_to), (date(2025, 1, 1), date(2025, 12, 31)))
            self.assertEqual(resolve_period("last_7_days").date_from, date(2026, 11, 6))

    def test_january_last_month_rolls_back_a_year(self):
        with mock.patch("ai_agent.my_tool.periods.timezone.localdate", return_value=date(2027, 1, 15)):
            lm = resolve_period("last_month")
            self.assertEqual((lm.date_from, lm.date_to), (date(2026, 12, 1), date(2026, 12, 31)))

    def test_all_time_and_custom(self):
        self.assertTrue(resolve_period("all_time").is_all_time)
        c = resolve_period("custom", "2026-01-01", "2026-01-31")
        self.assertEqual((c.from_str, c.to_str), ("2026-01-01", "2026-01-31"))

    def test_bad_custom_dates_are_tool_errors(self):
        for args in [("custom", None, None), ("custom", "2026-13-01", "2026-01-01"), ("custom", "2026-02-01", "2026-01-01")]:
            with self.assertRaises(ToolInputError):
                resolve_period(*args)


class HelperTests(SimpleTestCase):
    def test_to_text_truncates_and_serialises(self):
        from decimal import Decimal
        self.assertEqual(to_text({"a": Decimal("1.50"), "d": date(2026, 1, 2)}), '{"a":"1.50","d":"2026-01-02"}')
        self.assertLessEqual(len(to_text({"x": "y" * 20000})), MAX_TOOL_CHARS + 80)
        self.assertIn("truncated", to_text({"x": "y" * 20000}))

    def test_every_tool_has_a_step_label_and_guides_exist(self):
        for t in ALL_TOOLS:
            self.assertIn(t.name, STEP_LABELS)
        from ai_agent.my_tool.guide_tool import GUIDES_DIR
        self.assertTrue((GUIDES_DIR / "about.md").is_file())

    def test_wrapper_error_handling(self):
        user = mock.Mock()

        @agent_tool
        def boom(ctx: RunContextWrapper[AgentContext]) -> str:
            """boom"""
            raise RuntimeError("secret internals")

        @agent_tool
        def bad_input(ctx: RunContextWrapper[AgentContext]) -> str:
            """bad"""
            raise ToolInputError("dates are wrong")

        import asyncio
        ctx = tool_ctx(mock.Mock(user=user))
        out = asyncio.run(boom.on_invoke_tool(ctx, "{}"))
        self.assertNotIn("secret internals", out)          # never leak internals to the LLM
        self.assertIn("went wrong", out)
        self.assertEqual(asyncio.run(bad_input.on_invoke_tool(ctx, "{}")), "Cannot do that: dates are wrong")


class PromptTests(SimpleTestCase):
    def test_prompt_is_short_static_prefix_plus_dynamic_tail(self):
        user = mock.Mock(first_name="Awaab", last_name="Sohail", email="a@x.com", role="admin")
        text = build_instructions(RunContextWrapper(context=AgentContext(user=user)), None)
        self.assertIn("Today:", text.splitlines()[-1])
        self.assertIn("Awaab Sohail (admin)", text.splitlines()[-1])
        self.assertTrue(all(t in text for t in TOPICS))
        self.assertLess(len(text) // 4, 500, "base prompt must stay small (~tokens)")


class ToolSmokeTests(TransactionTestCase):
    """Every tool must run end-to-end through the real SDK path (schema
    validation -> worker thread -> selector) on an empty database."""

    def setUp(self):
        self.user = make_admin()

    def _run(self, name, args=None):
        import asyncio
        tool = next(t for t in ALL_TOOLS if t.name == name)
        return asyncio.run(tool.on_invoke_tool(tool_ctx(AgentContext(user=self.user), name), json.dumps(args or {})))

    def test_all_tools_run_on_empty_db(self):
        calls = {
            "get_guide": {"topic": "about"},
            "business_snapshot": {}, "business_worth": {},
            "sales_summary": {"period": "this_month"},
            "find_invoices": {"customer_name": "ali", "period": "last_30_days"},
            "customer_info": {"search": "ali"}, "customers_who_owe": {},
            "supplier_info": {"search": "x"}, "suppliers_we_owe": {},
            "product_stock": {"search": "rice"}, "stock_alerts": {"kind": "low"},
            "expenses_summary": {"period": "this_year", "list_recent": True},
            "profit_report": {"view": "current_month"},
            "tax_position": {},
        }
        self.assertEqual(set(calls), {t.name for t in ALL_TOOLS}, "a tool has no smoke test")
        for name, args in calls.items():
            out = self._run(name, args)
            self.assertFalse(out.startswith("The tool failed"), f"{name}: {out}")
            self.assertFalse(out.startswith("Cannot do that"), f"{name}: {out}")

    def test_all_time_sales_summary_and_bad_period(self):
        self.assertIn('"invoices":0', self._run("sales_summary", {"period": "all_time"}))
        self.assertIn("Cannot do that", self._run("sales_summary", {"period": "custom"}))   # missing dates

    def test_enum_is_enforced_by_schema(self):
        out = self._run("stock_alerts", {"kind": "banana"})
        self.assertNotIn('"showing"', out)    # rejected before reaching the selector

    def test_get_guide_content(self):
        out = self._run("get_guide", {"topic": "about"})
        self.assertIn("Uzair Waseem", out)
        self.assertIn("Sohail Iqbal", out)
        self.assertIn("Awaab Sohail", out)

    # --- 3-match cap on customer_info / supplier_info -------------------------
    def test_customer_info_gives_figures_for_three_and_names_for_the_rest(self):
        from billing.models import Customer
        from billing.selectors import get_customer_outstanding
        for i in range(8):
            Customer.objects.create(name=f"Book Depot {i}", code=f"BD-{i}", mobile=f"030{i}")

        with mock.patch("billing.selectors.get_customer_outstanding", wraps=get_customer_outstanding) as per_customer:
            data = json.loads(self._run("customer_info", {"search": "book depot"}))

        self.assertEqual(per_customer.call_count, 3)                      # 1 query per detailed match, no more
        self.assertEqual(len(data["customers"]), 3)
        self.assertEqual(len(data["other_matches_names_only"]), 3)        # up to 6 listed in total
        self.assertEqual(data["matches_shown"], 6)
        self.assertTrue(data["more_matches_not_shown"])                    # 8 matched, 6 shown
        self.assertNotIn("still_owes", data["other_matches_names_only"][0])
        self.assertIn("still_owes", data["customers"][0])

    def test_customer_info_with_few_matches_has_no_extras(self):
        from billing.models import Customer
        Customer.objects.create(name="Solo Traders", code="ST-1", mobile="0300")
        data = json.loads(self._run("customer_info", {"search": "solo"}))
        self.assertEqual((len(data["customers"]), data["other_matches_names_only"], data["more_matches_not_shown"]),
                         (1, [], False))

    def test_supplier_info_gives_figures_for_three_and_names_for_the_rest(self):
        from purchases.models import Supplier
        from purchases.selectors import get_supplier_payable_summary
        for i in range(5):
            Supplier.objects.create(name=f"Paper Mill {i}", code=f"PM-{i}")

        with mock.patch("purchases.selectors.get_supplier_payable_summary", wraps=get_supplier_payable_summary) as per_supplier:
            data = json.loads(self._run("supplier_info", {"search": "paper mill"}))

        self.assertEqual(per_supplier.call_count, 3)
        self.assertEqual((len(data["suppliers"]), len(data["other_matches_names_only"]), data["more_matches_not_shown"]),
                         (3, 2, False))

