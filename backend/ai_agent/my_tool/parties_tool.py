"""Customers (receivables) and suppliers (payables)."""
from agents import RunContextWrapper
from django.core.exceptions import ObjectDoesNotExist

from ..schemas.context import AgentContext
from .base import agent_tool, clamp_limit, money, to_text

DETAILED_MATCHES = 3    # figures cost one query per party, so only the first few get them
LISTED_MATCHES = 6      # further matches are listed by name/code only (no extra queries)


@agent_tool
def customer_info(ctx: RunContextWrapper[AgentContext], search: str) -> str:
    """Look up customers by name, code or mobile. The first 3 matches include what each has been billed,
    paid and still owes, plus credit tier; further matches (up to 6 in total) are names/codes only.
    If several match, list them all and ask which one the user means.

    Args:
        search: Part of the customer's name, code or mobile number.
    """
    from billing.selectors import get_all_customers, get_customer_outstanding

    matches = list(get_all_customers(search=search)[: LISTED_MATCHES + 1])
    rows = []
    for c in matches[:DETAILED_MATCHES]:
        o = get_customer_outstanding(c.id)
        try:
            tier, score = c.credit_score.tier, c.credit_score.score
        except ObjectDoesNotExist:
            tier = score = None
        rows.append({
            "name": c.name, "code": c.code, "mobile": c.mobile,
            "total_billed": money(o["total_billed"]),
            "total_paid": money(o["total_paid"]),
            "still_owes": money(o["total_credit_outstanding"]),
            "credit_tier": tier, "credit_score": score,
        })
    return to_text({
        "matches_shown": min(len(matches), LISTED_MATCHES),
        "more_matches_not_shown": len(matches) > LISTED_MATCHES,
        "customers": rows,
        "other_matches_names_only": [{"name": c.name, "code": c.code} for c in matches[DETAILED_MATCHES:LISTED_MATCHES]],
    })


@agent_tool
def customers_who_owe(ctx: RunContextWrapper[AgentContext], limit: int = 10, min_owed: str | None = None) -> str:
    """Customers with an unpaid balance, largest first (who owes us the most, receivables list).

    Args:
        limit: Max customers (capped).
        min_owed: Only customers owing at least this amount (PKR).
    """
    from billing.selectors import get_customers_with_outstanding

    qs = get_customers_with_outstanding(min_outstanding=min_owed)
    rows = [
        {"name": c.name, "code": c.code, "still_owes": money(c.outstanding)}
        for c in qs[: clamp_limit(limit)]
    ]
    return to_text({"showing": len(rows), "customers": rows})


@agent_tool
def supplier_info(ctx: RunContextWrapper[AgentContext], search: str) -> str:
    """Look up suppliers by name or code. The first 3 matches include what we bought, paid and still owe;
    further matches (up to 6 in total) are names/codes only.
    If several match, list them all and ask which one the user means.

    Args:
        search: Part of the supplier's name or code.
    """
    from purchases.selectors import get_all_suppliers, get_supplier_payable_summary

    matches = list(get_all_suppliers(search=search)[: LISTED_MATCHES + 1])
    rows = []
    for s in matches[:DETAILED_MATCHES]:
        t = get_supplier_payable_summary(s.id)
        rows.append({
            "name": s.name, "code": s.code,
            "total_payable": money(t["total_net_payable"]),
            "total_paid": money(t["total_paid"]),
            "we_still_owe": money(t["total_payable_outstanding"]),
        })
    return to_text({
        "matches_shown": min(len(matches), LISTED_MATCHES),
        "more_matches_not_shown": len(matches) > LISTED_MATCHES,
        "suppliers": rows,
        "other_matches_names_only": [{"name": s.name, "code": s.code} for s in matches[DETAILED_MATCHES:LISTED_MATCHES]],
    })


@agent_tool
def suppliers_we_owe(ctx: RunContextWrapper[AgentContext], limit: int = 10) -> str:
    """Suppliers we still owe money to, largest first (payables list).

    Args:
        limit: Max suppliers (capped).
    """
    from purchases.selectors import get_suppliers_with_outstanding

    rows = [
        {"name": s.name, "code": s.code, "we_still_owe": money(s.outstanding)}
        for s in get_suppliers_with_outstanding()[: clamp_limit(limit)]
    ]
    return to_text({"showing": len(rows), "suppliers": rows})
