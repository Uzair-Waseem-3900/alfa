from typing import Literal

from agents import RunContextWrapper

from ..schemas.context import AgentContext
from .base import agent_tool, clamp_limit, money, to_text


def _row(inv) -> dict:
    return {
        "product": inv.product.name,
        "code": inv.product.code,
        "category": inv.product.category.name if inv.product.category_id else None,
        "quantity": inv.quantity,
        "avg_unit_cost": money(inv.avg_unit_cost),
    }


@agent_tool
def product_stock(ctx: RunContextWrapper[AgentContext], search: str, limit: int = 10) -> str:
    """Current stock quantity and average unit cost of products matching a name or code.

    Args:
        search: Part of the product name or code.
        limit: Max products (capped).
    """
    from purchases.selectors import get_all_inventory

    rows = [_row(i) for i in get_all_inventory(search=search)[: clamp_limit(limit)]]
    return to_text({"showing": len(rows), "products": rows})


@agent_tool
def stock_alerts(ctx: RunContextWrapper[AgentContext], kind: Literal["low", "out"], limit: int = 15) -> str:
    """Products running low (a few units left) or out of stock, with the total counts.

    Args:
        kind: "low" for low stock, "out" for out of stock.
        limit: Max products to list (capped).
    """
    from purchases.selectors import get_inventory_stats, get_low_stock_inventory, get_out_of_stock_inventory

    stats = get_inventory_stats()
    qs = get_low_stock_inventory() if kind == "low" else get_out_of_stock_inventory()
    rows = [_row(i) for i in qs[: clamp_limit(limit, default=15)]]
    return to_text({
        "total_low_stock": stats.low_stock_count,
        "total_out_of_stock": stats.out_of_stock_count,
        "showing": len(rows),
        "products": rows,
    })
