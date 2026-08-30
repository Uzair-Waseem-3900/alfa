from django.db.models import QuerySet
from django.shortcuts import get_object_or_404

from backend.search import search_q

from .models import Asset, AssetCategory, AssetDisposal, AssetFlow, AssetPayment, AssetValuationEntry
from .services import _catch_up_asset_depreciation, catch_up_all_asset_depreciation


def _clean(value):
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


# ---------------------------------------------------------------------------
# AssetCategory
# ---------------------------------------------------------------------------

def get_all_asset_categories(*, search: str = None) -> QuerySet:
    # created_by is serialized on every row — select_related avoids one
    # extra query per category (N+1).
    qs = AssetCategory.objects.select_related("created_by")
    if _clean(search):
        qs = qs.filter(search_q(_clean(search), "name"))
    return qs.order_by("name")


def get_asset_category_by_id(pk: int) -> AssetCategory:
    return get_object_or_404(AssetCategory, pk=pk)


# ---------------------------------------------------------------------------
# Asset — every read path runs catch-up first, so results are always current
# without any background job (see assets.services._catch_up_asset_depreciation).
# ---------------------------------------------------------------------------

def get_all_assets(
    *,
    category_id      : str = None,
    acquisition_type : str = None,
    is_disposed      : str = None,
    search           : str = None,
) -> QuerySet:
    # Depreciation is kept current via the O(1) month-marker sweep (covers
    # every active asset — a superset of the old per-matched-row loop, which
    # also evaluated the queryset twice). created_by/updated_by are
    # serialized on every row — joined here to avoid two queries per asset.
    catch_up_all_asset_depreciation()

    qs = Asset.objects.filter(is_deleted=False).select_related(
        "category", "created_by", "updated_by",
    )

    if _clean(category_id):
        qs = qs.filter(category_id=_clean(category_id))
    if _clean(acquisition_type):
        qs = qs.filter(acquisition_type=_clean(acquisition_type))
    if is_disposed is not None and _clean(is_disposed) is not None:
        qs = qs.filter(is_disposed=_clean(is_disposed).lower() == "true")
    if _clean(search):
        qs = qs.filter(search_q(_clean(search), "name"))

    return qs.order_by("-acquisition_date", "-created_at")


def get_asset_by_id(pk: int) -> Asset:
    asset = get_object_or_404(
        Asset.objects.select_related("category", "created_by", "updated_by"),
        pk=pk, is_deleted=False,
    )
    _catch_up_asset_depreciation(asset)
    asset.refresh_from_db()
    return asset


# ---------------------------------------------------------------------------
# AssetValuationEntry — read-only history
# ---------------------------------------------------------------------------

def get_asset_valuation_entries(
    *, asset_id: str = None, entry_type: str = None,
) -> QuerySet:
    qs = AssetValuationEntry.objects.select_related("asset", "created_by")

    if _clean(asset_id):
        qs = qs.filter(asset_id=_clean(asset_id))
    if _clean(entry_type):
        qs = qs.filter(entry_type=_clean(entry_type))

    return qs.order_by("-period", "-created_at")


# ---------------------------------------------------------------------------
# AssetDisposal
# ---------------------------------------------------------------------------

def get_all_asset_disposals(*, disposal_type: str = None, category_id: str = None) -> QuerySet:
    qs = AssetDisposal.objects.select_related("asset", "asset__category", "created_by")
    if _clean(disposal_type):
        qs = qs.filter(disposal_type=_clean(disposal_type))
    if _clean(category_id):
        qs = qs.filter(asset__category_id=_clean(category_id))
    return qs.order_by("-disposal_date", "-created_at")


# ---------------------------------------------------------------------------
# AssetPayment — the unified purchases+sales feed (event table, see model
# docstring). One indexed query per page, regardless of history size.
# ---------------------------------------------------------------------------

def get_all_asset_payments(
    *, payment_type: str = None, date_from: str = None, date_to: str = None, search: str = None,
) -> QuerySet:
    qs = AssetPayment.objects.select_related(
        "asset", "asset__category", "asset__disposal", "created_by",
    )
    if _clean(payment_type):
        qs = qs.filter(payment_type=_clean(payment_type))
    if _clean(date_from):
        qs = qs.filter(date__gte=_clean(date_from))
    if _clean(date_to):
        qs = qs.filter(date__lte=_clean(date_to))
    if _clean(search):
        qs = qs.filter(search_q(_clean(search), "asset__name"))
    return qs.order_by("-date", "-created_at")


def get_asset_payment_by_id(pk: int) -> AssetPayment:
    return get_object_or_404(
        AssetPayment.objects.select_related("asset", "asset__category", "asset__disposal", "created_by"),
        pk=pk,
    )


# ---------------------------------------------------------------------------
# AssetFlow stats
# ---------------------------------------------------------------------------

def get_asset_stats() -> dict:
    """
    Ensures depreciation is current (O(1) month-marker check — the per-asset
    sweep only actually runs on the first read of each month, or after a
    rate edit), then reads the AssetFlow singleton — always current, no cron.
    """
    catch_up_all_asset_depreciation()

    af = AssetFlow.get_instance()
    return {
        "total_asset_cost"               : af.total_asset_cost,
        "total_current_worth"            : af.total_current_worth,
        "total_accumulated_depreciation" : af.total_accumulated_depreciation,
        "total_disposed_count"           : af.total_disposed_count,
        "total_gain_on_disposal"         : af.total_gain_on_disposal,
        "total_loss_on_disposal"         : af.total_loss_on_disposal,
    }
