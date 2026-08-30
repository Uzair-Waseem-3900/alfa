from django.db import transaction
from django.utils import timezone

from .models import CreditScoreFlow, CreditScoreHistory, CustomerCreditScore, ScoreTier
from .selectors import get_customer_score_inputs, get_overdue_customer_ids_not_yet_caught_up
from .utils import BASELINE_SCORE, compute_score


@transaction.atomic
def initialize_credit_score(customer, user) -> CustomerCreditScore:
    """
    Called once, at customer creation (billing.services.create_customer).
    Every customer must have a score row from day one — baseline
    50/AVERAGE — so list/report pages never need a null case. Idempotent:
    safe to call again (e.g. from the backfill command) without creating a
    duplicate row.

    `user` is accepted (not stored) for the same reason every other
    service function in this codebase takes it — CreditScoreHistory
    deliberately has no created_by field, same convention as CashMovement:
    the triggering source row (Customer/Invoice/Payment) already carries
    that attribution.
    """
    score_obj, created = CustomerCreditScore.objects.get_or_create(
        customer=customer, defaults={"score": BASELINE_SCORE, "tier": ScoreTier.AVERAGE},
    )
    if created:
        CreditScoreHistory.objects.create(
            customer=customer,
            score_before=None, score_after=BASELINE_SCORE,
            tier_before=None, tier_after=ScoreTier.AVERAGE,
            trigger="customer_created", reference=customer.code,
            factor_breakdown={"note": "Baseline on customer creation."},
        )
    return score_obj


@transaction.atomic
def recalculate_credit_score(*, customer_id, user, trigger: str, reference: str = "") -> CustomerCreditScore:
    """
    Full recompute from current source-of-truth data every time (not an
    increment) — this makes concurrent triggers for the SAME customer
    naturally safe: select_for_update() serializes them, and whichever
    runs last simply writes the numerically-correct end state regardless
    of interleaving order.

    Aggregates only this ONE customer's own invoices/returns (see
    selectors.get_customer_score_inputs) — bounded by that customer's own
    transaction count, not the whole table, so this stays fast at any
    system-wide data volume.
    """
    score_obj = CustomerCreditScore.objects.select_for_update().filter(customer_id=customer_id).first()
    if score_obj is None:
        # Defensive fallback — every customer should already have a row from
        # initialize_credit_score, but a billing event must never crash over
        # a missing row (e.g. data created before this feature existed and
        # not yet backfilled).
        from billing.models import Customer
        customer = Customer.objects.get(pk=customer_id)
        initialize_credit_score(customer, user)
        score_obj = CustomerCreditScore.objects.select_for_update().get(customer_id=customer_id)

    inputs = get_customer_score_inputs(customer_id)
    result = compute_score(**inputs)

    score_before, tier_before = score_obj.score, score_obj.tier
    if score_before == result["score"] and tier_before == result["tier"]:
        # Recomputed, but nothing actually changed — CreditScoreHistory
        # exists to answer "why did this score change" (see its docstring),
        # so a no-op recompute (e.g. overdue_catchup re-checking a customer
        # whose overdue bucket hasn't moved) must not write a row. Found
        # 2026-08-31: daily catch-up was logging a fresh "44 -> 44" row for
        # every unaffected customer, forever.
        return score_obj

    score_obj.score = result["score"]
    score_obj.tier = result["tier"]
    score_obj.factor_breakdown = result["factor_breakdown"]
    score_obj.save(update_fields=["score", "tier", "factor_breakdown", "last_calculated_at"])

    CreditScoreHistory.objects.create(
        customer_id=customer_id,
        score_before=score_before, score_after=result["score"],
        tier_before=tier_before, tier_after=result["tier"],
        trigger=trigger, reference=reference or "",
        factor_breakdown=result["factor_breakdown"],
    )
    return score_obj


def run_overdue_catchup(*, user) -> int:
    """
    Marker-gated (see CreditScoreFlow.overdue_caught_up_through): O(1) on
    every call except the rare day-rollover, and even then bounded to
    invoices that are ACTUALLY overdue right now — not a scan of every
    customer. Call from GET /api/system/catch-up/.

    Only the STORED score needs this — the Due Invoices tab itself is a
    live filter and needs no catch-up at all.

    Returns the number of customers recalculated.
    """
    today = timezone.localtime(timezone.now()).date()
    flow = CreditScoreFlow.get_instance()
    if flow.overdue_caught_up_through == today:
        return 0

    customer_ids = get_overdue_customer_ids_not_yet_caught_up(as_of_date=today)
    for customer_id in customer_ids:
        recalculate_credit_score(customer_id=customer_id, user=user, trigger="overdue_catchup")

    flow.overdue_caught_up_through = today
    flow.save(update_fields=["overdue_caught_up_through", "last_updated_at"])
    return len(customer_ids)
