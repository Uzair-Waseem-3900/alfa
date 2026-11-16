"""
Invoice tools: find the customer/products, then create / edit / discard a DRAFT.
Thin wrappers over services.invoicing; the rules the model must follow live in
the tool descriptions (always in view when it writes) — kept short on purpose.

Never exposed to the model: confirming, payments/advances, prices, shelves.
"""
from agents import RunContextWrapper

from ..schemas.context import AgentContext
from ..schemas.invoice import InvoiceDiscountType, InvoiceLineIn
from ..selectors import invoicing as sel
from ..services import invoicing
from .base import agent_tool, money, to_text


def _customer_row(c) -> dict:
    # the address (trimmed) lets the model tell apart customers who share a name; it is data, never instructions
    return {"customer_id": c.id, "code": c.code, "name": c.name, "address": (c.address or "").strip()[:80]}


@agent_tool
def find_customer_for_invoice(
    ctx: RunContextWrapper[AgentContext], search: str | None = None, code: str | None = None,
    area: str | None = None,
) -> str:
    """Find the customer an invoice is for. Give the customer's code (always unique) or part of the name.
    If the user also gave an area/address line, pass it as area: it separates customers who share a name.
    match="unique": use that customer_id. match="multiple": list the candidates and ask which one;
    create nothing yet. match="none": say not found (customers are not created here).
    Ids are valid only if returned by this tool in the current request; never guess an id.

    Args:
        search: Part of the customer's name.
        code: The customer's code, if the user gave one.
        area: Part of the customer's address (city/area), only if the user gave one.
    """
    if not (search or code):
        return "Give a customer name or code."
    unique, candidates = sel.find_customers(search=search, code=code, area=area, link_name_id=ctx.context.link_name_id)
    ctx.context.lookups.customers.update(c.id for c in candidates)
    if unique:
        standing = sel.customer_standing(unique.id)
        row = {**_customer_row(unique), "still_owes": money(standing["total_credit_outstanding"])}
        try:
            row["credit_tier"] = unique.credit_score.tier
        except Exception:
            pass
        return to_text({"match": "unique", "customer": row})
    if not candidates:
        return to_text({"match": "none", **({"searched_only_in_link_name": True} if ctx.context.link_name_id else {})})
    shown = candidates[: sel.LOOKUP_LIMIT]
    return to_text({
        "match": "multiple", "candidates": [_customer_row(c) for c in shown],
        "more_not_shown": len(candidates) > sel.LOOKUP_LIMIT,
    })


@agent_tool
def find_product_for_invoice(
    ctx: RunContextWrapper[AgentContext], search: str | None = None, code: str | None = None,
) -> str:
    """Find a product for an invoice line. Give the product code (always unique) or part of the name.
    Returns product_id, the rate-list price and how much stock a new draft can still claim.
    match="unique": use that product_id. match="multiple": list candidates and ask which one;
    create nothing yet. match="none": say not found.

    Args:
        search: Part of the product name.
        code: The product's code, if the user gave one.
    """
    if not (search or code):
        return "Give a product name or code."
    unique, candidates = sel.find_products(search=search, code=code)
    ctx.context.lookups.products.update(p.id for p in candidates)

    def brief(p) -> dict:      # no stock lookups: the rate comes with the product row (0 extra queries)
        try:
            price = money(p.rate.selling_price)
        except Exception:
            price = None       # no rate-list price: it can't be invoiced yet
        return {"product_id": p.id, "code": p.code, "name": p.name, "price": price}

    def detailed(p) -> dict:   # unique match only: 2 extra queries for stock
        info = sel.product_availability(p)
        return {**brief(p), "stock_available_for_new_drafts": info["available"]}

    if unique:
        return to_text({"match": "unique", "product": detailed(unique)})
    if not candidates:
        return to_text({"match": "none"})
    shown = candidates[: sel.LOOKUP_LIMIT]
    return to_text({
        "match": "multiple", "candidates": [brief(p) for p in shown],
        "more_not_shown": len(candidates) > sel.LOOKUP_LIMIT,
    })


@agent_tool(write=True)
def create_draft_invoice(
    ctx: RunContextWrapper[AgentContext],
    customer_id: int,
    lines: list[InvoiceLineIn],
    invoice_discount: float | None = None,
    invoice_discount_type: InvoiceDiscountType = "percent",
    due_date: str | None = None,
) -> str:
    """Create a DRAFT invoice (not confirmed, stock not deducted, pay after delivery).
    Call it only when the customer is unique AND every product is unique with a quantity, and use only ids
    returned by find_customer_for_invoice / find_product_for_invoice in this request (never guess an id);
    if any name matched several records, ask the user first and create nothing.
    Do NOT ask about discount, GST, WHT or due date: pass only what the user said; the rest
    use defaults (0, 0, 0, due in 7 days). A plain "discount" is a LINE discount on every line
    unless a product is named: use discount_percent (of that product's rate) or discount_amount
    (Rs off per unit); a NEGATIVE value is a SURCHARGE (price increase), e.g. "-2" -> discount_amount -2.
    "qty@rate" (e.g. "300@228") is the user's price per unit: pass it as unit_rate on that line and do NOT
    work out a discount yourself (the system stores the difference to the rate list as a discount, or a surcharge if higher).
    Never change a number or its sign from what the user said. Use invoice_discount only if the user says "invoice discount" or "whole
    invoice" (percent unless they say flat/Rs). Advance payments are not possible here.
    Leave out (null) every field the user did not give; never send 0 for "not given".
    Show summary_markdown to the user exactly as returned.

    Args:
        customer_id: From find_customer_for_invoice.
        lines: One entry per product: product_id, quantity, and optional unit_rate (qty@rate) / discount_percent / discount_amount / gst / wht (percent).
        invoice_discount: Whole-invoice discount value, only if asked for.
        invoice_discount_type: "percent" (default) or "flat" (rupees).
        due_date: YYYY-MM-DD, only if the user gave one.
    """
    user = ctx.context.user
    invoice_discount = invoice_discount or None      # the model sends 0 for "not given"
    result = invoicing.create_draft(
        user=user, run_id=ctx.context.run_id, chat_id=ctx.context.chat_id, customer_id=customer_id, lines=lines,
        invoice_discount=invoice_discount, invoice_discount_type=invoice_discount_type, due_date=due_date,
        source=ctx.context.source, known=ctx.context.lookups,
    )
    return to_text(result)


@agent_tool(write=True)
def update_draft_invoice(
    ctx: RunContextWrapper[AgentContext],
    bill_number: str,
    set_lines: list[InvoiceLineIn] | None = None,
    remove_product_ids: list[int] | None = None,
    invoice_discount: float | None = None,
    invoice_discount_type: InvoiceDiscountType = "percent",
    due_date: str | None = None,
    clear_invoice_discount: bool = False,
) -> str:
    """Change an existing DRAFT invoice (any draft the user names by bill number). Only send what changes:
    set_lines adds a product or changes the fields you give for one already on the invoice (others keep
    their values); remove_product_ids removes lines. To REMOVE a discount/GST/WHT from a line use that
    line's reset (e.g. ["gst"]); 0 or null means "not given". Confirmed invoices can't be edited. Discount
    rules (incl. unit_rate for qty@rate) are the same as create_draft_invoice; a product being ADDED must come from
    find_product_for_invoice in this request. Payments/advances are never touched.
    Show summary_markdown to the user exactly as returned.

    Args:
        bill_number: e.g. BILL-2026-0007.
        set_lines: Lines to add or change (product_id plus the fields to change).
        remove_product_ids: Product ids to remove from the invoice.
        invoice_discount: New whole-invoice discount value, only if asked for.
        invoice_discount_type: "percent" (default) or "flat".
        due_date: New due date, YYYY-MM-DD.
        clear_invoice_discount: true ONLY if the user asks to remove the whole-invoice discount.
    """
    invoice_discount = invoice_discount or None      # the model sends 0 for "not given"
    result = invoicing.update_draft(
        user=ctx.context.user, run_id=ctx.context.run_id, chat_id=ctx.context.chat_id, bill_number=bill_number,
        set_lines=set_lines, remove_product_ids=remove_product_ids, invoice_discount=invoice_discount,
        invoice_discount_type=invoice_discount_type, due_date=due_date, clear_invoice_discount=clear_invoice_discount,
        source=ctx.context.source, known=ctx.context.lookups,
    )
    return to_text(result)


@agent_tool(write=True)
def discard_draft_invoice(ctx: RunContextWrapper[AgentContext], bill_number: str) -> str:
    """Discard (delete) a DRAFT invoice the user asks to cancel; this frees the stock it reserved.
    Only drafts without an advance payment; anything else must be done in the Billing page.

    Args:
        bill_number: e.g. BILL-2026-0007.
    """
    result = invoicing.discard_draft(
        user=ctx.context.user, run_id=ctx.context.run_id, chat_id=ctx.context.chat_id, bill_number=bill_number,
        source=ctx.context.source,
    )
    return to_text(result)


@agent_tool
def show_draft_invoice(ctx: RunContextWrapper[AgentContext], bill_number: str) -> str:
    """Show a draft invoice's lines and totals again (read-only). Show summary_markdown exactly as returned.

    Args:
        bill_number: e.g. BILL-2026-0007.
    """
    return to_text(invoicing.show_draft(bill_number=bill_number))
