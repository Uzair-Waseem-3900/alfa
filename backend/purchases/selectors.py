from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Prefetch, Q, QuerySet, Sum
from django.db.models.functions import Coalesce
from django.db.models import DecimalField, Value
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date

from backend.search import search_q

from .models import (
    LOW_STOCK_THRESHOLD, Category, Inventory, InventoryStatsFlow,
    LostInventoryItem, LostInventoryRecord, Product, PurchaseItem,
    PurchaseItemShelfAllocation, PurchaseOrder, PurchaseReturn,
    PurchaseReturnItem, PurchaseReturnItemShelfAllocation, Shelf, ShelfStock,
    Supplier,
)


# ---------------------------------------------------------------------------
# Date-range helpers
# ---------------------------------------------------------------------------
# `created_at__date=...` wraps the column in a date-conversion, which stops
# PostgreSQL from using the created_at index. These convert a YYYY-MM-DD
# string into aware datetime bounds in the current timezone (the same
# boundaries __date uses), so filters become plain index-friendly range
# comparisons. On an unparseable value callers fall back to the original
# __date lookup — identical behavior to before.

def _day_start(value):
    """Aware datetime at local midnight of the given date string, or None."""
    day = parse_date(str(value))
    if day is None:
        return None
    return timezone.make_aware(datetime.combine(day, time.min))


def _next_day_start(value):
    """Aware datetime at local midnight of the day AFTER the given date, or None."""
    day = parse_date(str(value))
    if day is None:
        return None
    return timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min))


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------

def get_all_categories():
    # created_by/updated_by are serialized on every row — select_related
    # avoids 2 extra queries per category (N+1).
    return Category.objects.select_related("created_by", "updated_by").filter(is_deleted=False)

def get_category_by_id(pk: int) -> Category:
    return get_object_or_404(Category, pk=pk, is_deleted=False)


# ---------------------------------------------------------------------------
# Shelf
# ---------------------------------------------------------------------------

def get_all_shelves(*, search: str = None, product_search: str = None) -> QuerySet:
    """
    search         : shelf name (partial match)
    product_search : only shelves currently holding a product matching this
                      name/code (quantity > 0) — the second, independent
                      search bar on the Shelves page.
    """
    qs = Shelf.objects.select_related("created_by", "updated_by").filter(is_deleted=False)
    if _clean(search):
        qs = qs.filter(search_q(_clean(search), "name"))
    if _clean(product_search):
        # Both conditions must hold on the SAME stock_rows row — two
        # separate .filter() calls on a multi-valued relation each open
        # their own join, so a shelf could match "quantity>0" via one
        # product's row and the search via a different (possibly
        # zero-quantity) row of the searched product. A single .filter()
        # with both conditions combined keeps it to one join, one row.
        qs = qs.filter(
            Q(stock_rows__quantity__gt=0)
            & search_q(_clean(product_search), "stock_rows__product__name", "stock_rows__product__code")
        ).distinct()
    return qs

def get_shelf_by_id(pk: int) -> Shelf:
    return get_object_or_404(Shelf, pk=pk, is_deleted=False)


def get_shelf_stock_rows(shelf_id: int, *, search: str = None) -> QuerySet:
    """
    Products + quantities currently on one shelf — feeds the shelf detail
    page (click a shelf → see its contents). Only rows with quantity > 0
    are shown; a product that was fully moved/consumed off a shelf leaves
    no trace here (ShelfStockMovement is the audit trail for that).
    """
    # Only "product" is actually read (ShelfStockReadSerializer nests
    # ProductLiteSerializer: id/name/code only) — category/created_by/
    # updated_by were an unnecessary 3-way JOIN on every row.
    qs = ShelfStock.objects.select_related("product").filter(shelf_id=shelf_id, quantity__gt=0)
    if _clean(search):
        qs = qs.filter(search_q(_clean(search), "product__name", "product__code"))
    return qs.order_by("product__name")


def get_candidate_shelves_for_product(product_id: int, *, search: str = None) -> QuerySet:
    """
    Shelves that currently hold stock (quantity > 0) of a given product —
    the search source for every CONSUMPTION allocation context (sale line,
    purchase return, lost inventory): only shelves that can actually supply
    the product are offered. `search` narrows by shelf name — a large
    factory can have this product spread across many shelves, so this is a
    live backend search, not a client-preloaded dropdown.
    """
    qs = Shelf.objects.filter(
        is_deleted=False, stock_rows__product_id=product_id, stock_rows__quantity__gt=0,
    )
    if _clean(search):
        qs = qs.filter(search_q(_clean(search), "name"))
    return qs.annotate(
        available_quantity=Sum("stock_rows__quantity")
    ).order_by("name")


def compute_auto_shelf_allocation(*, product_id: int, quantity: int, exclude_shelf_ids: list = None) -> dict:
    """
    THE single implementation of shelf auto-allocation — shared by every
    consumption context (invoice items, purchase returns to supplier, lost
    inventory) through each app's own thin view, same as
    get_candidate_shelves_for_product above.

    Greedily fills `quantity` units of product_id across shelves that
    currently hold stock, largest available quantity first — minimizes how
    many shelves a single pick touches. `exclude_shelf_ids` skips shelves
    the caller already has a manual row for, so calling this again after
    the user has hand-picked one or two shelves only fills the remaining
    gap and never touches their existing rows.

    Deliberately does NOT select_for_update() — this is an advisory
    computation, not a write path. The actual concurrency-safety guarantee
    comes from validate_shelf_consumption's locked re-check at save/confirm
    time (same as get_candidate_shelves_for_product's dropdown, which is
    equally a snapshot). A stale suggestion here just means the user (or a
    second auto-allocate click) adjusts before saving — it can never result
    in an over-committed shelf actually being persisted.
    """
    exclude_shelf_ids = set(exclude_shelf_ids or [])
    rows = (
        ShelfStock.objects
        .select_related("shelf")
        .filter(product_id=product_id, quantity__gt=0, shelf__is_deleted=False)
        .exclude(shelf_id__in=exclude_shelf_ids)
        .order_by("-quantity", "shelf__name")
    )

    remaining = quantity
    allocations = []
    for row in rows:
        if remaining <= 0:
            break
        take = min(row.quantity, remaining)
        allocations.append({"shelf_id": row.shelf_id, "shelf_name": row.shelf.name, "quantity": take})
        remaining -= take

    return {"allocations": allocations, "shortfall": max(remaining, 0)}


# ---------------------------------------------------------------------------
# Supplier
# ---------------------------------------------------------------------------

def get_all_suppliers(*, search: str = None) -> QuerySet:
    # SYS-OPENING is the internal system supplier for opening stock — never shown to users.
    qs = Supplier.objects.select_related("created_by", "updated_by").filter(
        is_deleted=False,
    ).exclude(code="SYS-OPENING")
    if search:
        qs = qs.filter(search_q(search, "name", "code"))
    return qs

def get_supplier_by_id(pk: int) -> Supplier:
    return get_object_or_404(Supplier, pk=pk, is_deleted=False)


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------

# ProductReadSerializer nests full category (with its own audit users) plus
# the product's own audit users — everything here is serialized, nothing
# extra. Product no longer has a shelf (shelves are decoupled — physical
# location now lives in ShelfStock, per-product-per-shelf, not on Product).
_PRODUCT_RELATED = (
    "category", "created_by", "updated_by",
    "category__created_by", "category__updated_by",
)

def get_all_products(*, search: str = None) -> QuerySet:
    qs = Product.objects.select_related(*_PRODUCT_RELATED).filter(is_deleted=False)
    if search:
        qs = qs.filter(search_q(search, "name", "code"))
    return qs

def get_product_by_id(pk: int) -> Product:
    return get_object_or_404(
        Product.objects.select_related(*_PRODUCT_RELATED),
        pk=pk, is_deleted=False,
    )


# ---------------------------------------------------------------------------
# PurchaseOrder
# ---------------------------------------------------------------------------

def _order_qs():
    # Exactly what PurchaseOrderReadSerializer outputs — nothing more:
    #  - supplier's own audit users (SupplierReadSerializer serializes them)
    #  - live items with their product (PurchaseItem.objects already filters
    #    is_deleted=False via SoftDeleteManager), and each item's shelf
    #    allocations with their shelf (the put-away plan shown on the draft
    #    so the frontend can render "remaining to allocate" without N+1)
    # The old payments / returns / item-category prefetches were never
    # serialized here — each was a wasted query on every list request.
    return PurchaseOrder.objects.select_related(
        "supplier", "supplier__created_by", "supplier__updated_by",
        "created_by", "updated_by", "confirmed_by", "deleted_by",
    ).prefetch_related(
        Prefetch(
            "items",
            queryset=PurchaseItem.objects.select_related("product").prefetch_related(
                Prefetch(
                    "shelf_allocations",
                    queryset=PurchaseItemShelfAllocation.objects.select_related("shelf"),
                ),
            ),
        ),
    )


def _clean(value):
    """Returns None if value is None or empty/whitespace string, else stripped value."""
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped if stripped else None


def get_all_purchase_orders(
    *,
    status         : str = None,
    supplier_name  : str = None,
    supplier_code  : str = None,
    order_number   : str = None,
    date           : str = None,
    date_from      : str = None,
    date_to        : str = None,
    payment_status : str = None,
    payment_type   : str = None,
    min_amount     : str = None,
    max_amount     : str = None,
) -> QuerySet:
    """
    Master filter selector — every list view uses this.
    All params are optional. Only non-empty values are applied.
    _clean() ensures empty strings from query params don't slip through.
    """
    # Opening-balance orders (real suppliers) ARE shown — they are real
    # outstanding payables that must be tracked and settled. Only opening-STOCK
    # orders (the internal SYS-OPENING supplier) are hidden.
    qs = _order_qs().filter(is_deleted=False).exclude(supplier__code="SYS-OPENING")

    if _clean(status):
        qs = qs.filter(status=_clean(status))
    if _clean(supplier_name):
        qs = qs.filter(search_q(_clean(supplier_name), "supplier__name"))
    if _clean(supplier_code):
        qs = qs.filter(search_q(_clean(supplier_code), "supplier__code"))
    if _clean(order_number):
        qs = qs.filter(search_q(_clean(order_number), "order_number"))
    if _clean(date):
        start = _day_start(_clean(date))
        end   = _next_day_start(_clean(date))
        if start and end:
            qs = qs.filter(created_at__gte=start, created_at__lt=end)
        else:
            qs = qs.filter(created_at__date=_clean(date))
    if _clean(date_from):
        start = _day_start(_clean(date_from))
        qs = qs.filter(created_at__gte=start) if start else qs.filter(created_at__date__gte=_clean(date_from))
    if _clean(date_to):
        end = _next_day_start(_clean(date_to))
        qs = qs.filter(created_at__lt=end) if end else qs.filter(created_at__date__lte=_clean(date_to))
    if _clean(payment_status):
        qs = qs.filter(payment_status=_clean(payment_status))
    if _clean(payment_type):
        qs = qs.filter(payment_type=_clean(payment_type))
    if _clean(min_amount):
        qs = qs.filter(net_payable__gte=_clean(min_amount))
    if _clean(max_amount):
        qs = qs.filter(net_payable__lte=_clean(max_amount))

    return qs


def get_draft_purchase_orders() -> QuerySet:
    # Data-entry orders are always confirmed, so drafts are naturally unaffected.
    return _order_qs().filter(is_deleted=False, status=PurchaseOrder.Status.DRAFT)


def get_confirmed_purchase_orders(
    *,
    supplier_name  : str = None,
    supplier_code  : str = None,
    date_from      : str = None,
    date_to        : str = None,
    payment_status : str = None,
    min_amount     : str = None,
    max_amount     : str = None,
) -> QuerySet:
    return get_all_purchase_orders(
        status="confirmed",
        supplier_name=supplier_name,
        supplier_code=supplier_code,
        date_from=date_from,
        date_to=date_to,
        payment_status=payment_status,
        min_amount=min_amount,
        max_amount=max_amount,
    )


def get_purchase_order_by_id(pk: int) -> PurchaseOrder:
    return get_object_or_404(_order_qs(), pk=pk, is_deleted=False)


# ---------------------------------------------------------------------------
# PurchaseItem
# ---------------------------------------------------------------------------

def get_purchase_item_by_id(pk: int) -> PurchaseItem:
    return get_object_or_404(
        PurchaseItem.objects.select_related("order", "product"),
        pk=pk, is_deleted=False,
    )


def get_purchase_item_with_allocations_by_id(pk: int) -> PurchaseItem:
    return get_object_or_404(
        PurchaseItem.objects.select_related("order", "product").prefetch_related(
            Prefetch(
                "shelf_allocations",
                queryset=PurchaseItemShelfAllocation.objects.select_related("shelf"),
            ),
        ),
        pk=pk, is_deleted=False,
    )


def get_available_purchase_items_for_fifo(product_id: int, *, for_update: bool = False) -> QuerySet:
    """
    Returns confirmed purchase items with remaining stock, oldest first (FIFO).
    Used by billing app to consume stock.

    for_update=True locks the batch rows (select_for_update) — REQUIRED for
    every path that decrements remaining_quantity, so two concurrent stock
    consumers (invoice confirm, lost-inventory record, ...) can never sell
    the same physical units twice. Must run inside a transaction. Read-only
    paths (previews, draft validation) must NOT pass it. No-op on SQLite
    (dev); real row locks on PostgreSQL, acquired in FIFO order so
    same-product consumers can't deadlock each other.
    """
    qs = (
        PurchaseItem.objects
        .filter(
            product_id=product_id,
            is_deleted=False,
            order__status=PurchaseOrder.Status.CONFIRMED,
            remaining_quantity__gt=0,
        )
        .order_by("order__confirmed_at")
    )
    if for_update:
        qs = qs.select_for_update()
    return qs


# ---------------------------------------------------------------------------
# PurchaseReturn
# ---------------------------------------------------------------------------

_RETURN_ITEM_PREFETCH = Prefetch(
    "items",
    queryset=PurchaseReturnItem.objects.select_related("purchase_item__product").prefetch_related(
        Prefetch(
            "shelf_allocations",
            queryset=PurchaseReturnItemShelfAllocation.objects.select_related("shelf"),
        ),
    ),
)


def get_returns_for_order(order_id: int) -> QuerySet:
    # order__supplier: the read serializer outputs order_number and
    # supplier_name for every return — without this it's 2 queries per row.
    return PurchaseReturn.objects.filter(
        order_id=order_id, is_deleted=False,
    ).select_related("order__supplier", "created_by", "accepted_by").prefetch_related(
        _RETURN_ITEM_PREFETCH,
    )


def get_purchase_return_by_id(pk: int) -> PurchaseReturn:
    return get_object_or_404(
        PurchaseReturn.objects.select_related(
            "order", "created_by", "accepted_by",
        ).prefetch_related(_RETURN_ITEM_PREFETCH),
        pk=pk, is_deleted=False,
    )


def get_purchase_return_item_by_id(pk: int) -> PurchaseReturnItem:
    return get_object_or_404(
        PurchaseReturnItem.objects.select_related(
            "return_record", "purchase_item__product",
        ),
        pk=pk,
    )


def get_purchase_return_item_with_allocations_by_id(pk: int) -> PurchaseReturnItem:
    return get_object_or_404(
        PurchaseReturnItem.objects.select_related(
            "return_record", "purchase_item__product",
        ).prefetch_related(
            Prefetch(
                "shelf_allocations",
                queryset=PurchaseReturnItemShelfAllocation.objects.select_related("shelf"),
            ),
        ),
        pk=pk,
    )


def get_all_returns(
    *,
    status        : str = None,
    supplier_name : str = None,
    supplier_code : str = None,
    order_number  : str = None,
    date_from     : str = None,
    date_to       : str = None,
) -> QuerySet:
    qs = PurchaseReturn.objects.select_related(
        "order__supplier", "created_by", "accepted_by",
    ).prefetch_related(_RETURN_ITEM_PREFETCH).filter(is_deleted=False)

    if _clean(status):
        qs = qs.filter(status=_clean(status))
    if _clean(supplier_name):
        qs = qs.filter(search_q(_clean(supplier_name), "order__supplier__name"))
    if _clean(supplier_code):
        qs = qs.filter(search_q(_clean(supplier_code), "order__supplier__code"))
    if _clean(order_number):
        qs = qs.filter(search_q(_clean(order_number), "order__order_number"))
    if _clean(date_from):
        start = _day_start(_clean(date_from))
        qs = qs.filter(created_at__gte=start) if start else qs.filter(created_at__date__gte=_clean(date_from))
    if _clean(date_to):
        end = _next_day_start(_clean(date_to))
        qs = qs.filter(created_at__lt=end) if end else qs.filter(created_at__date__lte=_clean(date_to))

    return qs.order_by("-created_at")


# ---------------------------------------------------------------------------
# Supplier Payment
# ---------------------------------------------------------------------------

def get_payments_for_order(order_id: int, *, reference: str = None) -> QuerySet:
    from .models import SupplierPayment
    qs = SupplierPayment.objects.filter(
        order_id=order_id, is_deleted=False,
    ).select_related("created_by", "order__supplier").order_by("-payment_date")
    if _clean(reference):
        qs = qs.filter(search_q(_clean(reference), "reference_number"))
    return qs


def get_all_supplier_payments(
    *,
    reference     : str = None,
    supplier_name : str = None,
    supplier_code : str = None,
    method        : str = None,
    date_from     : str = None,
    date_to       : str = None,
) -> QuerySet:
    """Search supplier payments across all orders with full filter support."""
    from .models import SupplierPayment
    qs = SupplierPayment.objects.filter(
        is_deleted=False, amount__gt=0,
    ).select_related("order__supplier", "created_by").order_by("-payment_date")
    if _clean(reference):
        qs = qs.filter(search_q(_clean(reference), "reference_number"))
    if _clean(supplier_name):
        qs = qs.filter(search_q(_clean(supplier_name), "order__supplier__name"))
    if _clean(supplier_code):
        qs = qs.filter(search_q(_clean(supplier_code), "order__supplier__code"))
    if _clean(method):
        qs = qs.filter(method=_clean(method))
    if _clean(date_from):
        qs = qs.filter(payment_date__gte=_clean(date_from))
    if _clean(date_to):
        qs = qs.filter(payment_date__lte=_clean(date_to))
    return qs


def get_supplier_payment_by_id(pk: int):
    from .models import SupplierPayment
    return get_object_or_404(SupplierPayment, pk=pk, is_deleted=False)


# ---------------------------------------------------------------------------
# Supplier outstanding (aggregate)
# ---------------------------------------------------------------------------

def get_supplier_payable_summary(supplier_id: int) -> dict:
    """
    Aggregate payable summary for one supplier across all confirmed orders.
    Shows total we owe, total we paid, total outstanding.
    """
    orders = PurchaseOrder.objects.filter(
        supplier_id=supplier_id,
        is_deleted=False,
        status=PurchaseOrder.Status.CONFIRMED,
    )
    agg = orders.aggregate(
        total_net_payable       = Sum("net_payable"),
        total_paid              = Sum("total_paid"),
        total_payable_outstanding = Sum("payable_outstanding"),
    )
    return {
        "supplier_id"              : supplier_id,
        "total_net_payable"        : agg["total_net_payable"]          or Decimal("0"),
        "total_paid"               : agg["total_paid"]                 or Decimal("0"),
        "total_payable_outstanding": agg["total_payable_outstanding"]  or Decimal("0"),
    }


def get_suppliers_with_outstanding(
    *,
    search          : str = None,
    payment_status  : str = None,
    min_outstanding : str = None,
    max_outstanding : str = None,
) -> QuerySet:
    """
    Lists suppliers with their total payable_outstanding annotated.
    Supports full filtering:
        search         : supplier name or code (partial match)
        payment_status : filter by order-level payment_status
                         (partial = at least one partial order,
                          unpaid  = at least one fully unpaid order)
        min_outstanding: minimum total outstanding amount
        max_outstanding: maximum total outstanding amount

    NOTE: payment_status here filters the ORDERS being summed, not the supplier.
    e.g. ?payment_status=partial shows suppliers who have at least one partial order.
    """
    # Build the order filter for annotation
    order_filter = Q(
        purchase_orders__is_deleted=False,
        purchase_orders__status=PurchaseOrder.Status.CONFIRMED,
    )
    if _clean(payment_status):
        order_filter &= Q(purchase_orders__payment_status=_clean(payment_status))

    qs = Supplier.objects.filter(is_deleted=False).exclude(code="SYS-OPENING").annotate(
        outstanding=Coalesce(
            Sum(
                "purchase_orders__payable_outstanding",
                filter=order_filter,
            ),
            Value(0, output_field=DecimalField()),
        )
    ).filter(outstanding__gt=0)

    if _clean(search):
        qs = qs.filter(search_q(_clean(search), "name", "code"))
    if _clean(min_outstanding):
        qs = qs.filter(outstanding__gte=_clean(min_outstanding))
    if _clean(max_outstanding):
        qs = qs.filter(outstanding__lte=_clean(max_outstanding))

    return qs.order_by("-outstanding")


def get_order_payment_summary(order_id: int) -> PurchaseOrder:
    """Full payment breakdown for a single purchase order."""
    from .models import SupplierPayment
    # payments prefetched with their created_by (serialized per payment).
    # SupplierPayment.objects is the SoftDeleteManager — same filtering the
    # old bare "payments" prefetch applied via the related manager. The old
    # items__product prefetch was never serialized here — dropped.
    return get_object_or_404(
        PurchaseOrder.objects.select_related("supplier").prefetch_related(
            Prefetch("payments", queryset=SupplierPayment.objects.select_related("created_by", "order__supplier")),
        ),
        pk=order_id, is_deleted=False,
    )


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

def get_all_inventory(
    *,
    search      : str = None,
    category_id : str = None,
) -> QuerySet:
    """
    Returns inventory (global per-product total) with optional filters:
        search      : product name or product code (partial, case-insensitive)
        category_id : filter by category id
    Filtering by shelf no longer applies here — a product's stock can now
    span multiple shelves. Use get_shelf_stock_rows for "what's on shelf X".
    """
    # InventoryReadSerializer nests the full ProductReadSerializer (which in
    # turn nests category with its audit users) — without these, each row
    # costs extra queries (N+1).
    qs = Inventory.objects.select_related(
        "product", "product__category", "last_updated_by",
        "product__created_by", "product__updated_by",
        "product__category__created_by", "product__category__updated_by",
    ).filter(product__is_deleted=False)

    if _clean(search):
        qs = qs.filter(search_q(_clean(search), "product__name", "product__code"))
    if _clean(category_id):
        qs = qs.filter(product__category_id=_clean(category_id))

    return qs.order_by("product__name")


def get_inventory_by_product_id(product_id: int) -> Inventory:
    return get_object_or_404(
        Inventory.objects.select_related("product"),
        product_id=product_id,
    )


def get_inventory_stats() -> InventoryStatsFlow:
    """
    O(1) inventory stats for the Inventory page cards — reads the stored
    singleton instead of counting rows. Kept in sync at write time by
    services.sync_inventory()/delete_product(); rebuilt by
    backfill_inventory_stats.
    """
    return InventoryStatsFlow.get_instance()


def get_low_stock_inventory(*, search: str = None, category_id: str = None) -> QuerySet:
    """
    Breakdown behind the "Low Stock" card: 0 < quantity <= LOW_STOCK_THRESHOLD.
    Same filters as the main inventory list; quantity is indexed.
    """
    return get_all_inventory(
        search=search, category_id=category_id,
    ).filter(quantity__gt=0, quantity__lte=LOW_STOCK_THRESHOLD)


def get_out_of_stock_inventory(*, search: str = None, category_id: str = None) -> QuerySet:
    """
    Breakdown behind the "Out of Stock" card: quantity <= 0.
    Same filters as the main inventory list; quantity is indexed.
    """
    return get_all_inventory(
        search=search, category_id=category_id,
    ).filter(quantity__lte=0)


def get_outstanding_orders_for_supplier(supplier_id: int) -> QuerySet:
    """
    Returns all confirmed PurchaseOrders for a supplier that still have
    payable_outstanding > 0. Order-level breakdown of what we owe.
    Supports the "supplier bill-wise outstanding" view.
    """
    return (
        _order_qs()
        .filter(
            supplier_id=supplier_id,
            is_deleted=False,
            status=PurchaseOrder.Status.CONFIRMED,
            payable_outstanding__gt=0,
        )
        .order_by("created_at")
    )


def get_all_lost_inventory_records(
    *,
    search        : str = None,
    product_id    : str = None,
    product_name  : str = None,
    product_code  : str = None,
    reason        : str = None,
    date          : str = None,
    date_from     : str = None,
    date_to       : str = None,
    min_amount    : str = None,
    max_amount    : str = None,
) -> QuerySet:
    """
    Master filter selector for lost inventory records — mirrors the
    PurchaseOrder filter set (get_all_purchase_orders) wherever an
    equivalent field exists on lost inventory.
        search       : reference number (partial match)
        product_id   : filter records containing a specific product
        product_name : partial match on any item's product name
        product_code : partial match on any item's product code
        reason       : partial match on any item's reason
        date         : exact created_at date
        date_from / date_to : created_at date range
        min_amount / max_amount : total_lost_amount range
    """
    qs = LostInventoryRecord.objects.filter(is_deleted=False).select_related(
        "created_by", "updated_by",
    ).prefetch_related("items__product")

    if _clean(search):
        qs = qs.filter(search_q(_clean(search), "reference_number"))
    if _clean(product_id):
        qs = qs.filter(items__product_id=_clean(product_id))
    if _clean(product_name):
        qs = qs.filter(search_q(_clean(product_name), "items__product__name"))
    if _clean(product_code):
        qs = qs.filter(search_q(_clean(product_code), "items__product__code"))
    if _clean(reason):
        qs = qs.filter(search_q(_clean(reason), "items__reason"))
    if _clean(date):
        start = _day_start(_clean(date))
        end   = _next_day_start(_clean(date))
        if start and end:
            qs = qs.filter(created_at__gte=start, created_at__lt=end)
        else:
            qs = qs.filter(created_at__date=_clean(date))
    if _clean(date_from):
        start = _day_start(_clean(date_from))
        qs = qs.filter(created_at__gte=start) if start else qs.filter(created_at__date__gte=_clean(date_from))
    if _clean(date_to):
        end = _next_day_start(_clean(date_to))
        qs = qs.filter(created_at__lt=end) if end else qs.filter(created_at__date__lte=_clean(date_to))
    if _clean(min_amount):
        qs = qs.filter(total_lost_amount__gte=_clean(min_amount))
    if _clean(max_amount):
        qs = qs.filter(total_lost_amount__lte=_clean(max_amount))

    if any(_clean(v) for v in (product_id, product_name, product_code, reason)):
        qs = qs.distinct()

    return qs.order_by("-created_at")


def get_lost_inventory_record_by_id(pk: int) -> LostInventoryRecord:
    # fifo_consumptions are not serialized by LostInventoryReadSerializer —
    # prefetching them was wasted work on every detail request.
    return get_object_or_404(
        LostInventoryRecord.objects.select_related(
            "created_by", "updated_by",
        ).prefetch_related("items__product"),
        pk=pk, is_deleted=False,
    )


def get_lost_inventory_item_by_id(pk: int) -> LostInventoryItem:
    return get_object_or_404(
        LostInventoryItem.objects.select_related("product", "record"),
        pk=pk,
    )


def get_fifo_cost_preview(*, product_id: int, quantity: int) -> dict:
    """
    Read-only preview of the blended FIFO unit cost for a product/quantity,
    without consuming any stock. Used by the lost-inventory page to show the
    expected cost before submission. Mirrors the walk in
    purchases.services._consume_fifo_for_loss, but never writes.
    """
    batches   = get_available_purchase_items_for_fifo(product_id)
    remaining = quantity
    total_cost = Decimal("0")
    available  = 0

    for batch in batches:
        available += batch.remaining_quantity
        if remaining <= 0:
            continue
        consume = min(batch.remaining_quantity, remaining)
        tax_inclusive_unit_cost = (
            batch.total_price / batch.quantity if batch.quantity > 0 else batch.unit_price
        )
        total_cost += consume * tax_inclusive_unit_cost
        remaining  -= consume

    consumed  = quantity - remaining
    unit_cost = (total_cost / Decimal(str(consumed))) if consumed > 0 else Decimal("0")

    return {
        "product_id"        : product_id,
        "quantity"          : quantity,
        "available_quantity": available,
        "unit_cost"         : unit_cost,
        "total_cost"        : total_cost,
        "sufficient_stock"  : remaining <= 0,
    }


def get_all_outstanding_orders(
    *,
    supplier_name  : str = None,
    supplier_code  : str = None,
    payment_status : str = None,
    date_from      : str = None,
    date_to        : str = None,
    min_outstanding: str = None,
    max_outstanding: str = None,
) -> QuerySet:
    """
    Returns ALL confirmed orders with payable_outstanding > 0,
    across all suppliers. Full filter support.
    Supports the "all outstanding bills" view.
    """
    from django.db.models import Q
    qs = (
        _order_qs()
        .filter(
            is_deleted=False,
            status=PurchaseOrder.Status.CONFIRMED,
            payable_outstanding__gt=0,
        )
    )

    if _clean(supplier_name):
        qs = qs.filter(search_q(_clean(supplier_name), "supplier__name"))
    if _clean(supplier_code):
        qs = qs.filter(search_q(_clean(supplier_code), "supplier__code"))
    if _clean(payment_status):
        qs = qs.filter(payment_status=_clean(payment_status))
    if _clean(date_from):
        qs = qs.filter(created_at__date__gte=_clean(date_from))
    if _clean(date_to):
        qs = qs.filter(created_at__date__lte=_clean(date_to))
    if _clean(min_outstanding):
        qs = qs.filter(payable_outstanding__gte=_clean(min_outstanding))
    if _clean(max_outstanding):
        qs = qs.filter(payable_outstanding__lte=_clean(max_outstanding))

    return qs.order_by("-payable_outstanding")