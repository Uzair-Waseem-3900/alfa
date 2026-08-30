from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone

from backend.search import search_q

from .models import CreditScoreHistory, CustomerCreditScore


def get_customer_credit_score(customer_id):
    return get_object_or_404(
        CustomerCreditScore, customer_id=customer_id, customer__is_deleted=False,
    )


def get_credit_score_history(customer_id):
    """Always customer-scoped + meant to be paginated by the view — never a
    full-table scan regardless of how many customers or how long history grows."""
    return CreditScoreHistory.objects.filter(
        customer_id=customer_id, customer__is_deleted=False,
    ).order_by("-created_at")


def get_customers_by_tier(*, tier: str = None, search: str = None):
    """
    Backs the Credit Customer Report's three tier-filter buttons. Indexed
    tier column, one JOIN to Customer, paginated by the view.
    """
    qs = CustomerCreditScore.objects.select_related("customer").filter(customer__is_deleted=False)
    if tier:
        qs = qs.filter(tier=tier)
    if search:
        qs = qs.filter(search_q(search, "customer__name", "customer__code"))
    return qs.order_by("-score")


def get_customer_score_inputs(customer_id) -> dict:
    """
    Aggregates this ONE customer's own non-draft invoices/returns — bounded
    by that customer's transaction count, not the whole table, so this stays
    fast regardless of total system-wide data volume (same pattern as
    billing._sync_invoice_payment_summary's per-invoice aggregate).

    Excludes only DRAFT, not just filtering to status="confirmed" — a
    partially-returned invoice (status=PARTIAL) still has real payment
    history and can still carry a genuine overdue balance.
    """
    from billing.models import Invoice, Return

    today = timezone.localtime(timezone.now()).date()

    agg = Invoice.objects.filter(
        customer_id=customer_id, is_deleted=False,
    ).exclude(status="draft").aggregate(
        confirmed_count=Count("id"),
        paid_count=Count("id", filter=Q(payment_status="paid")),
        advance_count=Count("id", filter=Q(payment_type="advance")),
        total_volume=Sum("grand_total"),
        overdue_outstanding=Sum(
            "credit_outstanding",
            filter=Q(credit_outstanding__gt=0, payment_due_date__lte=today),
        ),
        non_overdue_outstanding=Sum(
            "credit_outstanding",
            filter=Q(credit_outstanding__gt=0) & (
                Q(payment_due_date__gt=today) | Q(payment_due_date__isnull=True)
            ),
        ),
    )

    returned_value = Return.objects.filter(
        invoice__customer_id=customer_id, invoice__is_deleted=False, status="accepted",
    ).aggregate(total=Sum("total_return_amount"))["total"] or Decimal("0")

    return {
        "confirmed_invoice_count": agg["confirmed_count"] or 0,
        "paid_invoice_count": agg["paid_count"] or 0,
        "advance_invoice_count": agg["advance_count"] or 0,
        "overdue_outstanding": agg["overdue_outstanding"] or Decimal("0"),
        "non_overdue_outstanding": agg["non_overdue_outstanding"] or Decimal("0"),
        "returned_value": returned_value,
        "total_invoiced_volume": agg["total_volume"] or Decimal("0"),
    }


def get_overdue_customer_ids_not_yet_caught_up(*, as_of_date) -> list:
    """
    Bounded to invoices that are ACTUALLY overdue right now — not a scan of
    every customer. Backs the CreditScoreFlow catch-up sweep.
    """
    from billing.models import Invoice

    return list(
        Invoice.objects.filter(
            is_deleted=False,
            credit_outstanding__gt=0, payment_due_date__lte=as_of_date,
        ).exclude(status="draft").values_list("customer_id", flat=True).distinct()
    )
