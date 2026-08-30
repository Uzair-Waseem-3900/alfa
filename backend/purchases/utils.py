from decimal import ROUND_HALF_UP, Decimal


def calculate_total_price(
    quantity: int,
    unit_price: Decimal,
    gst: Decimal,
    wht: Decimal,
) -> dict:
    """
    Single source of truth for the ERP purchase price calculation.

    Formula (Pakistan FBR standard):
        gross_amount = quantity × unit_price
        gst_amount   = gross_amount × (gst  / 100)   — added to payable
        wht_amount   = gross_amount × (wht  / 100)   — deducted from payable (WHT on gross)
        total_price  = gross_amount + gst_amount - wht_amount

    Example:
        qty=10, unit_price=100.5, gst=18.5%, wht=1.5%
        gross  = 1005.0000
        gst    =  185.9250
        wht    =   15.0750
        total  = 1175.8500

    Returns a dict of all four computed Decimal values so callers can store
    each breakdown field individually without re-computing.
    """
    qty = Decimal(str(quantity))
    up = Decimal(str(unit_price))
    gst_pct = Decimal(str(gst))
    wht_pct = Decimal(str(wht))

    gross_amount = qty * up
    gst_amount = gross_amount * (gst_pct / Decimal("100"))
    wht_amount = gross_amount * (wht_pct / Decimal("100"))
    total_price = gross_amount + gst_amount - wht_amount

    precision = Decimal("0.0001")
    return {
        "gross_amount": gross_amount.quantize(precision, rounding=ROUND_HALF_UP),
        "gst_amount": gst_amount.quantize(precision, rounding=ROUND_HALF_UP),
        "wht_amount": wht_amount.quantize(precision, rounding=ROUND_HALF_UP),
        "total_price": total_price.quantize(precision, rounding=ROUND_HALF_UP),
    }