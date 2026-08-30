from decimal import Decimal

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import ProductRate, ProductRateHistory


# ---------------------------------------------------------------------------
# ProductRate selectors
# ---------------------------------------------------------------------------

def _clean(value):
    """Returns None if value is None or empty/whitespace, else stripped string."""
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


# ProductRateReadSerializer nests the full ProductReadSerializer (which in
# turn nests category with its audit users) — everything here is
# serialized; without the user relations each row costs extra queries (N+1).
# Product no longer has a shelf (shelves are decoupled from Product).
_RATE_RELATED = (
    "product", "product__category",
    "product__created_by", "product__updated_by",
    "product__category__created_by", "product__category__updated_by",
    "updated_by", "created_by",
)


def get_all_rates(
    *,
    search      : str = None,
    category_id : str = None,
    min_price   : str = None,
    max_price   : str = None,
) -> QuerySet:
    """
    Returns current active rates with optional filtering and searching.

    Search  : product name or product code (case-insensitive, partial match)
    Filters : category id, min/max selling price
    """
    from backend.search import search_q

    qs = ProductRate.objects.select_related(*_RATE_RELATED).filter(
        product__is_deleted=False,
    )

    if _clean(search):
        qs = qs.filter(search_q(_clean(search), "product__name", "product__code"))
    if _clean(category_id):
        qs = qs.filter(product__category_id=_clean(category_id))
    if _clean(min_price):
        qs = qs.filter(selling_price__gte=_clean(min_price))
    if _clean(max_price):
        qs = qs.filter(selling_price__lte=_clean(max_price))

    return qs


def get_unpriced_products(*, search: str = None, category_id: str = None) -> QuerySet:
    """
    Products with no ProductRate yet — the "needs a price set" queue.
    Joins through UnpricedProduct (a materialized, explicitly-synced set —
    see rates.models.UnpricedProduct), not a live rate__isnull=True scan
    over the whole product catalog: as more products get priced over time,
    this join gets cheaper instead of staying proportional to catalog size.
    Paginated + searched the same way as get_all_rates.
    """
    from backend.search import search_q
    from purchases.models import Product

    # Mirrors purchases.selectors._PRODUCT_RELATED — ProductReadSerializer
    # nests category (with its own audit users) plus the product's own audit
    # users; without these every row costs N+1 queries.
    qs = Product.objects.select_related(
        "category", "created_by", "updated_by",
        "category__created_by", "category__updated_by",
    ).filter(is_deleted=False, unpriced_entry__isnull=False)
    if _clean(search):
        qs = qs.filter(search_q(_clean(search), "name", "code"))
    if _clean(category_id):
        qs = qs.filter(category_id=_clean(category_id))
    return qs


def get_rate_by_id(pk: int) -> ProductRate:
    return get_object_or_404(
        ProductRate.objects.select_related(*_RATE_RELATED),
        pk=pk,
        product__is_deleted=False,
    )


def get_rate_by_product_id(product_id: int) -> ProductRate:
    return get_object_or_404(
        ProductRate.objects.select_related(*_RATE_RELATED),
        product_id=product_id,
        product__is_deleted=False,
    )


# ---------------------------------------------------------------------------
# ProductRateHistory selectors
# ---------------------------------------------------------------------------

def get_history_for_product(product_id: int) -> QuerySet:
    """Full price change log for a single product, newest first."""
    return ProductRateHistory.objects.select_related(
        "product", "changed_by"
    ).filter(product_id=product_id)


def get_price_at_date(product_id: int, at: timezone.datetime) -> ProductRateHistory | None:
    """
    Returns the most recent history entry for a product at or before
    the given datetime. Used by billing to snapshot the correct price.
    Returns None if no price was set before that date.
    """
    return (
        ProductRateHistory.objects
        .filter(product_id=product_id, changed_at__lte=at)
        .order_by("-changed_at")
        .first()
    )