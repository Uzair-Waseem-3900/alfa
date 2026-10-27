from decimal import Decimal, ROUND_HALF_UP


PRECISION = Decimal("0.0001")


def get_invoice_print_context(invoice) -> dict:
    """
    Single source of truth for "what actually gets shown/printed for this
    invoice" — used by BOTH the PDF (billing.pdf_service) and the Invoice
    Preview page's `print_preview` API field (billing.serializers), so the
    two can never drift out of sync (they used to: draft_preview's
    line_total ignores discount/GST/WHT, which is a DIFFERENT number than
    what the draft PDF actually prints).

    Confirmed invoices read their real stored fields. Drafts don't have
    those yet (only set at confirmation), so this computes the exact same
    math a confirmation would produce via calculate_line_item/
    calculate_invoice_totals — an item whose product has no rate or
    otherwise can't be priced comes back with effective_price/line_total
    as None ("N/A" on the bill), same as the PDF's existing fallback.

    Returns:
        {"items": [{"product_name", "product_code", "quantity",
                     "effective_price", "line_total"}, ...],
         "grand_total": Decimal or None}
    """
    from .models import Invoice

    items_ctx = []

    if invoice.status != Invoice.Status.DRAFT:
        for item in invoice.items.all():
            items_ctx.append({
                "product_name"    : item.product.name,
                "product_code"    : item.product.code,
                "quantity"        : item.quantity,
                "effective_price" : item.effective_price,
                "line_total"      : item.line_total,
            })
        return {
            "items": items_ctx, "grand_total": invoice.grand_total,
            "invoice_discount": invoice.invoice_discount_amount,
        }

    line_calcs = []
    for item in invoice.items.all():
        try:
            selling_price = item.product.rate.selling_price
            calc = calculate_line_item(
                quantity=item.quantity, selling_price=selling_price,
                discount=item.discount, gst=item.gst, wht=item.wht,
            )
            items_ctx.append({
                "product_name"    : item.product.name,
                "product_code"    : item.product.code,
                "quantity"        : item.quantity,
                "effective_price" : calc["effective_price"],
                "line_total"      : calc["line_total"],
            })
            line_calcs.append({**calc, "line_cogs": Decimal("0")})
        except Exception:
            items_ctx.append({
                "product_name"    : item.product.name,
                "product_code"    : item.product.code,
                "quantity"        : item.quantity,
                "effective_price" : None,
                "line_total"      : None,
            })

    if not line_calcs:
        return {"items": items_ctx, "grand_total": None, "invoice_discount": Decimal("0")}

    pre_discount_total = calculate_invoice_totals(line_calcs)["grand_total"]
    invoice_discount = resolve_invoice_discount(
        discount_type=invoice.invoice_discount_type,
        discount_value=invoice.invoice_discount_value,
        pre_discount_total=pre_discount_total,
    )
    return {
        "items": items_ctx,
        "grand_total": pre_discount_total - invoice_discount,
        "invoice_discount": invoice_discount,
    }


def quantize(value: Decimal) -> Decimal:
    return value.quantize(PRECISION, rounding=ROUND_HALF_UP)


def resolve_invoice_discount(*, discount_type, discount_value, pre_discount_total) -> Decimal:
    """
    Single source of truth for turning the user's whole-invoice discount
    input into rupees. `pre_discount_total` is the tax-inclusive sum of line
    totals (after item-level discounts) — a percent is taken of that, a flat
    value is used as-is.
    """
    value = Decimal(str(discount_value or 0))
    if value <= 0:
        return Decimal("0")
    if discount_type == "percent":
        return quantize(Decimal(str(pre_discount_total)) * value / Decimal("100"))
    return quantize(value)


def invoice_discount_factor(invoice) -> Decimal:
    """
    Share of a returned line's value the customer actually paid, given the
    invoice's whole-invoice discount: grand_total / (grand_total + discount).
    1 when there is no discount (so undiscounted invoices are unaffected).
    O(1) — reads only stored invoice fields; grand_total is never rewritten
    by a return.
    """
    discount = invoice.invoice_discount_amount
    if not discount:
        return Decimal("1")
    pre_discount_total = invoice.grand_total + discount
    if pre_discount_total <= 0:
        return Decimal("1")
    return invoice.grand_total / pre_discount_total


def calculate_return_line_total(*, effective_price, quantity, discount_factor=Decimal("1")) -> Decimal:
    """
    Single source of truth for what a returned line is worth: the quantity
    at the price the customer was actually billed (effective_price =
    selling_price - discount, so a surcharge - negative discount - is
    included too), NOT the list selling_price. A full return therefore
    credits exactly what the invoice billed and outstanding reaches zero.

    discount_factor (invoice_discount_factor) scales the value down by the
    invoice's whole-invoice discount, so the credit equals what was paid.

    Tax (GST/WHT) is deliberately not part of a return's value yet.
    """
    return quantize(
        Decimal(str(effective_price)) * Decimal(str(quantity)) * Decimal(str(discount_factor))
    )


def calculate_line_item(
    *,
    quantity: int,
    selling_price: Decimal,
    discount: Decimal,
    gst: Decimal,
    wht: Decimal,
) -> dict:
    """
    Single source of truth for invoice line item calculation.

    Formula:
        effective_price = selling_price - discount
        line_gross      = quantity x effective_price
        line_gst        = line_gross x (gst / 100)
        line_wht        = line_gross x (wht / 100)
        line_total      = line_gross + line_gst - line_wht   (tax-inclusive, shown on bill)

    Notes:
        - discount > 0  => price reduction
        - discount < 0  => surcharge (price increase)
        - discount/gst/wht default to 0 (no effect)
        - COGS is unaffected by discount/gst/wht (purely from FIFO purchase cost)

    Returns dict of all computed Decimal values.
    """
    qty             = Decimal(str(quantity))
    sp              = Decimal(str(selling_price))
    disc            = Decimal(str(discount))
    gst_pct         = Decimal(str(gst))
    wht_pct         = Decimal(str(wht))

    effective_price = sp - disc
    line_gross      = qty * effective_price
    line_gst        = line_gross * (gst_pct / Decimal("100"))
    line_wht        = line_gross * (wht_pct / Decimal("100"))
    line_total      = line_gross + line_gst - line_wht

    return {
        "effective_price" : quantize(effective_price),
        "line_gross"      : quantize(line_gross),
        "line_gst_amount" : quantize(line_gst),
        "line_wht_amount" : quantize(line_wht),
        "line_total"      : quantize(line_total),
    }


def calculate_invoice_totals(line_items: list[dict], invoice_discount=Decimal("0")) -> dict:
    """
    Aggregates line-level results into invoice-level totals.
    line_items: list of dicts returned by calculate_line_item() + line_cogs.
    invoice_discount: resolved whole-invoice discount in rupees.

    Returns:
        subtotal    = sum of line_gross  (before tax)
        gst_total   = sum of line_gst
        wht_total   = sum of line_wht
        grand_total = sum of line_total - invoice_discount
                      (tax-inclusive, what customer pays)
        total_cogs  = sum of line_cogs
        gross_profit = grand_total - total_cogs
    """
    subtotal     = Decimal("0")
    gst_total    = Decimal("0")
    wht_total    = Decimal("0")
    grand_total  = Decimal("0")
    total_cogs   = Decimal("0")

    for item in line_items:
        subtotal    += item["line_gross"]
        gst_total   += item["line_gst_amount"]
        wht_total   += item["line_wht_amount"]
        grand_total += item["line_total"]
        total_cogs  += item["line_cogs"]

    grand_total -= Decimal(str(invoice_discount or 0))
    gross_profit = grand_total - total_cogs

    return {
        "subtotal"    : quantize(subtotal),
        "gst_total"   : quantize(gst_total),
        "wht_total"   : quantize(wht_total),
        "grand_total" : quantize(grand_total),
        "total_cogs"  : quantize(total_cogs),
        "gross_profit": quantize(gross_profit),
    }