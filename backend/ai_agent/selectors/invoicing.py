"""
READS the invoice tools need (customer / product lookup, stock for a product,
audit rows). Everything goes through the other apps' existing selectors —
no query logic is re-implemented here.
"""
from django.db.models import Sum

from billing.selectors import (
    get_all_customers, get_available_purchase_batches, get_customer_outstanding,
    get_invoice_by_bill_number, get_reserved_quantity_for_product,
)
from purchases.selectors import get_all_products

from ..models import AgentAction

LOOKUP_LIMIT = 8   # candidates shown when a name matches several records


def _resolve(candidates: list, *, name_of, code_of, search: str | None, code: str | None):
    """-> (unique_or_None, matches_list). A code is exact (codes are unique); a name that
    matches exactly ONE record (ignoring case) wins even if longer names also contain it."""
    if code:
        wanted = code.strip().lower()
        exact = [c for c in candidates if code_of(c).lower() == wanted]
        if len(exact) == 1:
            return exact[0], exact
    if search:
        wanted = search.strip().lower()
        exact = [c for c in candidates if name_of(c).lower() == wanted]
        if len(exact) == 1:
            return exact[0], exact
    return (candidates[0] if len(candidates) == 1 else None), candidates


def find_customers(*, search: str | None, code: str | None):
    qs = get_all_customers(code=code) if code else get_all_customers(name=search)
    candidates = list(qs[: LOOKUP_LIMIT + 1])
    unique, _ = _resolve(candidates, name_of=lambda c: c.name, code_of=lambda c: c.code, search=search, code=code)
    return unique, candidates


def find_products(*, search: str | None, code: str | None):
    # select_related("rate"): the price comes with the product row instead of one query per product.
    candidates = list(get_all_products(search=code or search).select_related("rate")[: LOOKUP_LIMIT + 1])
    unique, _ = _resolve(candidates, name_of=lambda p: p.name, code_of=lambda p: p.code, search=search, code=code)
    return unique, candidates


def product_availability(product) -> dict:
    """Rate-list price (None if unpriced) and stock that a NEW draft could still claim."""
    try:
        price = product.rate.selling_price
    except Exception:   # no rate row
        price = None
    # Stock is counted in whole units (PositiveIntegerField), but billing's reservation helper
    # returns a Decimal when nothing is reserved: normalise so the model sees plain numbers.
    physical = int(get_available_purchase_batches(product.id).aggregate(total=Sum("remaining_quantity"))["total"] or 0)
    reserved = int(get_reserved_quantity_for_product(product_id=product.id))
    return {"price": price, "physical": physical, "reserved": reserved, "available": physical - reserved}


def customer_standing(customer_id: int):
    return get_customer_outstanding(customer_id)


def get_invoice_by_bill(bill_number: str):
    return get_invoice_by_bill_number(bill_number.strip())


def get_action(*, run_id, tool: str, args_hash: str):
    return AgentAction.objects.filter(run_id=run_id, tool=tool, args_hash=args_hash).first()


def load_products(ids) -> dict:
    """{id: Product} with the rate-list row, in ONE query (billing's get_product_by_id is one query per product)."""
    return get_all_products().select_related("rate").in_bulk(list(ids))


def count_run_writes(run_id) -> int:
    # prefix of the unique index (run, tool, args_hash)
    return AgentAction.objects.filter(run_id=run_id).count()


def bills_written_in_run(run_id) -> list[tuple[str, str]]:
    return list(AgentAction.objects.filter(run_id=run_id).order_by("id").values_list("bill_number", "result"))


def count_writes_since(user, since) -> int:
    # served by idx_agentaction_user_time (user, -created_at)
    return AgentAction.objects.filter(user=user, created_at__gte=since).count()
