from agents import RunContextWrapper

from ..schemas.context import AgentContext
from .base import agent_tool, money, to_text


@agent_tool
def business_snapshot(ctx: RunContextWrapper[AgentContext]) -> str:
    """Current overall position: cash in hand, money customers owe us, money we owe suppliers,
    lifetime sales/purchases/expenses/gross profit, and stock alert counts. Fast. All-time figures."""
    from cash_flow.selectors import get_cashflow_stats
    from purchases.selectors import get_inventory_stats

    cf = get_cashflow_stats()
    inv = get_inventory_stats()
    return to_text({
        "cash_in_hand": money(cf["cash_in_hand"]),
        "customers_owe_us": money(cf["customer_outstanding"]),
        "we_owe_suppliers": money(cf["total_outstanding_payable"]),
        "lifetime": {
            "invoices": cf["total_number_of_invoices"],
            "net_sales": money(cf["net_invoice_revenue"]),
            "net_gross_profit": money(cf["net_gross_profit"]),
            "purchases": money(cf["total_purchases_cash"]),
            "expenses": money(cf["total_expenses_amount"]),
        },
        "stock": {
            "products": inv.total_products,
            "low_stock": inv.low_stock_count,
            "out_of_stock": inv.out_of_stock_count,
        },
    })


@agent_tool
def business_worth(ctx: RunContextWrapper[AgentContext]) -> str:
    """Total business worth (net worth): cash + inventory value + assets + receivables - payables - pending recurring dues.
    Slower than business_snapshot (values inventory live) - use only when asked about worth/net worth/equity."""
    from profits.selectors import get_business_worth

    return to_text({k: money(v) for k, v in get_business_worth().items()})
