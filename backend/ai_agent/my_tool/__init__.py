"""
Tool registry. `ALL_TOOLS` is what the agent gets; `STEP_LABELS` are the
friendly texts shown in the chat while a tool runs.

Every schema here is sent to the model on every call, so keep the list short
and the docstrings tight.
"""
from .finance_tool import expenses_summary, profit_report, tax_position
from .guide_tool import get_guide
from .inventory_tool import product_stock, stock_alerts
from .parties_tool import customer_info, customers_who_owe, supplier_info, suppliers_we_owe
from .sales_tool import find_invoices, sales_summary
from .snapshot_tool import business_snapshot, business_worth

ALL_TOOLS = [
    get_guide,
    business_snapshot, business_worth,
    sales_summary, find_invoices,
    customer_info, customers_who_owe,
    supplier_info, suppliers_we_owe,
    product_stock, stock_alerts,
    expenses_summary, profit_report, tax_position,
]

STEP_LABELS = {
    "get_guide": "Reading the rules…",
    "business_snapshot": "Checking the overall position…",
    "business_worth": "Calculating business worth…",
    "sales_summary": "Looking at sales…",
    "find_invoices": "Searching invoices…",
    "customer_info": "Looking up the customer…",
    "customers_who_owe": "Checking who owes money…",
    "supplier_info": "Looking up the supplier…",
    "suppliers_we_owe": "Checking what we owe suppliers…",
    "product_stock": "Checking stock…",
    "stock_alerts": "Checking stock alerts…",
    "expenses_summary": "Adding up expenses…",
    "profit_report": "Checking profit…",
    "tax_position": "Checking tax position…",
}


def step_label(tool_name: str) -> str:
    return STEP_LABELS.get(tool_name, f"Using {tool_name.replace('_', ' ')}…")
