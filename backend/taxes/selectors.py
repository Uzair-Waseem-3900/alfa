from django.db.models import QuerySet
from django.shortcuts import get_object_or_404

from backend.search import search_q

from .models import TaxFlow, TaxPayment, WHTPayment


def _clean(value):
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


# ---------------------------------------------------------------------------
# TaxFlow stats
# ---------------------------------------------------------------------------

def get_tax_stats() -> dict:
    """
    Returns the store's current tax position, straight off the TaxFlow
    singleton — zero aggregation queries, same O(1) pattern as
    cash_flow.get_cashflow_stats().
    """
    tf = TaxFlow.get_instance()
    return {
        "total_input_tax_paid"              : tf.total_input_tax_paid,
        "total_output_tax_collected"        : tf.total_output_tax_collected,
        "net_sales_tax_payable"             : tf.net_sales_tax_payable,
        "total_sales_tax_paid"              : tf.total_sales_tax_paid,
        "sales_tax_outstanding"             : tf.sales_tax_outstanding,
        "total_wht_withheld_from_suppliers" : tf.total_wht_withheld_from_suppliers,
        "total_wht_withheld_by_customers"   : tf.total_wht_withheld_by_customers,
        "total_wht_paid"                    : tf.total_wht_paid,
        "wht_outstanding"                   : tf.wht_outstanding,
    }


# ---------------------------------------------------------------------------
# TaxPayment
# ---------------------------------------------------------------------------

def get_all_tax_payments(
    *,
    search     : str = None,
    date_from  : str = None,
    date_to    : str = None,
    min_amount : str = None,
    max_amount : str = None,
) -> QuerySet:
    """Returns all non-deleted tax payments with full filter support."""
    qs = TaxPayment.objects.filter(is_deleted=False).select_related(
        "created_by", "updated_by",
    )

    if _clean(search):
        qs = qs.filter(search_q(_clean(search), "note"))
    if _clean(date_from):
        qs = qs.filter(payment_date__gte=_clean(date_from))
    if _clean(date_to):
        qs = qs.filter(payment_date__lte=_clean(date_to))
    if _clean(min_amount):
        qs = qs.filter(amount__gte=_clean(min_amount))
    if _clean(max_amount):
        qs = qs.filter(amount__lte=_clean(max_amount))

    return qs.order_by("-payment_date", "-created_at")


def get_tax_payment_by_id(pk: int) -> TaxPayment:
    return get_object_or_404(TaxPayment, pk=pk, is_deleted=False)


# ---------------------------------------------------------------------------
# WHTPayment
# ---------------------------------------------------------------------------

def get_all_wht_payments(
    *,
    search     : str = None,
    date_from  : str = None,
    date_to    : str = None,
    min_amount : str = None,
    max_amount : str = None,
) -> QuerySet:
    """Returns all non-deleted WHT payments with full filter support."""
    qs = WHTPayment.objects.filter(is_deleted=False).select_related(
        "created_by", "updated_by",
    )

    if _clean(search):
        qs = qs.filter(search_q(_clean(search), "note"))
    if _clean(date_from):
        qs = qs.filter(payment_date__gte=_clean(date_from))
    if _clean(date_to):
        qs = qs.filter(payment_date__lte=_clean(date_to))
    if _clean(min_amount):
        qs = qs.filter(amount__gte=_clean(min_amount))
    if _clean(max_amount):
        qs = qs.filter(amount__lte=_clean(max_amount))

    return qs.order_by("-payment_date", "-created_at")


def get_wht_payment_by_id(pk: int) -> WHTPayment:
    return get_object_or_404(WHTPayment, pk=pk, is_deleted=False)
