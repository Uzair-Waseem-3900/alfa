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
        return {"items": items_ctx, "grand_total": invoice.grand_total}

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

    grand_total = calculate_invoice_totals(line_calcs)["grand_total"] if line_calcs else None
    return {"items": items_ctx, "grand_total": grand_total}


def quantize(value: Decimal) -> Decimal:
    return value.quantize(PRECISION, rounding=ROUND_HALF_UP)


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


def calculate_invoice_totals(line_items: list[dict]) -> dict:
    """
    Aggregates line-level results into invoice-level totals.
    line_items: list of dicts returned by calculate_line_item() + line_cogs.

    Returns:
        subtotal    = sum of line_gross  (before tax)
        gst_total   = sum of line_gst
        wht_total   = sum of line_wht
        grand_total = sum of line_total  (tax-inclusive, what customer pays)
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

    gross_profit = grand_total - total_cogs

    return {
        "subtotal"    : quantize(subtotal),
        "gst_total"   : quantize(gst_total),
        "wht_total"   : quantize(wht_total),
        "grand_total" : quantize(grand_total),
        "total_cogs"  : quantize(total_cogs),
        "gross_profit": quantize(gross_profit),
    }