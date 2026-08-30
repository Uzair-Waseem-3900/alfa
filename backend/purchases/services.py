from decimal import Decimal
from django.db import transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from .models import (
    LOW_STOCK_THRESHOLD, Category, DocumentCounter, Inventory,
    InventoryStatsFlow, LostInventoryFIFOConsumption, LostInventoryItem,
    LostInventoryRecord, LostInventoryRecovery, Product, ProductStockMovement,
    PurchaseItem, PurchaseItemShelfAllocation, PurchaseOrder, PurchaseReturn,
    PurchaseReturnItem, PurchaseReturnItemShelfAllocation,
    SavedPurchaseOrderPDF, Shelf, ShelfStock, ShelfStockMovement,
    StockMovementFlow, Supplier, SupplierPayment,
)
from .selectors import (
    get_available_purchase_items_for_fifo, get_category_by_id,
    get_lost_inventory_item_by_id, get_product_by_id, get_purchase_item_by_id,
    get_purchase_order_by_id, get_purchase_return_by_id, get_shelf_by_id,
    get_supplier_by_id, get_supplier_payment_by_id,
)
from .utils import calculate_total_price


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _soft_delete(instance, user) -> None:
    """DRY soft delete — single place for this logic."""
    instance.is_deleted = True
    instance.deleted_at = timezone.now()
    instance.deleted_by = user
    instance.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])


def _adjust_stock_movement(
    *, product_id: int,
    purchased_delta: int = 0,
    purchase_returned_delta: int = 0,
    sold_delta: int = 0,
    sale_returned_delta: int = 0,
    lost_delta: int = 0,
    found_delta: int = 0,
) -> None:
    """
    The ONLY function that writes to ProductStockMovement/StockMovementFlow
    — called from purchases (PO confirm, purchase return accept, lost
    inventory record, mark-as-found) and billing (invoice confirm, customer
    return accept) for the Stock Movement Report. All six fields only ever
    increase (none of the six source events are ever undone in this
    codebase), so no floor-at-0 logic is needed — plain PositiveIntegerField
    addition.

    Additions run inside the database via F() expressions, so two stock
    events committing at the same instant can never overwrite each other's
    counter update (the old read-add-save on the flow singleton could lose
    one side's addition). No row lock needed. .update() bypasses auto_now,
    hence last_updated_at is set explicitly — same field, same meaning.
    """
    deltas = {
        "total_purchased"        : purchased_delta,
        "total_purchase_returned": purchase_returned_delta,
        "total_sold"             : sold_delta,
        "total_sale_returned"    : sale_returned_delta,
        "total_lost"             : lost_delta,
        "total_found"            : found_delta,
    }
    with transaction.atomic():
        now = timezone.now()
        ProductStockMovement.objects.get_or_create(product_id=product_id)
        ProductStockMovement.objects.filter(product_id=product_id).update(
            last_updated_at=now,
            **{field: F(field) + delta for field, delta in deltas.items()},
        )

        StockMovementFlow.get_instance()
        StockMovementFlow.objects.filter(pk=1).update(
            last_updated_at=now,
            **{field: F(field) + delta for field, delta in deltas.items()},
        )


# Model + reference field that each counter doc_type seeds its legacy max from.
_DOC_TYPE_SOURCES = {
    "PO"  : (PurchaseOrder,       "order_number"),
    "SPY" : (SupplierPayment,     "reference_number"),
    "RTN" : (PurchaseReturn,      "reference_number"),
    "LOSS": (LostInventoryRecord, "reference_number"),
}


def _legacy_max_sequence(model, field: str, prefix: str) -> int:
    """
    Numeric max of the sequence part of existing references for this
    prefix — parsed as integers, NOT text-sorted (text sort is the bug that
    broke the old generators at 10000). Scans ALL rows including
    soft-deleted ones (a soft-deleted document still owns its unique
    reference). O(N) but runs only once per counter, when its row is first
    created.
    """
    manager = getattr(model, "all_objects", model._default_manager)
    refs = manager.filter(
        **{f"{field}__startswith": prefix}
    ).values_list(field, flat=True)
    max_seq = 0
    for ref in refs:
        try:
            max_seq = max(max_seq, int(ref.rsplit("-", 1)[-1]))
        except (TypeError, ValueError):
            continue
    return max_seq


def next_reference(*, counter_key: str, prefix_label: str, model, field: str) -> str:
    """
    Returns the next sequential reference (e.g. PO-2026-0001) by locking the
    (counter_key, year) DocumentCounter row and incrementing it — O(1) and
    race-safe regardless of how many documents exist. Numbers below 10000
    keep the historical 4-digit padding; beyond that the number simply grows
    (PO-2026-10000) since ordering no longer relies on text sort.

    counter_key and prefix_label are separate because two apps can share a
    display prefix while keeping independent sequences: purchase returns and
    billing returns both format as RTN-<year>-#### (unique per table), so
    billing uses counter_key="BILL-RTN" with prefix_label="RTN".
    """
    year   = timezone.localtime(timezone.now()).year
    prefix = f"{prefix_label}-{year}-"
    with transaction.atomic():
        counter, created = (
            DocumentCounter.objects.select_for_update()
            .get_or_create(doc_type=counter_key, year=year)
        )
        if created:
            counter.last_number = _legacy_max_sequence(model, field, prefix)
        counter.last_number += 1
        counter.save(update_fields=["last_number"])
        return f"{prefix}{counter.last_number:04d}"


def _next_reference(doc_type: str) -> str:
    """Purchases-app wrapper: counter key and prefix are the same string."""
    model, field = _DOC_TYPE_SOURCES[doc_type]
    return next_reference(counter_key=doc_type, prefix_label=doc_type, model=model, field=field)


def _generate_order_number() -> str:
    """Sequential PO number: PO-2026-0001."""
    return _next_reference("PO")


def _generate_supplier_payment_reference() -> str:
    """Sequential supplier payment reference: SPY-2026-0001."""
    return _next_reference("SPY")


def _generate_purchase_return_reference() -> str:
    """Sequential purchase return reference: RTN-2026-0001."""
    return _next_reference("RTN")


def _generate_lost_inventory_reference() -> str:
    """Sequential lost inventory reference: LOSS-2026-0001."""
    return _next_reference("LOSS")


def _recalculate_order_totals(order: PurchaseOrder) -> None:
    """
    Recomputes PurchaseOrder header totals from all line items.
    Single source of truth — called after confirmation and returns.
    """
    gross = Decimal("0")
    gst   = Decimal("0")
    wht   = Decimal("0")
    net   = Decimal("0")

    for item in order.items.filter(is_deleted=False):
        gross += item.gross_amount
        gst   += item.gst_amount
        wht   += item.wht_amount
        net   += item.total_price

    order.gross_amount = gross
    order.gst_total    = gst
    order.wht_total    = wht
    order.net_payable  = net
    order.save(update_fields=["gross_amount", "gst_total", "wht_total", "net_payable"])


def _sync_order_payable(order: PurchaseOrder) -> None:
    """
    Recomputes payable_outstanding, total_paid, payment_status for a PurchaseOrder.
    Called after every SupplierPayment create/delete and after return acceptance.

    Logic (mirrors billing._sync_invoice_payment_summary):
        - On confirmation: payable_outstanding = net_payable (we owe full amount)
        - Each payment reduces payable_outstanding
        - Return credit notes (negative payments) reduce payable_outstanding further
        - payment_status = unpaid / partial / paid
    """
    # One conditional aggregate instead of loading every payment row into
    # Python — same numbers, one query (mirrors billing's
    # _sync_invoice_payment_summary).
    agg = SupplierPayment.objects.filter(order=order, is_deleted=False).aggregate(
        paid=Sum("amount", filter=Q(amount__gt=0)),
        credits=Sum("amount", filter=Q(amount__lt=0)),
    )
    total_paid     = agg["paid"] or Decimal("0")
    return_credits = abs(agg["credits"] or Decimal("0"))

    payable_outstanding = max(
        Decimal("0"),
        order.net_payable - total_paid - return_credits,
    )

    if payable_outstanding <= 0:
        payment_status = PurchaseOrder.PaymentStatus.PAID
    elif total_paid > 0 or return_credits > 0:
        payment_status = PurchaseOrder.PaymentStatus.PARTIAL
    else:
        payment_status = PurchaseOrder.PaymentStatus.UNPAID

    order.payable_outstanding = payable_outstanding
    order.total_paid          = total_paid
    order.payment_status      = payment_status
    order.save(update_fields=["payable_outstanding", "total_paid", "payment_status"])


def _stock_bucket(quantity: int) -> str:
    """Maps a quantity to its stats bucket: 'out' / 'low' / 'ok'."""
    if quantity <= 0:
        return "out"
    if quantity <= LOW_STOCK_THRESHOLD:
        return "low"
    return "ok"


def _apply_inventory_stats_deltas(*, total_delta: int = 0, low_delta: int = 0, out_delta: int = 0) -> None:
    """
    Adjusts the InventoryStatsFlow singleton with F() expressions so the
    arithmetic happens inside the database — concurrent stock movements can
    never overwrite each other's counter updates.
    """
    if not (total_delta or low_delta or out_delta):
        return
    InventoryStatsFlow.get_instance()  # ensure the singleton row exists
    InventoryStatsFlow.objects.filter(pk=1).update(
        total_products     = F("total_products") + total_delta,
        low_stock_count    = F("low_stock_count") + low_delta,
        out_of_stock_count = F("out_of_stock_count") + out_delta,
        last_updated_at    = timezone.now(),
    )


_BUCKET_FIELD_DELTAS = {
    "out": {"out_delta": 1},
    "low": {"low_delta": 1},
    "ok" : {},
}


def _stats_deltas_for_transition(old_bucket: str | None, new_bucket: str) -> dict:
    """
    Counter deltas for a bucket transition. old_bucket=None means the
    inventory row was just created (also counts toward total_products).
    """
    deltas = {"total_delta": 0, "low_delta": 0, "out_delta": 0}
    if old_bucket == new_bucket:
        return deltas
    if old_bucket is None:
        deltas["total_delta"] = 1
    else:
        for key, value in _BUCKET_FIELD_DELTAS[old_bucket].items():
            deltas[key] -= value
    for key, value in _BUCKET_FIELD_DELTAS[new_bucket].items():
        deltas[key] += value
    return deltas


def sync_inventory(*, product: Product, quantity_delta: int, user=None) -> None:
    """
    THE single writer for Inventory.quantity — purchases AND billing must go
    through here (billing used to write quantity directly, which would let
    the stats counters drift). delta > 0 = increase, delta < 0 = decrease.
    Floored at 0 — inventory never goes negative. user=None leaves
    last_updated_by untouched (matches billing's return path, which never
    recorded a user).

    Also keeps InventoryStatsFlow in sync: when the new quantity crosses a
    low-stock/out-of-stock threshold, the singleton counters are adjusted in
    the same transaction. The row lock makes old_quantity trustworthy under
    concurrency, so a transition is never counted twice.
    """
    with transaction.atomic():
        inventory, created = (
            Inventory.objects.select_for_update().get_or_create(product=product)
        )
        old_bucket = None if created else _stock_bucket(inventory.quantity)

        inventory.quantity = max(0, inventory.quantity + quantity_delta)
        update_fields = ["quantity", "last_updated_at"]
        if user is not None:
            inventory.last_updated_by = user
            update_fields.append("last_updated_by")
        inventory.save(update_fields=update_fields)

        _apply_inventory_stats_deltas(
            **_stats_deltas_for_transition(old_bucket, _stock_bucket(inventory.quantity))
        )


# ---------------------------------------------------------------------------
# Shelf stock (per-location physical quantity) — parallel to Inventory
# ---------------------------------------------------------------------------

def get_default_shelf() -> Shelf:
    """
    The fallback shelf for flows that don't (yet) collect an explicit shelf
    choice: the historical backfill, and data-entry opening stock when no
    shelf is specified. Earliest non-deleted shelf, deterministic. Raises a
    clear error if no shelf exists yet — the admin needs to create at least
    one before any stock-moving action can run.
    """
    from rest_framework.exceptions import ValidationError
    shelf = Shelf.objects.order_by("id").first()
    if shelf is None:
        raise ValidationError({"shelf": "No shelves exist yet. Create at least one shelf first."})
    return shelf


def apply_shelf_delta(*, shelf: Shelf, product: Product, delta: int, reason: str, reference: str = "", user=None) -> None:
    """
    THE single writer for ShelfStock.quantity — every put-away/consumption/
    move funnels through here, mirroring sync_inventory's role for the
    global Inventory total. Locks the (shelf, product) row, floors at 0
    (defensive only — callers must validate availability before calling
    this for a negative delta via validate_shelf_consumption), and appends
    a ShelfStockMovement audit row in the same transaction.
    """
    with transaction.atomic():
        stock, _ = ShelfStock.objects.select_for_update().get_or_create(shelf=shelf, product=product)
        stock.quantity = max(0, stock.quantity + delta)
        stock.save(update_fields=["quantity", "last_updated_at"])
        ShelfStockMovement.objects.create(
            shelf=shelf, product=product, delta=delta,
            reason=reason, reference=reference, created_by=user,
        )


def apply_shelf_allocations(*, product: Product, allocations: list[dict], sign: int, reason: str, reference: str = "", user=None) -> None:
    """
    Applies a list of {"shelf": Shelf, "quantity": int} allocations for one
    product, each multiplied by `sign` (+1 for put-away, -1 for
    consumption). Locks shelves in deterministic (pk) order so two
    transactions touching overlapping shelf sets can never deadlock.

    Batched to a fixed small number of queries regardless of how many
    shelves this product's allocations span (one locking SELECT, one
    bulk_create for new rows, one bulk_update for existing rows, one
    bulk_create for the movement audit rows) instead of the previous
    per-shelf apply_shelf_delta() loop, which cost 3-4 sequential round
    trips PER SHELF — a purchase order with many multi-shelf lines could
    turn one confirm into hundreds of sequential queries. Same end state,
    same audit rows, same lock semantics — just fewer round trips.
    """
    if not allocations:
        return

    delta_by_shelf: dict[int, int] = {}
    shelf_by_id: dict[int, Shelf] = {}
    for allocation in allocations:
        shelf = allocation["shelf"]
        delta_by_shelf[shelf.pk] = delta_by_shelf.get(shelf.pk, 0) + sign * allocation["quantity"]
        shelf_by_id[shelf.pk] = shelf

    shelf_ids = sorted(delta_by_shelf.keys())
    now = timezone.now()

    with transaction.atomic():
        existing = {
            s.shelf_id: s
            for s in ShelfStock.objects.select_for_update()
                .filter(product=product, shelf_id__in=shelf_ids)
                .order_by("shelf_id")
        }
        to_create = []
        to_update = []
        movements = []
        for shelf_id in shelf_ids:
            delta = delta_by_shelf[shelf_id]
            stock = existing.get(shelf_id)
            if stock is None:
                to_create.append(ShelfStock(
                    shelf_id=shelf_id, product=product,
                    quantity=max(0, delta), last_updated_at=now,
                ))
            else:
                stock.quantity = max(0, stock.quantity + delta)
                stock.last_updated_at = now
                to_update.append(stock)
            movements.append(ShelfStockMovement(
                shelf_id=shelf_id, product=product, delta=delta,
                reason=reason, reference=reference, created_by=user,
            ))
        if to_create:
            ShelfStock.objects.bulk_create(to_create)
        if to_update:
            ShelfStock.objects.bulk_update(to_update, ["quantity", "last_updated_at"])
        ShelfStockMovement.objects.bulk_create(movements)


def validate_shelf_consumption(*, product: Product, allocations: list[dict]) -> None:
    """
    Guard for consumption-type allocations (sale, purchase return, lost
    inventory): every selected shelf must currently hold at least the
    requested quantity of this product. Raises a clear per-shelf error
    naming the shortfall so the frontend can prompt the user to also select
    another shelf. Locks the rows it checks (called from within the
    caller's atomic block) so the check is trustworthy at commit time.

    One locking SELECT for every shelf in `allocations` instead of the
    previous per-shelf query loop — same rows locked, same error raised
    for the same shortfall, just one round trip instead of N.
    """
    from rest_framework.exceptions import ValidationError
    if not allocations:
        return

    shelf_by_id = {a["shelf"].pk: a["shelf"] for a in allocations}
    needed_by_id: dict[int, int] = {}
    for a in allocations:
        needed_by_id[a["shelf"].pk] = needed_by_id.get(a["shelf"].pk, 0) + a["quantity"]

    stock_by_shelf = {
        s.shelf_id: s.quantity
        for s in ShelfStock.objects.select_for_update()
            .filter(product=product, shelf_id__in=sorted(needed_by_id.keys()))
            .order_by("shelf_id")
    }
    for shelf_id in sorted(needed_by_id.keys()):
        shelf = shelf_by_id[shelf_id]
        needed = needed_by_id[shelf_id]
        available = stock_by_shelf.get(shelf_id, 0)
        if available < needed:
            raise ValidationError({
                "shelf_allocations": (
                    f"Shelf '{shelf.name}' only has {available} of '{product.name}' "
                    f"available, but {needed} was requested. Select another shelf "
                    f"to cover the remaining {needed - available}."
                )
            })


def _validate_shelf_ids_exist(shelf_ids: list[int]) -> dict[int, Shelf]:
    """
    Existence + not-soft-deleted check for a batch of shelf ids in ONE
    query instead of one get_shelf_by_id() call per id — same 404 behavior
    as get_shelf_by_id (raised the moment any requested id doesn't resolve
    to a live shelf), but O(1) round trips regardless of how many shelves
    were submitted. Returns the fetched shelves keyed by id so callers can
    reuse them instead of re-fetching.
    """
    from django.http import Http404
    ids = set(shelf_ids)
    if not ids:
        return {}
    shelves_by_id = {s.id: s for s in Shelf.objects.filter(pk__in=ids, is_deleted=False)}
    if len(shelves_by_id) != len(ids):
        raise Http404("No Shelf matches the given query.")
    return shelves_by_id


def validate_allocations_complete(*, product_name: str, allocated: int, required: int) -> None:
    """
    Guard used before any confirm/accept step that requires shelf
    allocations to be fully specified: the sum of an item's allocation rows
    must exactly equal its transaction quantity — no more, no less.
    """
    from rest_framework.exceptions import ValidationError
    if allocated != required:
        raise ValidationError({
            "shelf_allocations": (
                f"'{product_name}' has {allocated} of {required} units allocated to "
                f"shelves. Allocate the remaining {required - allocated} before confirming."
                if allocated < required else
                f"'{product_name}' has {allocated} units allocated to shelves but only "
                f"{required} are needed. Remove {allocated - required} units of allocation."
            )
        })


@transaction.atomic
def move_shelf_stock(*, from_shelf_id: int, to_shelf_id: int, product_id: int, quantity: int, user) -> None:
    """
    Moves quantity of a product from one shelf to another. Both shelf rows
    are locked up front in deterministic (pk) order before any write, so a
    concurrent move in the opposite direction can never deadlock.
    """
    from rest_framework.exceptions import ValidationError

    if from_shelf_id == to_shelf_id:
        raise ValidationError({"to_shelf": "Source and destination shelf must be different."})
    if quantity <= 0:
        raise ValidationError({"quantity": "Quantity must be greater than zero."})

    from_shelf = get_shelf_by_id(from_shelf_id)
    to_shelf   = get_shelf_by_id(to_shelf_id)
    product    = get_product_by_id(product_id)

    locked = {
        s.pk: ShelfStock.objects.select_for_update().get_or_create(shelf=s, product=product)[0]
        for s in sorted([from_shelf, to_shelf], key=lambda s: s.pk)
    }
    if locked[from_shelf.pk].quantity < quantity:
        raise ValidationError({
            "quantity": (
                f"Shelf '{from_shelf.name}' only has {locked[from_shelf.pk].quantity} "
                f"of '{product.name}' — cannot move {quantity}."
            )
        })

    reference = f"{from_shelf.name} -> {to_shelf.name}"
    apply_shelf_delta(shelf=from_shelf, product=product, delta=-quantity,
                       reason=ShelfStockMovement.Reason.MOVE_OUT, reference=reference, user=user)
    apply_shelf_delta(shelf=to_shelf, product=product, delta=quantity,
                       reason=ShelfStockMovement.Reason.MOVE_IN, reference=reference, user=user)


# ---------------------------------------------------------------------------
# Category services
# ---------------------------------------------------------------------------

def create_category(*, name: str, description: str = "", user) -> Category:
    return Category.objects.create(name=name, description=description, created_by=user, updated_by=user)


def update_category(*, pk: int, name: str = None, description: str = None, user) -> Category:
    category = get_category_by_id(pk)
    if name is not None:
        category.name = name
    if description is not None:
        category.description = description
    category.updated_by = user
    category.save(update_fields=["name", "description", "updated_by", "updated_at"])
    return category


def delete_category(*, pk: int, user) -> None:
    _soft_delete(get_category_by_id(pk), user)


# ---------------------------------------------------------------------------
# Shelf services
# ---------------------------------------------------------------------------

def create_shelf(*, name: str, description: str = "", user) -> Shelf:
    return Shelf.objects.create(name=name, description=description, created_by=user, updated_by=user)


def update_shelf(*, pk: int, name: str = None, description: str = None, user) -> Shelf:
    shelf = get_shelf_by_id(pk)
    if name is not None:
        shelf.name = name
    if description is not None:
        shelf.description = description
    shelf.updated_by = user
    shelf.save(update_fields=["name", "description", "updated_by", "updated_at"])
    return shelf


@transaction.atomic
def delete_shelf(*, pk: int, user) -> None:
    """
    Blocks deleting a shelf that still holds stock. Locks the shelf's
    ShelfStock rows for the duration of the check+delete (same transaction)
    so a concurrent put-away/move landing on this shelf right after the
    check either blocks until we finish (and then still 400s them, since
    the shelf is already gone) or completes first and is caught by our
    lock — narrows the race window instead of a bare check-then-act.
    """
    from rest_framework.exceptions import ValidationError
    shelf = get_shelf_by_id(pk)
    if ShelfStock.objects.select_for_update().filter(shelf=shelf, quantity__gt=0).exists():
        raise ValidationError({"shelf": "Cannot delete a shelf that still holds stock. Move its stock first."})
    _soft_delete(shelf, user)


# ---------------------------------------------------------------------------
# Supplier services
# ---------------------------------------------------------------------------

def create_supplier(*, name: str, code: str, user) -> Supplier:
    from rest_framework.exceptions import ValidationError
    if Supplier.objects.filter(code__iexact=code, is_deleted=False).exists():
        raise ValidationError({"code": "A supplier with this code already exists."})
    supplier = Supplier.objects.create(name=name, code=code.upper(), created_by=user, updated_by=user)

    # Auto-create empty ledger for this supplier
    from ledger.services import create_ledger_for_supplier
    create_ledger_for_supplier(supplier=supplier)

    return supplier


@transaction.atomic
def update_supplier(*, pk: int, name: str = None, code: str = None, user) -> Supplier:
    from rest_framework.exceptions import ValidationError
    supplier = get_supplier_by_id(pk)
    if code:
        if Supplier.objects.filter(code__iexact=code, is_deleted=False).exclude(pk=pk).exists():
            raise ValidationError({"code": "A supplier with this code already exists."})
        supplier.code = code.upper()
    if name is not None:
        supplier.name = name
    supplier.updated_by = user
    supplier.save(update_fields=["name", "code", "updated_by", "updated_at"])

    # Keep the ledger's name/code snapshot in sync — it's frozen at creation
    # for history, but must track the live supplier while the supplier is
    # still active (found 2026-08-31: renaming/re-coding a supplier left the
    # ledger showing its old name/code, and unreachable by ledger search).
    from ledger.services import sync_ledger_snapshot
    sync_ledger_snapshot(supplier=supplier)

    return supplier


def delete_supplier(*, pk: int, user) -> None:
    _soft_delete(get_supplier_by_id(pk), user)


# ---------------------------------------------------------------------------
# Product services
# ---------------------------------------------------------------------------

@transaction.atomic
def create_product(*, name: str, code: str, category_id: int, user) -> Product:
    get_category_by_id(category_id)
    product = Product.objects.create(
        name=name, code=code, category_id=category_id,
        created_by=user, updated_by=user,
    )
    # A brand-new product has no price yet — queue it for the Rates app.
    # Lazy import: purchases stays unaware rates exists at module load time.
    from rates.services import add_to_unpriced_queue
    add_to_unpriced_queue(product)
    return product


def update_product(
    *, pk: int, name: str = None, code: str = None,
    category_id: int = None, user,
) -> Product:
    product = get_product_by_id(pk)
    if name is not None:
        product.name = name
    if code is not None:
        product.code = code
    if category_id is not None:
        get_category_by_id(category_id)
        product.category_id = category_id
    product.updated_by = user
    product.save(update_fields=["name", "code", "category_id", "updated_by", "updated_at"])
    return product


@transaction.atomic
def delete_product(*, pk: int, user) -> None:
    product = get_product_by_id(pk)
    _soft_delete(product, user)
    # A deleted product no longer belongs in the "needs a price" queue.
    from rates.services import remove_from_unpriced_queue
    remove_from_unpriced_queue(product)
    # Stats count inventory rows of NON-deleted products only (mirrors the
    # inventory list's product__is_deleted=False filter), so a soft-deleted
    # product leaves the totals and its current bucket.
    inventory = Inventory.objects.filter(product=product).first()
    if inventory is not None:
        bucket = _stock_bucket(inventory.quantity)
        _apply_inventory_stats_deltas(
            total_delta=-1,
            low_delta=-1 if bucket == "low" else 0,
            out_delta=-1 if bucket == "out" else 0,
        )


# ---------------------------------------------------------------------------
# PurchaseOrder — draft create / edit / delete
# ---------------------------------------------------------------------------


def _cancel_advance_payment(*, order, user) -> bool:
    """
    Cancels any existing advance SupplierPayment on this order and restores cash.
    Also removes the linked ledger entry and recalculates snapshots.
    Returns True if an advance payment was found and cancelled.
    """
    advance_payment = SupplierPayment.objects.filter(
        order=order,
        note__startswith="Advance payment",
        amount__gt=0,
        is_deleted=False,
    ).first()
    if advance_payment:
        from cash_flow.services import reverse_cash_movement, sync_advance_payment_deleted
        sync_advance_payment_deleted(advance_amount=advance_payment.amount, user=user)

        # Remove ledger entry
        from ledger.services import remove_ledger_entry_for_payment
        remove_ledger_entry_for_payment(supplier_payment=advance_payment)

        advance_payment.is_deleted = True
        advance_payment.deleted_by = user
        advance_payment.deleted_at = timezone.now()
        advance_payment.save(update_fields=["is_deleted", "deleted_by", "deleted_at"])
        reverse_cash_movement(advance_payment)

        from payment_methods.services import reverse_allocations
        reverse_allocations(advance_payment)
        return True
    return False


def _update_advance_payment(
    *, order, old_amount: Decimal, new_amount: Decimal, method_allocations: list, user,
) -> None:
    """
    Updates the advance SupplierPayment record and adjusts cash_in_hand.
    Also updates the ledger entry amount so it stays in sync.

    method_allocations is the user's NEW split for new_amount — always a
    user-driven edit (called only from update_purchase_order_items); the
    caller validates it's present whenever new_amount > 0.
    """
    from ledger.models import SupplierLedgerEntry
    from ledger.services import _recalculate_snapshots_from, _get_year_month

    advance_payment = SupplierPayment.objects.filter(
        order=order,
        note__startswith="Advance payment",
        amount__gt=0,
        is_deleted=False,
    ).first()

    from payment_methods.services import derive_legacy_method_label, record_allocations, refresh_allocations

    if advance_payment:
        # Update payment amount
        advance_payment.amount = new_amount
        advance_payment.method = derive_legacy_method_label(method_allocations) if method_allocations else advance_payment.method
        advance_payment.save(update_fields=["amount", "method"])

        # Keep the drawer event's amount in step (hides it if edited to 0).
        from cash_flow.services import refresh_cash_movement
        refresh_cash_movement(advance_payment)

        if method_allocations:
            refresh_allocations(
                advance_payment, direction="outflow", splits=method_allocations,
                total_amount=new_amount, date=advance_payment.payment_date, user=user,
            )

        # Update linked ledger entry amount
        ledger_entry = SupplierLedgerEntry.objects.filter(
            supplier_payment=advance_payment
        ).first()
        if ledger_entry:
            ledger_entry.debit = new_amount
            ledger_entry.save(update_fields=["debit"])
            # Recalculate snapshots from this entry's month forward — same
            # per-supplier write lock as ledger.services' entry services.
            from ledger.models import SupplierLedger
            ledger = SupplierLedger.objects.select_for_update().get(pk=ledger_entry.ledger_id)
            _recalculate_snapshots_from(ledger, _get_year_month(ledger_entry.date))
    else:
        # No existing advance payment — create one with reference number + ledger entry
        adv_payment = SupplierPayment.objects.create(
            order=order,
            reference_number=_generate_supplier_payment_reference(),
            amount=new_amount,
            method=derive_legacy_method_label(method_allocations),
            payment_date=timezone.localtime(timezone.now()).date(),
            note="Advance payment on draft purchase order creation.",
            created_by=user,
            updated_by=user,
        )
        from ledger.services import add_advance_entry
        add_advance_entry(
            supplier=order.supplier,
            supplier_payment=adv_payment,
            amount=new_amount,
            date=timezone.localtime(timezone.now()).date(),
            user=user,
        )
        from cash_flow.services import record_cash_movement
        record_cash_movement(adv_payment)
        record_allocations(
            adv_payment, direction="outflow", splits=method_allocations,
            total_amount=new_amount, date=adv_payment.payment_date, user=user,
        )

    from cash_flow.services import sync_advance_payment_updated
    sync_advance_payment_updated(old_amount=old_amount, new_amount=new_amount, user=user)


@transaction.atomic
def create_purchase_order(
    *, supplier_id: int, items: list[dict], description: str = "",
    payment_type: str = "after_delivery", advance_amount: Decimal = Decimal("0"),
    method_allocations: list = None, user,
) -> PurchaseOrder:
    """
    Creates a DRAFT PurchaseOrder with line items.
    No inventory or debt effect at this stage.
    If payment_type=advance and advance_amount > 0:
        - advance_amount immediately deducted from cash_in_hand
        - A SupplierPayment record is auto-created for the advance
    """
    from rest_framework.exceptions import ValidationError

    get_supplier_by_id(supplier_id)

    if not items:
        raise ValidationError({"items": "At least one item is required."})

    seen_products = set()
    for item in items:
        if item["product_id"] in seen_products:
            raise ValidationError({"items": f"Duplicate product id {item['product_id']}."})
        seen_products.add(item["product_id"])
        get_product_by_id(item["product_id"])  # validates existence

    # Validate advance_amount
    if payment_type == "after_delivery":
        advance_amount = Decimal("0")
    if advance_amount < 0:
        from rest_framework.exceptions import ValidationError
        raise ValidationError({"advance_amount": "Advance amount cannot be negative."})
    if payment_type == "advance" and advance_amount > 0 and not method_allocations:
        from rest_framework.exceptions import ValidationError
        raise ValidationError({"method_allocations": "At least one method must be selected for the advance payment."})

    order = PurchaseOrder.objects.create(
        order_number=_generate_order_number(),
        supplier_id=supplier_id,
        status=PurchaseOrder.Status.DRAFT,
        description=description,
        payment_type=payment_type,
        advance_amount=advance_amount,
        created_by=user,
        updated_by=user,
    )

    # If advance payment: deduct from cash_in_hand and record in payment history
    if payment_type == "advance" and advance_amount > 0:
        from payment_methods.services import derive_legacy_method_label, record_allocations

        adv_payment = SupplierPayment.objects.create(
            order=order,
            reference_number=_generate_supplier_payment_reference(),
            amount=advance_amount,
            method=derive_legacy_method_label(method_allocations),
            payment_date=timezone.localtime(timezone.now()).date(),
            note="Advance payment on draft purchase order creation.",
            created_by=user,
            updated_by=user,
        )
        from cash_flow.services import record_cash_movement, sync_advance_payment_created
        sync_advance_payment_created(advance_amount=advance_amount, user=user)
        record_cash_movement(adv_payment)
        record_allocations(
            adv_payment, direction="outflow", splits=method_allocations,
            total_amount=advance_amount, date=adv_payment.payment_date, user=user,
        )

        # Ledger entry: advance debit
        from ledger.services import add_advance_entry
        add_advance_entry(
            supplier=order.supplier,
            supplier_payment=adv_payment,
            amount=advance_amount,
            date=timezone.localtime(timezone.now()).date(),
            user=user,
        )

    for item in items:
        PurchaseItem.objects.create(
            order=order,
            product_id=item["product_id"],
            quantity=item["quantity"],
            unit_price=item["unit_price"],
            gst=item.get("gst", 0),
            wht=item.get("wht", 0),
            description=item.get("description", ""),
            created_by=user,
            updated_by=user,
        )

    return order


@transaction.atomic
def update_purchase_order_items(
    *, order_id: int, items: list[dict], description: str = None,
    payment_type: str = None, advance_amount: Decimal = None,
    method_allocations: list = None, user,
) -> PurchaseOrder:
    """
    Replaces all line items on a DRAFT order.
    Confirmed orders cannot be edited.
    payment_type and advance_amount can also be updated while in draft.
    advance_amount changes auto-adjust cash_in_hand.
    """
    from rest_framework.exceptions import ValidationError

    order = get_purchase_order_by_id(order_id)

    if order.status != PurchaseOrder.Status.DRAFT:
        raise ValidationError({"status": "Only draft purchase orders can be edited."})

    if not items:
        raise ValidationError({"items": "At least one item is required."})

    seen_products = set()
    for item in items:
        if item["product_id"] in seen_products:
            raise ValidationError({"items": f"Duplicate product id {item['product_id']}."})
        seen_products.add(item["product_id"])
        get_product_by_id(item["product_id"])

    # Replace all items
    order.items.all().delete()
    for item in items:
        PurchaseItem.objects.create(
            order=order,
            product_id=item["product_id"],
            quantity=item["quantity"],
            unit_price=item["unit_price"],
            gst=item.get("gst", 0),
            wht=item.get("wht", 0),
            description=item.get("description", ""),
            created_by=user,
            updated_by=user,
        )

    if description is not None:
        order.description = description

    # Handle payment_type change
    if payment_type is not None:
        old_payment_type = order.payment_type
        order.payment_type = payment_type
        # If switching from advance to after_delivery — refund advance
        if old_payment_type == "advance" and payment_type == "after_delivery":
            old_advance = order.advance_amount
            if old_advance > 0:
                _cancel_advance_payment(order=order, user=user)
                order.advance_amount = Decimal("0")

    # Handle advance_amount change
    if advance_amount is not None and order.payment_type == "advance":
        if advance_amount < 0:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"advance_amount": "Advance amount cannot be negative."})
        old_advance = order.advance_amount
        if advance_amount != old_advance:
            if advance_amount > 0 and not method_allocations:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({"method_allocations": "At least one method must be selected for the advance payment."})
            _update_advance_payment(
                order=order, old_amount=old_advance, new_amount=advance_amount,
                method_allocations=method_allocations, user=user,
            )
            order.advance_amount = advance_amount

    order.updated_by = user
    order.save(update_fields=["description", "payment_type", "advance_amount", "updated_by", "updated_at"])
    return order


@transaction.atomic
def set_purchase_item_shelf_allocations(*, purchase_item_id: int, allocations: list[dict], user) -> PurchaseItem:
    """
    Replaces all shelf put-away allocations for one draft purchase item.
    allocations = [{"shelf_id": 1, "quantity": 20}, ...]. Any shelf is valid
    (put-away) — no stock check here, this is purely draft planning state
    applied to ShelfStock only at confirm_purchase_order time. Duplicate
    shelf_id entries in the input are merged so a double submission doesn't
    hit the unique constraint.
    """
    from rest_framework.exceptions import ValidationError

    purchase_item = get_purchase_item_by_id(purchase_item_id)
    if purchase_item.order.status != PurchaseOrder.Status.DRAFT:
        raise ValidationError({"status": "Shelf allocations can only be edited on a draft purchase order."})

    _validate_shelf_ids_exist([a["shelf_id"] for a in allocations])
    merged = {}
    for a in allocations:
        merged[a["shelf_id"]] = merged.get(a["shelf_id"], 0) + a["quantity"]

    total_allocated = sum(merged.values())
    if total_allocated > purchase_item.quantity:
        raise ValidationError({
            "shelf_allocations": (
                f"Allocated quantity ({total_allocated}) exceeds the purchased "
                f"quantity ({purchase_item.quantity})."
            )
        })

    purchase_item.shelf_allocations.all().delete()
    PurchaseItemShelfAllocation.objects.bulk_create([
        PurchaseItemShelfAllocation(purchase_item=purchase_item, shelf_id=shelf_id, quantity=qty)
        for shelf_id, qty in merged.items() if qty > 0
    ])
    return purchase_item


@transaction.atomic
def set_purchase_return_item_shelf_allocations(*, return_item_id: int, allocations: list[dict], user) -> PurchaseReturnItem:
    """
    Replaces all shelf consumption allocations for one pending purchase
    return item — which shelf(s) the returned-to-supplier stock is
    physically pulled from. Each shelf must currently hold enough stock of
    this product; accept_purchase_return re-validates at commit time.
    """
    from rest_framework.exceptions import ValidationError
    from .selectors import get_purchase_return_item_by_id

    return_item = get_purchase_return_item_by_id(return_item_id)
    if return_item.return_record.status != PurchaseReturn.Status.PENDING:
        raise ValidationError({"status": "Shelf allocations can only be edited on a pending return."})

    product = return_item.purchase_item.product
    shelves_by_id = _validate_shelf_ids_exist([a["shelf_id"] for a in allocations])
    merged = {}
    for a in allocations:
        merged[a["shelf_id"]] = merged.get(a["shelf_id"], 0) + a["quantity"]

    total_allocated = sum(merged.values())
    if total_allocated > return_item.quantity:
        raise ValidationError({
            "shelf_allocations": (
                f"Allocated quantity ({total_allocated}) exceeds the return "
                f"quantity ({return_item.quantity})."
            )
        })

    validate_shelf_consumption(product=product, allocations=[
        {"shelf": shelves_by_id[shelf_id], "quantity": qty}
        for shelf_id, qty in merged.items() if qty > 0
    ])

    return_item.shelf_allocations.all().delete()
    PurchaseReturnItemShelfAllocation.objects.bulk_create([
        PurchaseReturnItemShelfAllocation(return_item=return_item, shelf_id=shelf_id, quantity=qty)
        for shelf_id, qty in merged.items() if qty > 0
    ])
    return return_item


@transaction.atomic
def delete_purchase_order(*, order_id: int, user) -> None:
    """
    Only DRAFT orders can be deleted. Refunds advance payment if applicable.

    The refund goes through _cancel_advance_payment, which restores the cash
    AND soft-deletes the advance SupplierPayment row + its ledger entry +
    its drawer event — previously the cash was restored but the payment row
    stayed alive forever, leaving a phantom outflow in the cash-in-hand
    drawer and a phantom debit in the supplier ledger for an order that no
    longer exists (fix approved 2026-08-03).
    """
    from rest_framework.exceptions import ValidationError
    order = get_purchase_order_by_id(order_id)
    if order.status != PurchaseOrder.Status.DRAFT:
        raise ValidationError({"status": "Only draft purchase orders can be deleted."})

    # Refund advance if this was an advance order
    if order.payment_type == "advance" and order.advance_amount > 0:
        if not _cancel_advance_payment(order=order, user=user):
            # Advance payment row already deleted directly (its deletion
            # deliberately does NOT restore cash for advances) — restore the
            # cash here exactly as before.
            from cash_flow.services import sync_advance_payment_deleted
            sync_advance_payment_deleted(advance_amount=order.advance_amount, user=user)

    _soft_delete(order, user)


# ---------------------------------------------------------------------------
# PurchaseOrder — confirm
# ---------------------------------------------------------------------------

@transaction.atomic
def confirm_purchase_order(*, order_id: int, user) -> PurchaseOrder:
    """
    Confirms a DRAFT PurchaseOrder:
    1. Every item must already be fully allocated to shelves (put-away plan)
    2. Recalculates all totals from line items
    3. Sets remaining_quantity = quantity on each item (FIFO ready)
    4. Adds to inventory (global) AND to ShelfStock per the item's allocations
    5. Sets payable_outstanding = net_payable (we owe supplier full amount)
    6. Sets status = CONFIRMED
    """
    from rest_framework.exceptions import ValidationError

    order = get_purchase_order_by_id(order_id)
    if order.status != PurchaseOrder.Status.DRAFT:
        raise ValidationError({"status": "Only draft purchase orders can be confirmed."})

    # order.items.all() reuses the selector's prefetch cache (already
    # filtered to live items via SoftDeleteManager, with shelf_allocations
    # nested-prefetched) — a fresh .filter() here would discard that cache
    # and re-query per order (architecture.md rule 20). Sorted by product_id
    # (mirrors confirm_invoice) so two concurrent confirms touching
    # overlapping shelves always lock in the same order — no deadlock.
    items = sorted(order.items.all(), key=lambda i: i.product_id)
    if not items:
        raise ValidationError({"items": "Cannot confirm an order with no items."})

    # Every item must be fully put away before we touch stock — a purchase
    # order confirms exactly once, so this is the only allocation gate.
    for item in items:
        validate_allocations_complete(
            product_name=item.product.name,
            allocated=item.allocated_quantity,
            required=item.quantity,
        )

    # Set remaining_quantity and sync inventory
    for item in items:
        item.remaining_quantity = item.quantity
        item.save(update_fields=["remaining_quantity"])
        sync_inventory(product=item.product, quantity_delta=item.quantity, user=user)
        apply_shelf_allocations(
            product=item.product,
            allocations=[{"shelf": a.shelf, "quantity": a.quantity} for a in item.shelf_allocations.all()],
            sign=1, reason=ShelfStockMovement.Reason.PURCHASE_PUTAWAY,
            reference=order.order_number, user=user,
        )
        # Stock Movement Report — bootstrap opening-stock orders aren't
        # real operating-period purchases, mirrors every other report's
        # is_data_entry exclusion.
        if not order.is_data_entry:
            _adjust_stock_movement(product_id=item.product_id, purchased_delta=item.quantity)

    _recalculate_order_totals(order)

    order.status       = PurchaseOrder.Status.CONFIRMED
    order.confirmed_by = user
    order.confirmed_at = timezone.now()
    order.updated_by   = user
    order.save(update_fields=["status", "confirmed_by", "confirmed_at", "updated_by", "updated_at"])

    # Reload fresh net_payable
    order.refresh_from_db(fields=["net_payable", "advance_amount", "payment_type"])
    advance = order.advance_amount if order.payment_type == "advance" else Decimal("0")

    # Cap advance at net_payable (safety guard)
    if advance > order.net_payable:
        advance = order.net_payable
        order.advance_amount = advance
        order.save(update_fields=["advance_amount"])

    remaining_payable = max(Decimal("0"), order.net_payable - advance)
    order.payable_outstanding = remaining_payable
    order.payment_status = (
        PurchaseOrder.PaymentStatus.PAID if remaining_payable == 0
        else PurchaseOrder.PaymentStatus.PARTIAL if advance > 0
        else PurchaseOrder.PaymentStatus.UNPAID
    )
    order.save(update_fields=["payable_outstanding", "payment_status"])

    # Sync CashFlow: outstanding = net_payable - advance (advance already in cash)
    from cash_flow.services import sync_purchase_order_confirmed
    sync_purchase_order_confirmed(net_payable=order.net_payable, advance_amount=advance, user=user)

    # Sync TaxFlow: GST paid to supplier + WHT withheld from supplier
    from taxes.services import sync_purchase_tax
    sync_purchase_tax(gst_amount=order.gst_total, wht_amount=order.wht_total, user=user)

    # Ledger entry: credit (we owe supplier net_payable)
    from ledger.services import add_purchase_entry
    add_purchase_entry(
        supplier=order.supplier,
        purchase_order=order,
        amount=order.net_payable,
        date=timezone.localtime(order.confirmed_at).date(),
        user=user,
    )

    return order


# ---------------------------------------------------------------------------
# Data-entry bootstrap orders (called from data_entry.services)
# ---------------------------------------------------------------------------

@transaction.atomic
def create_opening_balance_order(*, supplier, amount: Decimal, user) -> PurchaseOrder:
    """
    Creates a CONFIRMED, is_data_entry PurchaseOrder with no line items,
    net_payable = payable_outstanding = amount. Exists so normal supplier
    payment APIs can work against the opening balance. No inventory/ledger/
    cashflow here — the caller orchestrates those.
    """
    return PurchaseOrder.objects.create(
        order_number        = _generate_order_number(),
        supplier            = supplier,
        status              = PurchaseOrder.Status.CONFIRMED,
        is_data_entry       = True,
        description         = "Opening balance (data entry).",
        gross_amount        = amount,
        net_payable         = amount,
        payable_outstanding = amount,
        payment_status      = PurchaseOrder.PaymentStatus.UNPAID,
        confirmed_by        = user,
        confirmed_at        = timezone.now(),
        created_by          = user,
        updated_by          = user,
    )


@transaction.atomic
def create_opening_stock_order(*, supplier, items: list[dict], user) -> PurchaseOrder:
    """
    Creates a CONFIRMED, is_data_entry PurchaseOrder with line items for the
    system supplier. Sets remaining_quantity for FIFO and adds to inventory
    AND to the shelf the user picked for each item (shelf_id is required per
    item — data-entry opening stock is a real put-away action, not exempt
    from choosing a shelf like every other stock-adding flow). No
    cashflow/ledger effect (system supplier is excluded from payable tracking).
    """
    from rest_framework.exceptions import ValidationError

    for item in items:
        if not item.get("shelf_id"):
            raise ValidationError({"shelf_id": "A shelf is required for every opening stock item."})

    order = PurchaseOrder.objects.create(
        order_number  = _generate_order_number(),
        supplier      = supplier,
        status        = PurchaseOrder.Status.CONFIRMED,
        is_data_entry = True,
        description   = "Opening stock (data entry).",
        confirmed_by  = user,
        confirmed_at  = timezone.now(),
        created_by    = user,
        updated_by    = user,
    )
    for item in items:
        shelf = get_shelf_by_id(item["shelf_id"])
        pi = PurchaseItem.objects.create(
            order=order,
            product_id=item["product_id"],
            quantity=item["quantity"],
            unit_price=item["unit_price"],
            gst=item.get("gst", 0),
            wht=item.get("wht", 0),
            description=item.get("description", ""),
            created_by=user,
            updated_by=user,
        )  # .save() auto-computes gross/gst/wht/total
        pi.remaining_quantity = pi.quantity
        pi.save(update_fields=["remaining_quantity"])
        sync_inventory(product=pi.product, quantity_delta=pi.quantity, user=user)
        apply_shelf_delta(
            shelf=shelf, product=pi.product, delta=pi.quantity,
            reason=ShelfStockMovement.Reason.PURCHASE_PUTAWAY,
            reference=order.order_number, user=user,
        )
        # Stock Movement Report — unlike the financial is_data_entry
        # exclusions elsewhere, opening stock DOES move real physical
        # quantity (Inventory.quantity is incremented above too), so it
        # counts as "purchased" here on purpose.
        _adjust_stock_movement(product_id=pi.product_id, purchased_delta=pi.quantity)

    _recalculate_order_totals(order)
    return order


# ---------------------------------------------------------------------------
# Supplier Payment services
# ---------------------------------------------------------------------------

@transaction.atomic
def create_supplier_payment(
    *, order_id: int, amount: Decimal, method_allocations: list,
    payment_date, note: str = "", user,
) -> SupplierPayment:
    from rest_framework.exceptions import ValidationError

    order = get_purchase_order_by_id(order_id)
    if order.status == PurchaseOrder.Status.DRAFT:
        raise ValidationError({"order": "Cannot record payment on a draft purchase order."})

    order.refresh_from_db(fields=["payable_outstanding"])
    if amount > order.payable_outstanding:
        raise ValidationError({
            "amount": (
                f"Payment of {amount} exceeds outstanding payable. "
                f"Outstanding: {order.payable_outstanding}."
            )
        })

    from payment_methods.services import derive_legacy_method_label, record_allocations

    payment = SupplierPayment.objects.create(
        order=order,
        reference_number=_generate_supplier_payment_reference(),
        amount=amount,
        method=derive_legacy_method_label(method_allocations),
        payment_date=payment_date,
        note=note,
        created_by=user,
        updated_by=user,
    )
    _sync_order_payable(order)

    # Sync CashFlow: cash out, payable reduces, paid increases
    from cash_flow.services import record_cash_movement, sync_supplier_payment_made
    sync_supplier_payment_made(amount=amount, user=user)
    record_cash_movement(payment)
    # This is a REAL balance check, not the record_cash_movement no-op it
    # sits next to — if the chosen outflow method(s) can't cover the split,
    # this raises and the whole @transaction.atomic call rolls back
    # (including the SupplierPayment row and the _sync_order_payable above).
    record_allocations(
        payment, direction="outflow", splits=method_allocations,
        total_amount=amount, date=payment_date, user=user,
    )

    # Ledger entry: debit (we paid supplier)
    from ledger.services import add_payment_entry
    add_payment_entry(
        supplier=order.supplier,
        supplier_payment=payment,
        amount=amount,
        date=payment_date,
        user=user,
    )

    return payment


@transaction.atomic
def delete_supplier_payment(*, payment_id: int, user) -> None:
    payment = get_supplier_payment_by_id(payment_id)
    order   = payment.order
    amount  = payment.amount
    _soft_delete(payment, user)
    _sync_order_payable(order)

    # Reverse CashFlow sync only for positive non-advance payments
    if amount > 0 and not payment.note.startswith("Advance payment"):
        from cash_flow.services import sync_supplier_payment_deleted
        sync_supplier_payment_deleted(amount=amount, user=user)

    # The drawer hides ANY soft-deleted payment row (advance or not), so the
    # event is reversed unconditionally — mirroring row visibility, not cash.
    from cash_flow.services import reverse_cash_movement
    reverse_cash_movement(payment)

    from payment_methods.services import reverse_allocations
    reverse_allocations(payment)

    # Reverse ledger entry — mirrors billing.services.delete_payment. Without
    # this, a deleted supplier payment kept its debit entry (and baked-in
    # snapshot balance) alive forever, showing as a still-outstanding
    # payment on the supplier ledger (found 2026-08-31, SPY-2026-0013).
    from ledger.services import remove_ledger_entry_for_payment
    remove_ledger_entry_for_payment(supplier_payment=payment)


# ---------------------------------------------------------------------------
# Purchase Return services
# ---------------------------------------------------------------------------

@transaction.atomic
def create_purchase_return(
    *, order_id: int, items: list[dict], note: str = "", user,
) -> PurchaseReturn:
    """
    Creates a PENDING return to supplier.
    items = [{"purchase_item_id": 1, "quantity": 5, "gst": 0, "wht": 0}, ...]
    Previous PurchaseOrder and PurchaseItems are untouched.
    No inventory or debt change yet — happens on acceptance.
    """
    from rest_framework.exceptions import ValidationError

    order = get_purchase_order_by_id(order_id)
    if order.status != PurchaseOrder.Status.CONFIRMED:
        raise ValidationError({"order": "Can only return items from confirmed purchase orders."})

    if not items:
        raise ValidationError({"items": "At least one item is required."})

    return_record = PurchaseReturn.objects.create(
        order=order,
        reference_number=_generate_purchase_return_reference(),
        status=PurchaseReturn.Status.PENDING,
        note=note,
        created_by=user,
        updated_by=user,
    )

    for item_data in items:
        purchase_item = get_purchase_item_by_id(item_data["purchase_item_id"])

        if purchase_item.order_id != order.id:
            raise ValidationError({
                "purchase_item_id": f"Item {purchase_item.id} does not belong to this order."
            })
        if item_data["quantity"] > purchase_item.returnable_quantity:
            raise ValidationError({
                "quantity": (
                    f"Cannot return {item_data['quantity']} units of "
                    f"'{purchase_item.product.name}'. "
                    f"Returnable: {purchase_item.returnable_quantity}."
                )
            })

        PurchaseReturnItem.objects.create(
            return_record=return_record,
            purchase_item=purchase_item,
            quantity=item_data["quantity"],
            gst=item_data.get("gst", 0),
            wht=item_data.get("wht", 0),
        )

    return return_record


@transaction.atomic
def update_purchase_return_items(*, return_id: int, items: list[dict], note: str = None, user) -> PurchaseReturn:
    """
    Replaces all line items on a PENDING return. Mirrors
    update_purchase_order_items: old PurchaseReturnItem rows are deleted
    (cascading their shelf_allocations, since those are keyed to the
    specific item row) and new ones are created from scratch — the user
    re-allocates shelves for the new lines afterward, same as when a
    return is first created. A return has no side effects until accepted,
    so there's nothing to reverse here.
    """
    from rest_framework.exceptions import ValidationError

    return_record = get_purchase_return_by_id(return_id)
    if return_record.status != PurchaseReturn.Status.PENDING:
        raise ValidationError({"status": "Only pending returns can be edited."})

    if not items:
        raise ValidationError({"items": "At least one item is required."})

    return_record.items.all().delete()
    for item_data in items:
        purchase_item = get_purchase_item_by_id(item_data["purchase_item_id"])

        if purchase_item.order_id != return_record.order_id:
            raise ValidationError({
                "purchase_item_id": f"Item {purchase_item.id} does not belong to this order."
            })
        if item_data["quantity"] > purchase_item.returnable_quantity:
            raise ValidationError({
                "quantity": (
                    f"Cannot return {item_data['quantity']} units of "
                    f"'{purchase_item.product.name}'. "
                    f"Returnable: {purchase_item.returnable_quantity}."
                )
            })

        PurchaseReturnItem.objects.create(
            return_record=return_record,
            purchase_item=purchase_item,
            quantity=item_data["quantity"],
            gst=item_data.get("gst", 0),
            wht=item_data.get("wht", 0),
        )

    if note is not None:
        return_record.note = note
    return_record.updated_by = user
    return_record.save(update_fields=["note", "updated_by", "updated_at"])
    return return_record


def cancel_purchase_return(*, return_id: int, user) -> None:
    """
    Cancels a PENDING return — soft delete, same as delete_purchase_order.
    A return has no side effects until accepted (no inventory/payable/FIFO
    change happens at creation), so there's nothing to reverse: cancelling
    is purely "this never happened." The order and its items are
    untouched, and the user is free to create another return against the
    same order afterward (returnable_quantity is computed from
    returned_quantity, which a pending-then-cancelled return never
    incremented).
    """
    from rest_framework.exceptions import ValidationError

    return_record = get_purchase_return_by_id(return_id)
    if return_record.status != PurchaseReturn.Status.PENDING:
        raise ValidationError({"status": "Only pending returns can be cancelled."})

    _soft_delete(return_record, user)


@transaction.atomic
def accept_purchase_return(*, return_id: int, user) -> PurchaseReturn:
    """
    Accepts a pending return:
    1. Snapshots unit_price from original purchase item
    2. Calculates return amounts using calculate_total_price (with return GST/WHT)
    3. Decreases remaining_quantity on purchase items (FIFO reversal)
    4. Decreases inventory
    5. Updates returned_quantity on purchase items
    6. Creates negative SupplierPayment entry (credit note — reduces our debt)
    7. Resyncs order payable
    """
    from rest_framework.exceptions import ValidationError

    return_record = get_purchase_return_by_id(return_id)
    if return_record.status != PurchaseReturn.Status.PENDING:
        raise ValidationError({"status": "Only pending returns can be accepted."})

    # Sorted by product_id (mirrors confirm_invoice) so two concurrent
    # accepts touching overlapping shelves always lock in the same order.
    return_items = sorted(return_record.items.all(), key=lambda ri: ri.purchase_item.product_id)

    # Every item must be fully allocated to shelves (which shelf the
    # returned-to-supplier stock is physically pulled from) before we touch
    # stock, and each selected shelf must actually hold enough right now.
    for return_item in return_items:
        product = return_item.purchase_item.product
        validate_allocations_complete(
            product_name=product.name,
            allocated=return_item.allocated_quantity,
            required=return_item.quantity,
        )
        validate_shelf_consumption(
            product=product,
            allocations=[{"shelf": a.shelf, "quantity": a.quantity} for a in return_item.shelf_allocations.all()],
        )

    total_gross  = Decimal("0")
    total_gst    = Decimal("0")
    total_wht    = Decimal("0")
    total_amount = Decimal("0")

    for return_item in return_items:
        purchase_item = return_item.purchase_item
        qty           = return_item.quantity

        # Snapshot unit_price from original purchase item
        unit_price = purchase_item.unit_price

        # Calculate return financials using same formula as purchases
        calc = calculate_total_price(
            quantity=qty,
            unit_price=unit_price,
            gst=return_item.gst,
            wht=return_item.wht,
        )

        return_item.unit_price   = unit_price
        return_item.gross_amount = calc["gross_amount"]
        return_item.gst_amount   = calc["gst_amount"]
        return_item.wht_amount   = calc["wht_amount"]
        return_item.total_amount = calc["total_price"]
        return_item.save(update_fields=[
            "unit_price", "gross_amount", "gst_amount", "wht_amount", "total_amount"
        ])

        # Returning to the supplier permanently removes this batch's stock —
        # remaining_quantity decreases in the SAME direction as the
        # Inventory decrease below (a prior version of this code instead
        # INCREASED remaining_quantity here, silently diverging it from
        # Inventory.quantity and inflating this product's FIFO-cost
        # valuation on every accepted return — fixed 2026-08-09).
        #
        # select_for_update: remaining_quantity is read-then-written, so
        # this row must be locked against concurrent FIFO consumers
        # (sales/losses). PurchaseItem has unique_together=(order, product),
        # so there is exactly one batch per order+product — no multi-batch
        # walk needed here, unlike billing's _reverse_fifo which spans
        # however many batches an invoice item's sale originally consumed.
        locked_item = PurchaseItem.objects.select_for_update().get(pk=purchase_item.pk)
        if qty > locked_item.remaining_quantity:
            raise ValidationError({
                "quantity": (
                    f"Cannot return {qty} units of '{purchase_item.product.name}' — only "
                    f"{locked_item.remaining_quantity} are currently in stock (some may have "
                    f"been sold or marked lost since this return was created)."
                )
            })
        locked_item.remaining_quantity -= qty
        locked_item.returned_quantity = purchase_item.returned_quantity + qty
        locked_item.save(update_fields=["remaining_quantity", "returned_quantity"])

        # Decrease inventory (global) and the specific shelf(s) it's pulled from
        sync_inventory(product=purchase_item.product, quantity_delta=-qty, user=user)
        apply_shelf_allocations(
            product=purchase_item.product,
            allocations=[{"shelf": a.shelf, "quantity": a.quantity} for a in return_item.shelf_allocations.all()],
            sign=-1, reason=ShelfStockMovement.Reason.PURCHASE_RETURN_CONSUMPTION,
            reference=return_record.reference_number, user=user,
        )

        # Stock Movement Report
        if not purchase_item.order.is_data_entry:
            _adjust_stock_movement(product_id=purchase_item.product_id, purchase_returned_delta=qty)

        total_gross  += calc["gross_amount"]
        total_gst    += calc["gst_amount"]
        total_wht    += calc["wht_amount"]
        total_amount += calc["total_price"]

    # Save return totals
    return_record.total_return_gross  = total_gross
    return_record.total_return_gst    = total_gst
    return_record.total_return_wht    = total_wht
    return_record.total_return_amount = total_amount
    return_record.status      = PurchaseReturn.Status.ACCEPTED
    return_record.accepted_by = user
    return_record.accepted_at = timezone.now()
    return_record.updated_by  = user
    return_record.save(update_fields=[
        "total_return_gross", "total_return_gst", "total_return_wht",
        "total_return_amount", "status", "accepted_by", "accepted_at", "updated_by", "updated_at",
    ])

    # Credit note: negative payment reduces our payable to supplier
    order = return_record.order
    SupplierPayment.objects.create(
        order=order,
        reference_number=_generate_supplier_payment_reference(),
        amount=-total_amount,
        method=SupplierPayment.Method.CASH,
        payment_date=timezone.localtime(timezone.now()).date(),
        note=f"Auto credit note for Return #{return_record.reference_number}",
        created_by=user,
        updated_by=user,
    )
    _sync_order_payable(order)

    # Sync CashFlow: payable_outstanding reduces, total_purchase_returns_value/cogs increase
    from cash_flow.services import sync_purchase_return_accepted
    sync_purchase_return_accepted(return_amount=total_amount, return_cogs=total_gross, user=user)

    # Ledger entry: return debit (supplier owes us back)
    from ledger.services import add_return_entry
    add_return_entry(
        supplier=return_record.order.supplier,
        purchase_return=return_record,
        amount=total_amount,
        date=timezone.localtime(return_record.accepted_at).date(),
        user=user,
    )

    return return_record


# ---------------------------------------------------------------------------
# Lost Inventory
# ---------------------------------------------------------------------------

def _consume_fifo_for_loss(*, product: Product, quantity: int) -> tuple[Decimal, list[dict]]:
    """
    Consumes stock from purchase batches in FIFO order for a lost product.
    Mirrors billing._run_fifo — oldest batch first, tax-inclusive unit cost
    (total_price / quantity), decrements remaining_quantity on each batch.

    Returns (blended_unit_cost, consumptions) — consumptions is one dict per
    batch actually touched: {"purchase_item", "quantity", "unit_cost"}. The
    caller persists these as LostInventoryFIFOConsumption rows so a later
    "mark as found" can restore the EXACT original batches instead of an
    approximation.
    """
    from rest_framework.exceptions import ValidationError

    remaining_to_consume = quantity
    total_cost = Decimal("0")
    consumptions = []
    # for_update: this path decrements remaining_quantity — the batch rows
    # must be locked so a concurrent invoice confirm can't consume the same
    # units (runs inside create_lost_inventory_record's transaction).
    batches = get_available_purchase_items_for_fifo(product.id, for_update=True)

    for batch in batches:
        if remaining_to_consume <= 0:
            break

        consume = min(batch.remaining_quantity, remaining_to_consume)
        tax_inclusive_unit_cost = (
            batch.total_price / batch.quantity
            if batch.quantity > 0 else batch.unit_price
        )
        total_cost += consume * tax_inclusive_unit_cost

        batch.remaining_quantity -= consume
        batch.save(update_fields=["remaining_quantity"])

        consumptions.append({
            "purchase_item": batch,
            "quantity": consume,
            "unit_cost": tax_inclusive_unit_cost,
        })

        remaining_to_consume -= consume

    if remaining_to_consume > 0:
        raise ValidationError({
            "quantity": f"Stock ran out mid-processing for '{product.name}'. Please refresh and try again."
        })

    return total_cost / Decimal(str(quantity)), consumptions


def _validate_lost_stock(*, product: Product, requested_qty: int) -> None:
    """Guard: ensures enough FIFO stock exists before consuming it. Mirrors billing._validate_stock."""
    from rest_framework.exceptions import ValidationError

    # Single aggregate instead of loading every batch row to sum in Python
    # (mirrors billing's _validate_stock). Deliberately unlocked — it's a
    # pre-check; the locked walk in _consume_fifo_for_loss has its own
    # ran-out guard for the race.
    available = (
        get_available_purchase_items_for_fifo(product.id)
        .aggregate(total=Sum("remaining_quantity"))["total"] or 0
    )
    if available < requested_qty:
        raise ValidationError({
            "quantity": (
                f"Insufficient stock for '{product.name}'. "
                f"Requested: {requested_qty}, Available: {available}."
            )
        })


@transaction.atomic
def create_lost_inventory_record(*, items: list[dict], note: str = "", user) -> LostInventoryRecord:
    """
    Marks one or more products as lost from inventory in a single batch.
    items = [{"product_id": 1, "quantity": 5, "reason": "damaged",
               "shelf_allocations": [{"shelf_id": 2, "quantity": 5}]}, ...]

    There's no draft/pending step here (unlike purchase orders/invoices),
    so shelf_allocations are supplied and validated inline in the same call
    rather than as separate persisted draft rows — each item's allocations
    must sum exactly to its quantity, and each named shelf must currently
    hold enough of that product.

    For each item:
        1. Validates stock availability against FIFO purchase batches.
        2. Consumes stock FIFO-first, snapshotting the blended unit cost.
        3. Decreases live inventory by the lost quantity, and the specific
           shelf(s) it's pulled from.
    Takes effect immediately — no pending/accept step.
    """
    from rest_framework.exceptions import ValidationError

    if not items:
        raise ValidationError({"items": "At least one item is required."})

    seen_products = set()
    for item in items:
        if item["product_id"] in seen_products:
            raise ValidationError({"items": f"Duplicate product id {item['product_id']}."})
        seen_products.add(item["product_id"])
        if item["quantity"] <= 0:
            raise ValidationError({"quantity": "Quantity must be greater than zero."})

    record = LostInventoryRecord.objects.create(
        reference_number=_generate_lost_inventory_reference(),
        note=note,
        created_by=user,
        updated_by=user,
    )

    total_lost_amount = Decimal("0")

    # Sorted by product_id (mirrors confirm_invoice) so two concurrent lost-
    # inventory creates touching overlapping shelves always lock in the same
    # order — the item order here is entirely client-controlled otherwise.
    for item_data in sorted(items, key=lambda i: i["product_id"]):
        product = get_product_by_id(item_data["product_id"])
        quantity = item_data["quantity"]

        shelf_allocations = [
            {"shelf": get_shelf_by_id(a["shelf_id"]), "quantity": a["quantity"]}
            for a in item_data.get("shelf_allocations", [])
        ]
        validate_allocations_complete(
            product_name=product.name,
            allocated=sum(a["quantity"] for a in shelf_allocations),
            required=quantity,
        )
        validate_shelf_consumption(product=product, allocations=shelf_allocations)

        _validate_lost_stock(product=product, requested_qty=quantity)
        unit_cost, consumptions = _consume_fifo_for_loss(product=product, quantity=quantity)
        total_cost = unit_cost * Decimal(str(quantity))

        lost_item = LostInventoryItem.objects.create(
            record=record,
            product=product,
            quantity=quantity,
            reason=item_data.get("reason", ""),
            unit_cost=unit_cost,
            total_cost=total_cost,
        )

        LostInventoryFIFOConsumption.objects.bulk_create([
            LostInventoryFIFOConsumption(
                lost_item=lost_item,
                purchase_item=c["purchase_item"],
                quantity=c["quantity"],
                unit_cost=c["unit_cost"],
            )
            for c in consumptions
        ])

        sync_inventory(product=product, quantity_delta=-quantity, user=user)
        apply_shelf_allocations(
            product=product, allocations=shelf_allocations, sign=-1,
            reason=ShelfStockMovement.Reason.LOST_CONSUMPTION,
            reference=record.reference_number, user=user,
        )

        # Stock Movement Report
        _adjust_stock_movement(product_id=product.id, lost_delta=quantity)

        total_lost_amount += total_cost

    record.total_lost_amount = total_lost_amount
    record.save(update_fields=["total_lost_amount"])

    # Sync CashFlow: total_lost_inventory_worth increases by this batch's FIFO cost
    from cash_flow.services import sync_lost_inventory_created
    sync_lost_inventory_created(amount=total_lost_amount, user=user)

    return record


@transaction.atomic
def mark_lost_inventory_found(*, lost_item_id: int, quantity: int, shelf_allocations: list[dict] = None, user) -> LostInventoryItem:
    """
    Reverses part or all of a previously lost item: restores stock to the
    EXACT original purchase batch(es) it was consumed from (via the
    LostInventoryFIFOConsumption ledger), increases live Inventory, puts the
    found quantity away on the caller-chosen shelf(s) (any shelf — this is
    put-away, not consumption), and increases
    CashFlow.total_lost_inventory_recovered (net figure shown on dashboard =
    total_lost_inventory_worth - total_lost_inventory_recovered).

    Restoration order: oldest consumption row first (mirrors FIFO intent —
    the batch it left first is the batch it's credited back to first).

    Legacy fallback: lost items created before this feature has no ledger
    rows. For those, restored stock is added directly to Inventory without
    a batch to credit back to (no FIFO consumption to reverse).
    """
    from rest_framework.exceptions import ValidationError

    if quantity <= 0:
        raise ValidationError({"quantity": "Quantity must be greater than zero."})

    lost_item = get_lost_inventory_item_by_id(lost_item_id)

    resolved_allocations = [
        {"shelf": get_shelf_by_id(a["shelf_id"]), "quantity": a["quantity"]}
        for a in (shelf_allocations or [])
    ]
    validate_allocations_complete(
        product_name=lost_item.product.name,
        allocated=sum(a["quantity"] for a in resolved_allocations),
        required=quantity,
    )

    if quantity > lost_item.returnable_quantity:
        raise ValidationError({
            "quantity": (
                f"Cannot mark {quantity} as found — only "
                f"{lost_item.returnable_quantity} of this lost item is returnable."
            )
        })

    # select_for_update locks both the consumption rows and (via the join)
    # their purchase batches — restored_quantity and remaining_quantity are
    # read-then-written here, so concurrent "mark found" calls or FIFO
    # consumers must queue. Inside mark_lost_inventory_found's transaction.
    consumptions = list(
        lost_item.fifo_consumptions.select_related("purchase_item")
        .select_for_update().order_by("id")
    )

    remaining_to_restore = quantity
    if consumptions:
        for consumption in consumptions:
            if remaining_to_restore <= 0:
                break

            restorable = consumption.restorable_quantity
            if restorable <= 0:
                continue

            restore = min(restorable, remaining_to_restore)

            purchase_item = consumption.purchase_item
            purchase_item.remaining_quantity += restore
            purchase_item.save(update_fields=["remaining_quantity"])

            consumption.restored_quantity += restore
            consumption.save(update_fields=["restored_quantity"])

            remaining_to_restore -= restore

        if remaining_to_restore > 0:
            raise ValidationError({
                "quantity": "Ledger inconsistency: not enough restorable quantity recorded for this item."
            })
    # else: legacy record with no ledger — restored stock goes straight to Inventory below.

    lost_item.found_quantity += quantity
    lost_item.save(update_fields=["found_quantity"])

    sync_inventory(product=lost_item.product, quantity_delta=quantity, user=user)
    apply_shelf_allocations(
        product=lost_item.product, allocations=resolved_allocations, sign=1,
        reason=ShelfStockMovement.Reason.LOST_FOUND_PUTAWAY,
        reference=lost_item.record.reference_number, user=user,
    )

    # Stock Movement Report
    _adjust_stock_movement(product_id=lost_item.product_id, found_delta=quantity)

    # activity_log tracks LostInventoryRecord (the headline object) via
    # signal, but this action only ever saves LostInventoryItem
    # (deliberately untracked — same "child line item" exclusion as
    # PurchaseItem, see activity_log.tracking's docstring) and never
    # re-saves the parent record, so nothing would otherwise fire here —
    # one explicit call, not a reversion to per-function instrumentation.
    from activity_log.services import record_activity
    record_activity(
        action="state_change",
        instance=lost_item.record,
        description=(
            f"Marked {quantity} unit(s) of '{lost_item.product.name}' as found "
            f"for {lost_item.record.reference_number}"
        ),
        object_repr=lost_item.record.reference_number,
        changed_fields=["found_quantity"],
    )

    recovered_amount = lost_item.unit_cost * Decimal(str(quantity))
    from cash_flow.services import sync_lost_inventory_found
    sync_lost_inventory_found(amount=recovered_amount, user=user)

    # Dated ledger for the Monthly Profit report — this is what lets a
    # recovery be correctly attributed to the month it actually happened
    # in, instead of the month the original loss was recorded in.
    LostInventoryRecovery.objects.create(
        lost_item=lost_item,
        quantity=quantity,
        recovered_amount=recovered_amount,
        recovered_at=timezone.localtime(timezone.now()).date(),
        recovered_by=user,
    )

    return lost_item