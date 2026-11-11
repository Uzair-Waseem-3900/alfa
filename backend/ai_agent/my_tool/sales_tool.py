from decimal import Decimal

from agents import RunContextWrapper
from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from ..schemas.context import AgentContext
from ..schemas.tools import InvoiceStatus, PaymentStatus, PeriodName
from .base import agent_tool, clamp_limit, money, to_text
from .periods import resolve_period


@agent_tool
def sales_summary(
    ctx: RunContextWrapper[AgentContext],
    period: PeriodName = "this_month",
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """Sales performance for a period: invoice count and billed total, cash collected, customer returns,
    gross profit and net-of-returns profit.

    Args:
        period: Named window; use "custom" with date_from/date_to (YYYY-MM-DD) for any other range.
        date_from: Only for period="custom".
        date_to: Only for period="custom".
    """
    from reports import selectors as r

    p = resolve_period(period, date_from, date_to)
    if p.is_all_time:
        inv = r.get_invoices_report_stats_all_time()
        cash = r.get_cash_collected_report_stats_all_time()
        ret = r.get_customer_returns_report_stats_all_time()
        margin = r.get_profit_margin_report_stats_all_time()
    else:
        kw = {"date_from": p.from_str, "date_to": p.to_str}
        inv = r.get_invoices_report_stats(r.get_invoices_report_queryset(**kw))
        cash = r.get_cash_collected_report_stats(r.get_cash_collected_report_queryset(**kw))
        ret = r.get_customer_returns_report_stats(r.get_customer_returns_report_queryset(**kw))
        margin = r.get_profit_margin_report_stats(r.get_profit_margin_report_queryset(**kw), **kw)

    return to_text({
        "period": p.label,
        "invoices": inv["total_invoices"],
        "billed_total": money(inv["total_invoices_cash"]),
        "cash_collected": money(cash["total_cash_collected"]),
        "customer_returns": {"count": ret["total_returns"], "value": money(ret["total_return_value"])},
        "gross_profit": money(margin["total_gross_profit"]),
        "net_revenue_after_returns": money(margin["net_revenue"]),
        "net_gross_profit_after_returns": money(margin["net_gross_profit"]),
    })


@agent_tool
def find_invoices(
    ctx: RunContextWrapper[AgentContext],
    bill_number: str | None = None,
    customer_name: str | None = None,
    status: InvoiceStatus | None = None,
    payment_status: PaymentStatus | None = None,
    only_with_balance_due: bool = False,
    period: PeriodName = "all_time",
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 10,
) -> str:
    """List invoices (newest first) with their total, paid and still-owed amounts.
    Returns the matching count/total owed plus up to `limit` rows.

    Args:
        bill_number: Exact or partial bill number.
        customer_name: Partial customer name.
        only_with_balance_due: True to list only invoices customers still owe money on.
        period: Window by invoice creation date; "custom" uses date_from/date_to (YYYY-MM-DD).
        limit: Max rows (capped).
    """
    from billing.selectors import get_filtered_invoices_lean

    p = resolve_period(period, date_from, date_to)
    qs = get_filtered_invoices_lean(
        bill_number=bill_number, customer_name=customer_name, status=status,
        payment_status=payment_status, date_from=p.from_str, date_to=p.to_str,
        outstanding_only=only_with_balance_due,
    )
    # Same queryset as the list below -> count/total can never disagree with
    # the rows. One aggregate query (prefetches are ignored by aggregate()).
    summary = qs.aggregate(count=Count("id"), total=Coalesce(Sum("credit_outstanding"), Decimal("0")))
    rows = []
    for inv in qs[: clamp_limit(limit)]:
        rows.append({
            "bill_number": inv.bill_number,
            "customer": inv.customer.name,
            "date": timezone.localtime(inv.created_at).date().isoformat(),
            "status": inv.status,
            "payment_status": inv.payment_status,
            "total": money(inv.grand_total),
            "paid": money(inv.total_paid),
            "still_owed": money(inv.credit_outstanding),
        })
    return to_text({
        "period": p.label,
        "matching_invoices": summary["count"],
        "total_still_owed_on_matches": money(summary["total"]),
        "showing": len(rows),
        "invoices": rows,
    })
