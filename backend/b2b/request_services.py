"""
Writes for purchase requests this software makes to a partner (see models.PurchaseRequest).

Principles:
  * Local first. A request (with its private shelf plan) is saved BEFORE the partner
    is told; `sent_at` is set only when the partner confirms receipt. If the partner
    can't be reached the request stays saved and catch-up sends it later — the
    partner treats a repeat of the same request_uuid as a no-op, so nothing is lost
    and nothing is duplicated. Only a DEFINITE refusal (the partner understood and
    said no) removes the just-created row, because then it never existed remotely.
  * The partner is the single source of truth for cancel-vs-accept: cancelling is a
    call to the partner, which only cancels a request that is still pending.
  * Importing an accepted request is idempotent and all-or-nothing: one transaction
    creates the purchase order, sets its shelves and confirms it (stock in, FIFO
    cost, supplier ledger, taxes — all through the existing purchases code). Any
    failure rolls everything back, is recorded on the request, and is retried by the
    next catch-up.
"""

import logging
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from purchases.models import Product, Shelf, Supplier
from purchases.services import (
    confirm_purchase_order, create_purchase_order, set_purchase_item_shelf_allocations,
)

from . import client, config
from .models import PurchaseRequest, PurchaseRequestItem, PurchaseRequestShelf, SyncState

logger = logging.getLogger("b2b.requests")

Status = PurchaseRequest.Status

# Catch-up looks at the outstanding requests in bounded chunks, oldest first, and stops
# after a few chunks so one pass can never run unbounded inside a user request.
CATCH_UP_CHUNK = 100
CATCH_UP_MAX_CHUNKS = 5

# Largest unit price we will accept from a partner's answer (matches the column definition).
MAX_PRICE = Decimal("9999999999.9999")


def same_text(a: str, b: str) -> bool:
    """Trimmed, whitespace-collapsed, case-insensitive comparison."""
    return " ".join((a or "").split()).casefold() == " ".join((b or "").split()).casefold()


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def _validate_new_request(provider: str, items: list):
    if provider not in config.provider_names():
        raise NotFound("Unknown partner.")
    if not items:
        raise ValidationError({"items": "At least one item is required."})
    if len(items) > config.MAX_REQUEST_ITEMS:
        raise ValidationError({"items": f"At most {config.MAX_REQUEST_ITEMS} items per request."})

    product_ids = [i["product_id"] for i in items]
    if len(set(product_ids)) != len(product_ids):
        raise ValidationError({"items": "A product appears more than once."})
    products = {p.id: p for p in Product.objects.filter(id__in=product_ids, is_deleted=False)}
    missing = [pid for pid in product_ids if pid not in products]
    if missing:
        raise ValidationError({"items": "Some products are not in your catalog."})

    shelf_ids = {a["shelf_id"] for i in items for a in i.get("shelf_allocations", [])}
    if Shelf.objects.filter(id__in=shelf_ids, is_deleted=False).count() != len(shelf_ids):
        raise ValidationError({"items": "A selected shelf does not exist."})

    problems = []
    for item in items:
        product = products[item["product_id"]]
        allocations = item.get("shelf_allocations", [])
        total = sum(a["quantity"] for a in allocations)
        if total != item["quantity"]:
            problems.append(f"{product.name} ({product.code}): shelves must add up to {item['quantity']} (currently {total}).")
        if len({a["shelf_id"] for a in allocations}) != len(allocations):
            problems.append(f"{product.name} ({product.code}): a shelf is selected twice.")
    if problems:
        raise ValidationError({"items": problems})
    return products


def _payload(request: PurchaseRequest) -> dict:
    return {
        "request_uuid": str(request.request_uuid),
        "note": request.note,
        "items": [
            {
                "product_code": i.product_code, "product_name": i.product_name,
                "quantity": i.requested_quantity,
                "discount": str(i.discount), "gst": str(i.gst), "wht": str(i.wht),
            }
            for i in request.items.all()
        ],
    }


def _send(request: PurchaseRequest) -> None:
    """Delivers a saved request. Repeat-safe. Raises client.ProviderError on failure."""
    status = client.submit_request(request.provider_name, _payload(request))
    PurchaseRequest.objects.filter(pk=request.pk, sent_at__isnull=True).update(sent_at=timezone.now())
    request.refresh_from_db(fields=["sent_at"])
    if status != "pending":
        # A repeat of an already-decided request: learn the outcome right away.
        sync_requests([request])


def create_purchase_request(*, provider: str, items: list, note: str, user, request_uuid=None):
    """
    items = [{"product_id": <local product id>, "quantity": int, "discount": Decimal,
              "gst": Decimal, "wht": Decimal,
              "shelf_allocations": [{"shelf_id": int, "quantity": int}, ...]}, ...]
    `request_uuid` (optional, chosen by the form) makes a double-click or a retried
    POST return the request that already exists instead of creating a second one.
    Returns (request, delivered). delivered=False means saved but the partner was
    unreachable — it will be sent automatically.
    """
    if request_uuid is not None:
        existing = PurchaseRequest.objects.filter(provider_name=provider, request_uuid=request_uuid).first()
        if existing is not None:
            return existing, existing.sent_at is not None

    products = _validate_new_request(provider, items)

    with transaction.atomic():
        extra = {"request_uuid": request_uuid} if request_uuid is not None else {}
        request = PurchaseRequest.objects.create(provider_name=provider, note=note or "", created_by=user, **extra)
        # Two bulk inserts for the whole request (not two per item).
        lines = PurchaseRequestItem.objects.bulk_create([
            PurchaseRequestItem(
                request=request, product=products[item["product_id"]],
                product_code=products[item["product_id"]].code,
                product_name=products[item["product_id"]].name,
                requested_quantity=item["quantity"],
                discount=item["discount"], gst=item["gst"], wht=item["wht"],
            )
            for item in items
        ])
        PurchaseRequestShelf.objects.bulk_create([
            PurchaseRequestShelf(item=line, shelf_id=a["shelf_id"], quantity=a["quantity"])
            for line, item in zip(lines, items)
            for a in item["shelf_allocations"]
        ])

    try:
        _send(request)
    except client.ProviderUnreachable:
        logger.warning("b2b request %s saved but not delivered yet (partner unreachable).", request.request_uuid)
        return request, False
    except client.ProviderError:
        # The partner understood and refused (or this software isn't set up to talk
        # to it): it never existed remotely, so remove the local row again — both
        # deletes together, or neither.
        with transaction.atomic():
            PurchaseRequestItem.objects.filter(request=request).delete()
            request.delete()
        raise
    return request, True


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------

def cancel_purchase_request(*, request_id: int) -> PurchaseRequest:
    request = PurchaseRequest.objects.filter(pk=request_id).first()
    if request is None:
        raise NotFound("Request not found.")
    if request.status != Status.PENDING:
        raise ValidationError({"status": f"Only a pending request can be cancelled (this one is {request.get_status_display().lower()})."})

    result = client.cancel_request(request.provider_name, request.request_uuid)   # ProviderError propagates
    if result in ("cancelled", "not_found"):
        with transaction.atomic():
            locked = PurchaseRequest.objects.select_for_update().get(pk=request.pk)
            if locked.status == Status.PENDING:
                locked.status = Status.CANCELLED
                locked.decided_at = timezone.now()
                locked.save(update_fields=["status", "decided_at"])
        return locked

    # The partner decided first: pick up its decision and refuse the cancel clearly.
    sync_requests([request])
    raise ValidationError({"status": "The partner has already decided this request, so it can no longer be cancelled."})


# ---------------------------------------------------------------------------
# Decisions + import
# ---------------------------------------------------------------------------

def fit_shelves(plan, target: int):
    """
    Adjusts a shelf plan [(shelf_id, qty), ...] to a new total. Fewer units are
    taken from the LAST shelf rows first; extra units go onto the last shelf row.
    """
    rows = [[shelf_id, qty] for shelf_id, qty in plan if qty > 0]
    if not rows:
        raise ValidationError({"shelves": "This request has no shelf plan."})
    total = sum(qty for _, qty in rows)
    if target > total:
        rows[-1][1] += target - total
    elif target < total:
        excess = total - target
        for row in reversed(rows):
            cut = min(row[1], excess)
            row[1] -= cut
            excess -= cut
            if excess == 0:
                break
    return [(shelf_id, qty) for shelf_id, qty in rows if qty > 0]


def _error_text(exc) -> str:
    detail = getattr(exc, "detail", None)
    return (str(detail) if detail is not None else f"{type(exc).__name__}: {exc}")[:2000]


def _import_locked(request: PurchaseRequest) -> None:
    code = config.supplier_code_for(request.provider_name)
    supplier = (
        Supplier.objects.filter(Q(code=code) | Q(code=code.upper()), is_deleted=False).order_by("id").first()
        if code else None
    )
    if supplier is None:
        raise ValidationError({"supplier": (
            f"No supplier with code '{code}' exists for this partner. Create it (or fix the code in the settings)."
            if code else "No supplier code is configured for this partner."
        )})
    if request.created_by is None:
        raise ValidationError({"user": "The user who made this request no longer exists."})

    lines = list(request.items.select_related("product").prefetch_related("shelves"))
    supplied = [line for line in lines if (line.accepted_quantity or 0) > 0]
    if not supplied:
        raise ValidationError({"items": "Nothing was accepted on this request."})

    user = request.created_by
    order = create_purchase_order(
        supplier_id=supplier.id,
        items=[
            {
                "product_id": line.product_id, "quantity": line.accepted_quantity,
                "unit_price": line.unit_price, "gst": line.gst, "wht": line.wht,
                "description": f"Purchase request {request.request_uuid}",
            }
            for line in supplied
        ],
        payment_type="after_delivery",
        user=user,
    )
    order_lines = {oi.product_id: oi for oi in order.items.all()}
    for line in supplied:
        plan = fit_shelves([(s.shelf_id, s.quantity) for s in line.shelves.all()], line.accepted_quantity)
        set_purchase_item_shelf_allocations(
            purchase_item_id=order_lines[line.product_id].id,
            allocations=[{"shelf_id": shelf_id, "quantity": qty} for shelf_id, qty in plan],
            user=user,
        )
    confirm_purchase_order(order_id=order.id, user=user)
    order.refresh_from_db()

    request.order = order
    request.order_number = order.order_number
    request.import_error = ""
    request.save(update_fields=["order", "order_number", "import_error"])


def import_accepted(request_id: int) -> bool:
    """
    Creates the confirmed purchase order for an accepted request. Safe to call any
    number of times: returns True when the order exists, False when it could not be
    created (the reason is stored on the request and shown to the user).
    """
    try:
        with transaction.atomic():
            request = PurchaseRequest.objects.select_for_update().get(pk=request_id)
            if request.order_id:
                return True
            if request.status != Status.ACCEPTED:
                return False
            _import_locked(request)
        return True
    except Exception as exc:  # noqa: BLE001 — recorded, never raised into catch-up / the doorbell
        # Written after the rollback, and only while no order exists (never overwrites a
        # request another worker has just imported successfully).
        PurchaseRequest.objects.filter(pk=request_id, order__isnull=True).update(import_error=_error_text(exc))
        logger.warning("b2b import of request %s failed: %s", request_id, type(exc).__name__)
        return False


def _read_decision_line(row: dict):
    """(quantity, unit_price, gst, wht) from one partner line, or None when it isn't trustworthy."""
    try:
        quantity = int(row["quantity"])
        unit_price, gst, wht = Decimal(row["unit_price"]), Decimal(row["gst"]), Decimal(row["wht"])
    except (TypeError, ValueError, ArithmeticError):
        return None
    if not all(value.is_finite() for value in (unit_price, gst, wht)):
        return None
    if quantity < 0 or quantity > 1_000_000 or not (0 <= unit_price <= MAX_PRICE):
        return None
    if not (0 <= gst <= 100 and 0 <= wht <= 100):
        return None
    return quantity, unit_price, gst, wht


def _apply_decision(request: PurchaseRequest, decision: dict) -> bool:
    """Writes the partner's decision onto the local request (under a row lock). True if the row changed."""
    status = decision["status"]
    if status in ("pending", "not_found"):
        return False
    with transaction.atomic():
        locked = PurchaseRequest.objects.select_for_update().get(pk=request.pk)
        if locked.status != Status.PENDING:
            return False
        now = timezone.now()
        if status in ("denied", "cancelled"):
            locked.status = Status.DENIED if status == "denied" else Status.CANCELLED
            locked.decided_at = now
            locked.save(update_fields=["status", "decided_at"])
            return True

        # accepted — the partner's invoice is the truth, so its quantities, price and
        # taxes become ours (they are identical to what we asked for unless it changed
        # a quantity). An answer we cannot trust leaves the request PENDING with the
        # reason shown; the next sync looks again.
        accepted = {row["product_code"]: row for row in decision["items"]}
        lines = list(locked.items.all())
        if set(accepted) - {line.product_code for line in lines}:
            locked.import_error = "The partner's answer contains a product that was not on this request."
            locked.save(update_fields=["import_error"])
            return False
        for line in lines:
            row = accepted.get(line.product_code)
            if row is None:
                line.accepted_quantity = 0
                continue
            parsed = _read_decision_line(row)
            if parsed is None:
                locked.import_error = "The partner's answer could not be read."
                locked.save(update_fields=["import_error"])
                return False
            line.accepted_quantity, line.unit_price, line.gst, line.wht = parsed
        PurchaseRequestItem.objects.bulk_update(lines, ["accepted_quantity", "unit_price", "gst", "wht"])
        locked.status = Status.ACCEPTED
        locked.decided_at = now
        locked.import_error = ""
        locked.save(update_fields=["status", "decided_at", "import_error"])
        return True


def sync_requests(requests) -> int:
    """
    Learns the partner's decision for the given requests and imports accepted
    ones. Returns how many requests changed state or were imported. Raises
    client.ProviderError if the partner can't be asked.
    """
    changed = 0
    by_provider = {}
    for request in requests:
        by_provider.setdefault(request.provider_name, []).append(request)

    for provider, group in by_provider.items():
        asking = [r for r in group if r.status == Status.PENDING]
        decisions = {}
        if asking:
            decisions = {d["request_uuid"]: d for d in client.fetch_decisions(provider, [r.request_uuid for r in asking])}
        for request in group:
            decision = decisions.get(str(request.request_uuid))
            # Only re-read the row when something was actually written to it.
            if decision is not None and _apply_decision(request, decision):
                request.refresh_from_db()
                changed += 1
            if request.status == Status.ACCEPTED and not request.order_id:
                if import_accepted(request.pk):
                    changed += 1
    return changed


def process_doorbell(*, provider: str, request_uuid) -> bool:
    """The partner says one of our requests was decided: fetch it and act. Never raises."""
    request = PurchaseRequest.objects.filter(provider_name=provider, request_uuid=request_uuid).first()
    if request is None:
        return False
    try:
        sync_requests([request])
    except client.ProviderError:
        logger.warning("b2b doorbell for %s: could not reach the partner; catch-up will retry.", request_uuid)
        return False
    except Exception as exc:  # noqa: BLE001 — a doorbell must always get a quick, plain answer
        logger.warning("b2b doorbell for %s failed: %s", request_uuid, type(exc).__name__)
        return False
    return True


# ---------------------------------------------------------------------------
# Catch-up
# ---------------------------------------------------------------------------

def _undecided_requests():
    return PurchaseRequest.objects.filter(Q(status=Status.PENDING) | Q(status=Status.ACCEPTED, order__isnull=True))


def _claim_check_slot(*, force: bool) -> bool:
    """
    Takes the right to ask the partner now, with one conditional UPDATE (so two
    concurrent catch-ups can't both pass): allowed when never checked or the last
    check is older than a minute — or always when `force`.
    """
    SyncState.get()   # make sure the single row exists
    now = timezone.now()
    cutoff = now - timedelta(seconds=config.SYNC_MIN_INTERVAL_SECONDS)
    slot = SyncState.objects.filter(pk=1)
    if not force:
        slot = slot.filter(Q(last_checked_at__isnull=True) | Q(last_checked_at__lt=cutoff))
    return slot.update(last_checked_at=now) == 1


def run_catch_up(*, force: bool = False) -> int:
    """
    O(1) when nothing is outstanding (one indexed existence check). When something
    is, the partner is asked at most once a minute (marker on SyncState), unless
    `force` (the user pressed "check for updates"). Re-sends undelivered requests,
    learns pending decisions, and retries accepted-but-not-imported ones, in bounded
    chunks. Never raises: a partner that is offline simply means "try again next time".
    """
    if not config.consumer_enabled():
        return 0
    if not _undecided_requests().exists():
        return 0
    if not _claim_check_slot(force=force):
        return 0

    processed = 0
    cursor = None   # (created_at, id) of the last row of the previous chunk
    for _ in range(CATCH_UP_MAX_CHUNKS):
        outstanding = _undecided_requests().order_by("created_at", "id")
        if cursor is not None:
            outstanding = outstanding.filter(Q(created_at__gt=cursor[0]) | Q(created_at=cursor[0], id__gt=cursor[1]))
        batch = list(outstanding[:CATCH_UP_CHUNK])
        if not batch:
            break
        cursor = (batch[-1].created_at, batch[-1].id)

        try:
            for request in batch:
                if request.sent_at is not None or request.status != Status.PENDING:
                    continue
                # Re-check right before sending: the user may have cancelled it a moment ago.
                request.refresh_from_db(fields=["status", "sent_at"])
                if request.status != Status.PENDING or request.sent_at is not None:
                    continue
                try:
                    _send(request)
                    processed += 1
                except client.ProviderUnreachable:
                    raise            # the partner is down: stop wasting time on the rest
                except client.ProviderError:
                    continue         # this one was refused; the others may still go through
            processed += sync_requests(batch)
        except client.ProviderError:
            logger.warning("b2b catch-up: partner not reachable right now.")
            break
        except Exception as exc:  # noqa: BLE001 — catch-up must never take a user request down
            logger.warning("b2b catch-up failed: %s", type(exc).__name__)
            break
    return processed
