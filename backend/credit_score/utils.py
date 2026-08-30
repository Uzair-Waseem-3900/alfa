"""
Pure credit-score formula — no DB access, no imports from .models/.services.
Mirrors billing/utils.py's shape (calculate_line_item/calculate_invoice_totals):
services.py gathers the raw numbers, this module turns them into a score.
"""

from decimal import Decimal

from .models import ScoreTier

BASELINE_SCORE = 50
CONFIDENCE_FULL_AT_INVOICE_COUNT = 5

# Max points each factor can move the score, scaled by confidence.
WEIGHT_PAYMENT_COMPLETION = Decimal("30")
WEIGHT_OVERDUE_RATIO      = Decimal("30")
WEIGHT_OUTSTANDING_RATIO  = Decimal("15")
WEIGHT_RETURN_RATIO       = Decimal("10")
WEIGHT_ADVANCE_USAGE      = Decimal("10")


def _tier_for(score: int) -> str:
    if score >= 70:
        return ScoreTier.GOOD
    if score >= 31:
        return ScoreTier.AVERAGE
    return ScoreTier.POOR


def _ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator <= 0:
        return Decimal("0")
    return numerator / denominator


def compute_score(
    *,
    confirmed_invoice_count: int,
    paid_invoice_count: int,
    advance_invoice_count: int,
    overdue_outstanding: Decimal,
    non_overdue_outstanding: Decimal,
    returned_value: Decimal,
    total_invoiced_volume: Decimal,
) -> dict:
    """
    Returns {"score": int, "tier": str, "factor_breakdown": dict}.

    Baseline 50, then weighted factor deltas scaled by a confidence
    multiplier (min(1.0, confirmed_invoice_count / 5)) so a customer's
    first few invoices can't swing them to an extreme tier on one data
    point — the multiplier ramps to full strength by their 5th confirmed
    invoice.
    """
    if confirmed_invoice_count <= 0:
        # No confirmed history at all — pure baseline (matches
        # initialize_credit_score's own hardcoded 50/AVERAGE, kept here too
        # so this function is a safe fallback if ever called with zero count).
        return {
            "score": BASELINE_SCORE,
            "tier": ScoreTier.AVERAGE,
            "factor_breakdown": {"note": "No confirmed invoices yet — baseline."},
        }

    confidence = min(Decimal("1.0"), Decimal(confirmed_invoice_count) / Decimal(CONFIDENCE_FULL_AT_INVOICE_COUNT))

    completion_rate = _ratio(Decimal(paid_invoice_count), Decimal(confirmed_invoice_count))
    completion_points = completion_rate * WEIGHT_PAYMENT_COMPLETION

    overdue_ratio = _ratio(overdue_outstanding, total_invoiced_volume)
    overdue_points = -(overdue_ratio * WEIGHT_OVERDUE_RATIO)

    outstanding_ratio = _ratio(non_overdue_outstanding, total_invoiced_volume)
    outstanding_points = -(outstanding_ratio * WEIGHT_OUTSTANDING_RATIO)

    return_ratio = _ratio(returned_value, total_invoiced_volume)
    return_points = -(return_ratio * WEIGHT_RETURN_RATIO)

    advance_usage_ratio = _ratio(Decimal(advance_invoice_count), Decimal(confirmed_invoice_count))
    advance_points = advance_usage_ratio * WEIGHT_ADVANCE_USAGE

    raw_delta = completion_points + overdue_points + outstanding_points + return_points + advance_points
    scaled_delta = raw_delta * confidence

    score = int(max(0, min(100, round(BASELINE_SCORE + scaled_delta))))
    tier = _tier_for(score)

    factor_breakdown = {
        "baseline": BASELINE_SCORE,
        "confidence": float(confidence),
        "confirmed_invoice_count": confirmed_invoice_count,
        "factors": {
            "payment_completion_rate": {"ratio": float(completion_rate), "points": float(completion_points)},
            "overdue_ratio":           {"ratio": float(overdue_ratio), "points": float(overdue_points)},
            "outstanding_ratio":       {"ratio": float(outstanding_ratio), "points": float(outstanding_points)},
            "return_ratio":            {"ratio": float(return_ratio), "points": float(return_points)},
            "advance_usage_ratio":     {"ratio": float(advance_usage_ratio), "points": float(advance_points)},
        },
        "raw_delta": float(raw_delta),
        "scaled_delta": float(scaled_delta),
        "score": score,
    }

    return {"score": score, "tier": tier, "factor_breakdown": factor_breakdown}
