from django.db.models import QuerySet
from django.shortcuts import get_object_or_404

from backend.search import search_q

from .models import (
    CashAdjustment, CashManagementFlow, Investor, InvestorTransaction,
    InvestorValuationEntry, OwnerTransaction,
)
from .services import _catch_up_investor_growth, catch_up_all_investor_growth


def _clean(value):
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


# ---------------------------------------------------------------------------
# CashManagementFlow stats
# ---------------------------------------------------------------------------

def get_cash_management_stats() -> dict:
    """
    Ensures investor growth is current (O(1) month-marker check — the
    per-investor sweep only actually runs on the first read of each month),
    then returns the store's cash-reconciliation and investor-capital
    position off the CashManagementFlow singleton — same pattern as
    cash_flow.get_cashflow_stats().
    """
    catch_up_all_investor_growth()

    cmf = CashManagementFlow.get_instance()
    return {
        "total_cash_lost"               : cmf.total_cash_lost,
        "total_cash_recovered"          : cmf.total_cash_recovered,
        "net_cash_lost"                 : cmf.net_cash_lost,
        "total_investor_capital"        : cmf.total_investor_capital,
        "total_investor_withdrawn"      : cmf.total_investor_withdrawn,
        "net_investor_capital"          : cmf.net_investor_capital,
        "total_investor_net_worth"      : cmf.total_investor_net_worth,
        "total_owner_contributions"       : cmf.total_owner_contributions,
        "total_owner_drawings"            : cmf.total_owner_drawings,
        "total_owner_contributions_count" : cmf.total_owner_contributions_count,
        "total_owner_withdrawals_count"   : cmf.total_owner_withdrawals_count,
        "net_owner_capital"               : cmf.net_owner_capital,
    }


# ---------------------------------------------------------------------------
# CashAdjustment
# ---------------------------------------------------------------------------

def get_all_cash_adjustments(
    *,
    adjustment_type : str = None,
    search          : str = None,
    date_from       : str = None,
    date_to         : str = None,
    min_amount      : str = None,
    max_amount      : str = None,
) -> QuerySet:
    """Returns all non-deleted cash adjustments with full filter support."""
    qs = CashAdjustment.objects.filter(is_deleted=False).select_related(
        "created_by", "updated_by",
    )

    if _clean(adjustment_type):
        qs = qs.filter(adjustment_type=_clean(adjustment_type))
    if _clean(search):
        qs = qs.filter(search_q(_clean(search), "reason"))
    if _clean(date_from):
        qs = qs.filter(adjustment_date__gte=_clean(date_from))
    if _clean(date_to):
        qs = qs.filter(adjustment_date__lte=_clean(date_to))
    if _clean(min_amount):
        qs = qs.filter(amount__gte=_clean(min_amount))
    if _clean(max_amount):
        qs = qs.filter(amount__lte=_clean(max_amount))

    return qs.order_by("-adjustment_date", "-created_at")


def get_cash_adjustment_by_id(pk: int) -> CashAdjustment:
    return get_object_or_404(CashAdjustment, pk=pk, is_deleted=False)


# ---------------------------------------------------------------------------
# Investor
# ---------------------------------------------------------------------------

def get_all_investors(*, search: str = None) -> QuerySet:
    """
    Returns all non-deleted investors, optionally filtered by name/email/phone.
    Growth is kept current via the O(1) month-marker check (the sweep runs
    once per month, covering every investor — a superset of the old
    per-matched-row loop, so results are never staler than before).
    """
    catch_up_all_investor_growth()

    qs = Investor.objects.filter(is_deleted=False)

    if _clean(search):
        qs = qs.filter(search_q(_clean(search), "name", "email", "contact_number"))

    return qs.order_by("name")


def get_investor_by_id(pk: int) -> Investor:
    investor = get_object_or_404(Investor, pk=pk, is_deleted=False)
    _catch_up_investor_growth(investor)
    investor.refresh_from_db()
    return investor


# ---------------------------------------------------------------------------
# InvestorValuationEntry — read-only growth history
# ---------------------------------------------------------------------------

def get_investor_valuation_entries(*, investor_id: str = None) -> QuerySet:
    qs = InvestorValuationEntry.objects.select_related("investor", "created_by")
    if _clean(investor_id):
        qs = qs.filter(investor_id=_clean(investor_id))
    return qs.order_by("-period", "-created_at")


# ---------------------------------------------------------------------------
# InvestorTransaction
# ---------------------------------------------------------------------------

def get_all_investor_transactions(
    *,
    investor_id      : str = None,
    transaction_type : str = None,
    search           : str = None,
    date_from        : str = None,
    date_to          : str = None,
    min_amount       : str = None,
    max_amount       : str = None,
) -> QuerySet:
    """Returns all non-deleted investor transactions with full filter support."""
    qs = InvestorTransaction.objects.filter(is_deleted=False).select_related(
        "investor", "created_by", "updated_by",
    )

    if _clean(investor_id):
        qs = qs.filter(investor_id=_clean(investor_id))
    if _clean(transaction_type):
        qs = qs.filter(transaction_type=_clean(transaction_type))
    if _clean(search):
        qs = qs.filter(search_q(_clean(search), "note", "investor__name"))
    if _clean(date_from):
        qs = qs.filter(transaction_date__gte=_clean(date_from))
    if _clean(date_to):
        qs = qs.filter(transaction_date__lte=_clean(date_to))
    if _clean(min_amount):
        qs = qs.filter(amount__gte=_clean(min_amount))
    if _clean(max_amount):
        qs = qs.filter(amount__lte=_clean(max_amount))

    return qs.order_by("-transaction_date", "-created_at")


def get_investor_transaction_by_id(pk: int) -> InvestorTransaction:
    return get_object_or_404(InvestorTransaction, pk=pk, is_deleted=False)


# ---------------------------------------------------------------------------
# OwnerTransaction
# ---------------------------------------------------------------------------

def get_all_owner_transactions(
    *,
    transaction_type : str = None,
    search           : str = None,
    date_from        : str = None,
    date_to          : str = None,
    min_amount       : str = None,
    max_amount       : str = None,
) -> QuerySet:
    """Returns all non-deleted owner transactions with full filter support."""
    qs = OwnerTransaction.objects.filter(is_deleted=False).select_related(
        "created_by", "updated_by",
    )

    if _clean(transaction_type):
        qs = qs.filter(transaction_type=_clean(transaction_type))
    if _clean(search):
        qs = qs.filter(search_q(_clean(search), "note"))
    if _clean(date_from):
        qs = qs.filter(transaction_date__gte=_clean(date_from))
    if _clean(date_to):
        qs = qs.filter(transaction_date__lte=_clean(date_to))
    if _clean(min_amount):
        qs = qs.filter(amount__gte=_clean(min_amount))
    if _clean(max_amount):
        qs = qs.filter(amount__lte=_clean(max_amount))

    return qs.order_by("-transaction_date", "-created_at")


def get_owner_transaction_by_id(pk: int) -> OwnerTransaction:
    return get_object_or_404(OwnerTransaction, pk=pk, is_deleted=False)
