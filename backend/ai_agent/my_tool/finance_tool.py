"""Expenses, profit and tax."""
from typing import Literal

from agents import RunContextWrapper

from ..schemas.context import AgentContext
from ..schemas.tools import PeriodName
from .base import agent_tool, clamp_limit, money, to_text
from .periods import resolve_period


@agent_tool
def expenses_summary(
    ctx: RunContextWrapper[AgentContext],
    period: PeriodName = "this_month",
    date_from: str | None = None,
    date_to: str | None = None,
    search: str | None = None,
    list_recent: bool = False,
    limit: int = 10,
) -> str:
    """Total business expenses for a period (count and amount), optionally filtered by a word in the
    expense name, and optionally the most recent individual expenses.

    Args:
        period: Named window; "custom" uses date_from/date_to (YYYY-MM-DD).
        search: Word in the expense name.
        list_recent: True to also list the latest expenses.
        limit: Max rows when list_recent is True (capped).
    """
    from cash_flow.selectors import get_all_expenses, get_expenses_summary

    p = resolve_period(period, date_from, date_to)
    kw = {"date_from": p.from_str, "date_to": p.to_str, "search": search}
    s = get_expenses_summary(**kw)
    out = {"period": p.label, "expenses": s["count"], "total_amount": money(s["total_amount"])}
    if list_recent:
        out["recent"] = [
            {
                "date": e.expense_date.isoformat(), "name": e.name,
                "category": e.category.name if e.category_id else None,
                "amount": money(e.amount),
            }
            for e in get_all_expenses(**kw)[: clamp_limit(limit)]
        ]
    return to_text(out)


@agent_tool
def profit_report(
    ctx: RunContextWrapper[AgentContext],
    view: Literal["current_month", "monthly_trend", "lifetime"] = "current_month",
    months: int = 6,
) -> str:
    """Profit figures.

    Args:
        view: "current_month" = live provisional profit of the open month (revenue, costs, net profit);
              "monthly_trend" = finalized net profit for each of the last `months` months;
              "lifetime" = all-time profit totals and how much went to investors/owner.
        months: Number of months for monthly_trend (1-24).
    """
    from profits.selectors import get_current_month_net_profit_only, get_net_profit_trend, get_profit_flow_stats

    if view == "current_month":
        data = get_current_month_net_profit_only()
    elif view == "monthly_trend":
        data = {"months": get_net_profit_trend(months=max(1, min(months, 24)))}
    else:
        data = get_profit_flow_stats()
    return to_text(_stringify_money(data))


@agent_tool
def tax_position(ctx: RunContextWrapper[AgentContext]) -> str:
    """Sales tax (input/output, net payable, paid, outstanding) and withholding tax (WHT) position. All-time."""
    from taxes.selectors import get_tax_stats

    return to_text({k: money(v) for k, v in get_tax_stats().items()})


def _stringify_money(obj):
    """Decimals -> 2dp strings, recursively (profit selectors return nested dicts/lists)."""
    from decimal import Decimal

    if isinstance(obj, Decimal):
        return money(obj)
    if isinstance(obj, dict):
        return {k: _stringify_money(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_stringify_money(v) for v in obj]
    return obj
