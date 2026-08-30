from datetime import timedelta
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

DEFAULT_DUE_DATE_DAYS = 7

from rates.selectors import get_price_at_date

from .models import (
    Customer, FIFOLedger, Invoice, InvoiceItem, InvoiceItemShelfAllocation,
    InvoiceReturnItemShelfAllocation, Payment, Return, ReturnItem,
)
from .selectors import (
    get_available_purchase_batches,
    get_customer_by_id,
    get_invoice_by_id,
    get_invoice_item_by_id,
    get_payment_by_id,
    get_return_by_id,
    get_return_item_by_id,
)

# Single source of truth for identifying the system-generated advance
# Payment row (no dedicated is_advance field — see purchases.services'
# identical SupplierPayment convention). Every create/filter site below
# must use this constant so they can never drift out of sync.
ADVANCE_PAYMENT_NOTE = "Advance payment on draft invoice creation."


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _soft_delete(instance, user) -> None:
    """DRY soft delete - reused across all models in this app."""
    instance.is_deleted = True
    instance.deleted_at = timezone.now()
    instance.deleted_by = user
    instance.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])


def _sync_invoice_payment_summary(invoice) -> None:
    """
    Recomputes and saves all payment tracking fields on an Invoice.
    Called after every Payment create/delete, confirmation, and return acceptance.

    Business logic:
        - On confirmation: full grand_total is credited to customer
          (credit_outstanding = grand_total, meaning customer owes this on credit)
        - Each payment (cash/jazzcash/easypaisa/bank) reduces credit_outstanding
          and increases cash_received by the payment amount
        - Return credit notes (negative payments) reduce credit_outstanding further
          (customer owes less because stock came back)
        - remaining_amount = credit_outstanding (they are always equal)
        - payment_status:
            paid    -> credit_outstanding <= 0
            partial -> 0 < credit_outstanding < grand_total
            unpaid  -> credit_outstanding == grand_total (no payments at all)
    """
    from decimal import Decimal
    from django.db.models import Q, Sum
    from .models import Payment

    # One conditional aggregate instead of loading every payment row into
    # Python and looping twice — same numbers, one query.
    agg = Payment.objects.filter(invoice=invoice, is_deleted=False).aggregate(
        cash=Sum("amount", filter=Q(amount__gt=0)),
        credits=Sum("amount", filter=Q(amount__lt=0)),
    )
    # Actual cash/digital payments received (positive amounts)
    cash_received = agg["cash"] or Decimal("0")
    # Return credit notes (negative amounts) — reduce what customer owes
    return_credits = abs(agg["credits"] or Decimal("0"))

    # credit_outstanding = how much customer still owes on credit
    # Starts at grand_total, reduced by payments received and return credits
    credit_outstanding = max(
        Decimal("0"),
        invoice.grand_total - cash_received - return_credits,
    )

    # remaining_amount always mirrors credit_outstanding
    remaining_amount = credit_outstanding

    # total_paid = actual money received (excludes credit_outstanding)
    total_paid = cash_received

    if remaining_amount <= 0:
        payment_status = invoice.PaymentStatus.PAID
    elif cash_received > 0 or return_credits > 0:
        payment_status = invoice.PaymentStatus.PARTIAL
    else:
        payment_status = invoice.PaymentStatus.UNPAID

    invoice.cash_received      = cash_received
    invoice.credit_outstanding = credit_outstanding
    invoice.total_paid         = total_paid
    invoice.remaining_amount   = remaining_amount
    invoice.payment_status     = payment_status
    invoice.save(update_fields=[
        "cash_received", "credit_outstanding", "total_paid",
        "remaining_amount", "payment_status",
    ])


# Reference generation is counter-based (purchases.DocumentCounter): O(1),
# race-safe, immune to the text-sort rollover at 10000, and seeded from the
# numeric max of ALL existing rows including soft-deleted ones — the old
# generators here queried through the soft-delete manager, so soft-deleting
# the highest-numbered payment/return made the next create collide with the
# deleted row's unique reference (500).

def _generate_bill_number() -> str:
    """Sequential bill number: BILL-2026-0001."""
    from purchases.services import next_reference
    return next_reference(counter_key="BILL", prefix_label="BILL", model=Invoice, field="bill_number")


def _generate_payment_reference() -> str:
    """Sequential billing payment reference: PAY-2026-0001."""
    from purchases.services import next_reference
    return next_reference(counter_key="PAY", prefix_label="PAY", model=Payment, field="reference_number")


def _generate_return_reference() -> str:
    """
    Sequential billing return reference: RTN-2026-0001.
    Counter key BILL-RTN keeps this sequence independent from purchase
    returns, which share the RTN- display prefix (uniqueness is per-table).
    """
    from purchases.services import next_reference
    return next_reference(counter_key="BILL-RTN", prefix_label="RTN", model=Return, field="reference_number")


def _get_current_selling_price(product) -> Decimal:
    """
    Fetches the current selling price from the rate list.
    Raises ValidationError if no rate is set for this product.
    """
    from rest_framework.exceptions import ValidationError
    try:
        rate = product.rate  # OneToOne reverse from rates.ProductRate
        if not rate:
            raise ValidationError(
                {product.name: f"No selling price set for '{product.name}'. Please set a rate first."}
            )
        return rate.selling_price
    except Exception:
        raise ValidationError(
            {"product": f"No selling price set for '{product.name}'. Please set a rate first."}
        )


def _validate_stock(product, requested_qty: int, exclude_invoice_id: int = None) -> None:
    """
    Validates that enough stock is available in inventory.
    On draft edit, exclude the current invoice's already-reserved qty
    by checking remaining_quantity on purchase batches directly.
    Raises ValidationError with a clear message if stock is insufficient.
    """
    from rest_framework.exceptions import ValidationError
    from django.db.models import Sum

    # Single aggregate instead of loading every batch row to sum in Python.
    # Deliberately unlocked — this also runs on draft create/edit, which
    # must never take stock locks. The locked walk in _run_fifo has its own
    # ran-out guard for the confirm race.
    available = (
        get_available_purchase_batches(product.id)
        .aggregate(total=Sum("remaining_quantity"))["total"] or 0
    )

    if available < requested_qty:
        raise ValidationError({
            "quantity": (
                f"Insufficient stock for '{product.name}'. "
                f"Requested: {requested_qty}, Available: {available}."
            )
        })


def _run_fifo(*, invoice_item: InvoiceItem, quantity: int, user) -> Decimal:
    """
    Consumes stock from purchase batches in FIFO order for a given product.
    Creates FIFOLedger entries for each batch consumed.
    Returns the blended COGS per unit for storage on the invoice item.

    This is the heart of FIFO. It:
    1. Iterates purchase batches oldest-first
    2. Consumes as many units as possible from each batch
    3. Records each consumption in FIFOLedger
    4. Decrements remaining_quantity on the purchase batch
    5. Returns blended cost = total_cost / total_qty
    """
    product = invoice_item.product
    remaining_to_consume = quantity
    total_cost = Decimal("0")
    # for_update: this decrements remaining_quantity — batch rows are locked
    # so a concurrent confirm/loss can't consume the same units. Runs inside
    # confirm_invoice's transaction; locks acquired in FIFO order.
    batches = get_available_purchase_batches(product.id, for_update=True)

    for batch in batches:
        if remaining_to_consume <= 0:
            break

        consume = min(batch.remaining_quantity, remaining_to_consume)
        # Use tax-inclusive unit cost: total_price / quantity
        # This is the real cost we paid (includes GST added, WHT deducted)
        tax_inclusive_unit_cost = (
            batch.total_price / batch.quantity
            if batch.quantity > 0 else batch.unit_price
        )
        cost_for_layer = consume * tax_inclusive_unit_cost

        FIFOLedger.objects.create(
            invoice_item=invoice_item,
            purchase=batch,
            quantity=consume,
            unit_cost=tax_inclusive_unit_cost,
        )

        batch.remaining_quantity -= consume
        batch.save(update_fields=["remaining_quantity"])

        total_cost += cost_for_layer
        remaining_to_consume -= consume

    if remaining_to_consume > 0:
        # This should never happen if _validate_stock ran first
        from rest_framework.exceptions import ValidationError
        raise ValidationError({
            "stock": f"Stock ran out mid-confirmation for '{product.name}'. Please refresh and try again."
        })

    blended_cogs_per_unit = total_cost / Decimal(str(quantity))
    return blended_cogs_per_unit


def _reverse_fifo(*, invoice_item: InvoiceItem, return_quantity: int) -> None:
    """
    Reverses FIFO consumption for a return — restores remaining_quantity
    on purchase batches in reverse FIFO order (LIFO reversal = FIFO restore).
    Creates negative FIFOLedger entries for audit completeness.
    Also increments the inventory directly.
    """
    product = invoice_item.product
    remaining_to_restore = return_quantity

    # Reverse in newest-first order so the most recently consumed batch
    # is restored first (correct FIFO reversal).
    # select_related("purchase"): each layer's batch was previously lazy-
    # loaded one query at a time. select_for_update: the joined batch rows'
    # remaining_quantity is read-then-written, so they must be locked
    # against concurrent FIFO consumers. Inside accept_return's transaction.
    layers = FIFOLedger.objects.select_related("purchase").select_for_update().filter(
        invoice_item=invoice_item,
        quantity__gt=0,          # only original consumption entries
    ).order_by("-created_at")

    for layer in layers:
        if remaining_to_restore <= 0:
            break

        restore = min(layer.quantity, remaining_to_restore)

        # Restore remaining_quantity on the purchase batch
        layer.purchase.remaining_quantity += restore
        layer.purchase.save(update_fields=["remaining_quantity"])

        # Append a negative ledger entry for audit trail
        FIFOLedger.objects.create(
            invoice_item=invoice_item,
            purchase=layer.purchase,
            quantity=-restore,
            unit_cost=layer.unit_cost,
        )

        remaining_to_restore -= restore

    # Increment inventory — through the shared writer so the inventory
    # stats counters stay in sync (user=None: this path never recorded
    # last_updated_by, and the writer preserves that).
    from purchases.services import sync_inventory
    sync_inventory(product=product, quantity_delta=return_quantity, user=None)


def _recalculate_invoice_totals(invoice: Invoice) -> None:
    """
    Recomputes and saves all invoice-level totals from line items.
    Called after confirmation and after returns.
    Uses calculate_invoice_totals() from utils - single source of truth.
    """
    from .utils import calculate_invoice_totals

    line_data = [
        {
            "line_gross"      : item.line_gross,
            "line_gst_amount" : item.line_gst_amount,
            "line_wht_amount" : item.line_wht_amount,
            "line_total"      : item.line_total,
            "line_cogs"       : item.line_cogs,
        }
        for item in invoice.items.all()
    ]
    totals = calculate_invoice_totals(line_data)

    invoice.subtotal     = totals["subtotal"]
    invoice.gst_total    = totals["gst_total"]
    invoice.wht_total    = totals["wht_total"]
    invoice.grand_total  = totals["grand_total"]
    invoice.total_cogs   = totals["total_cogs"]
    invoice.gross_profit = totals["gross_profit"]
    invoice.save(update_fields=[
        "subtotal", "gst_total", "wht_total", "grand_total",
        "total_cogs", "gross_profit",
    ])


# ---------------------------------------------------------------------------
# Customer services
# ---------------------------------------------------------------------------

@transaction.atomic
def create_customer(*, name: str, code: str, address: str, mobile: str = "", user) -> Customer:
    from rest_framework.exceptions import ValidationError
    if Customer.objects.filter(code__iexact=code, is_deleted=False).exists():
        raise ValidationError({"code": "A customer with this code already exists."})
    customer = Customer.objects.create(
        name=name, code=code.upper(), address=address,
        mobile=mobile, created_by=user, updated_by=user,
    )

    from credit_score.services import initialize_credit_score
    initialize_credit_score(customer, user)

    # Auto-create empty ledger for this customer
    from ledger.services import create_ledger_for_customer
    create_ledger_for_customer(customer=customer)

    return customer


@transaction.atomic
def update_customer(
    *, pk: int, name: str = None, code: str = None,
    address: str = None, mobile: str = None, user,
) -> Customer:
    from rest_framework.exceptions import ValidationError
    customer = get_customer_by_id(pk)
    if code:
        qs = Customer.objects.filter(code__iexact=code, is_deleted=False).exclude(pk=pk)
        if qs.exists():
            raise ValidationError({"code": "A customer with this code already exists."})
        customer.code = code.upper()
    if name is not None:
        customer.name = name
    if address is not None:
        customer.address = address
    if mobile is not None:
        customer.mobile = mobile
    customer.updated_by = user
    customer.save(update_fields=["name", "code", "address", "mobile", "updated_by", "updated_at"])

    # Keep the ledger's name/code snapshot in sync with the live customer —
    # mirrors purchases.services.update_supplier's fix (same bug, found
    # 2026-08-31, on the supplier side first).
    from ledger.services import sync_customer_ledger_snapshot
    sync_customer_ledger_snapshot(customer=customer)

    return customer


def delete_customer(*, pk: int, user) -> None:
    customer = get_customer_by_id(pk)
    _soft_delete(customer, user)


# ---------------------------------------------------------------------------
# Invoice (Draft) services
# ---------------------------------------------------------------------------

@transaction.atomic
def create_invoice(
    *, customer_id: int, items: list[dict],
    payment_type: str = "after_delivery", advance_amount: Decimal = Decimal("0"),
    method_allocations: list = None, payment_due_date=None, user,
) -> Invoice:
    """
    Creates a DRAFT invoice with line items.
    items = [{"product_id": 1, "quantity": 5}, ...]

    Stock validation runs here so user sees errors immediately,
    but stock is NOT deducted yet (that happens on confirmation).
    Rate list validation also runs here.

    If payment_type=advance and advance_amount > 0:
        - advance_amount immediately added to cash_in_hand
        - A Payment record is auto-created for the advance
        - method_allocations (required in this case) — [(PaymentMethod,
          Decimal), ...] — records which real accounts the advance landed
          in via payment_methods.services.record_allocations

    payment_due_date defaults to today + DEFAULT_DUE_DATE_DAYS when omitted,
    and is carried through unchanged at confirmation.
    """
    from purchases.selectors import get_product_by_id
    from rest_framework.exceptions import ValidationError

    get_customer_by_id(customer_id)  # validate customer exists

    if not items:
        raise ValidationError({"items": "At least one item is required."})

    if payment_type == "after_delivery":
        advance_amount = Decimal("0")
    if advance_amount < 0:
        raise ValidationError({"advance_amount": "Advance amount cannot be negative."})
    if payment_type == "advance" and advance_amount > 0 and not method_allocations:
        raise ValidationError({"method_allocations": "At least one method must be selected for the advance payment."})

    if payment_due_date is None:
        payment_due_date = timezone.localtime(timezone.now()).date() + timedelta(days=DEFAULT_DUE_DATE_DAYS)

    # Validate all products + stock before creating anything
    validated_items = []
    seen_products = set()
    for item in items:
        product = get_product_by_id(item["product_id"])
        if product.id in seen_products:
            raise ValidationError({"items": f"Duplicate product '{product.name}' in items."})
        seen_products.add(product.id)
        _get_current_selling_price(product)      # raises if no rate
        _validate_stock(product, item["quantity"])
        validated_items.append((
            product,
            item["quantity"],
            item.get("discount", Decimal("0")),
            item.get("gst",      Decimal("0")),
            item.get("wht",      Decimal("0")),
        ))

    invoice = Invoice.objects.create(
        bill_number=_generate_bill_number(),
        customer_id=customer_id,
        status=Invoice.Status.DRAFT,
        payment_type=payment_type,
        advance_amount=advance_amount,
        payment_due_date=payment_due_date,
        created_by=user,
        updated_by=user,
    )

    # If advance payment: add to cash_in_hand and record in payment history
    if payment_type == "advance" and advance_amount > 0:
        from payment_methods.services import derive_legacy_method_label, record_allocations

        adv_payment = Payment.objects.create(
            invoice=invoice,
            reference_number=_generate_payment_reference(),
            amount=advance_amount,
            method=derive_legacy_method_label(method_allocations),
            payment_date=timezone.localtime(timezone.now()).date(),
            note=ADVANCE_PAYMENT_NOTE,
            created_by=user,
            updated_by=user,
        )
        from cash_flow.services import record_cash_movement, sync_invoice_advance_payment_created
        sync_invoice_advance_payment_created(advance_amount=advance_amount, user=user)
        record_cash_movement(adv_payment)
        record_allocations(
            adv_payment, direction="inflow", splits=method_allocations,
            total_amount=advance_amount, date=adv_payment.payment_date, user=user,
        )

        # Ledger entry: advance credit (customer paid upfront, owes us less)
        from ledger.services import add_customer_advance_entry
        add_customer_advance_entry(
            customer=invoice.customer,
            payment=adv_payment,
            amount=advance_amount,
            date=adv_payment.payment_date,
            user=user,
        )

    for product, quantity, discount, gst, wht in validated_items:
        InvoiceItem.objects.create(
            invoice=invoice,
            product=product,
            quantity=quantity,
            discount=discount,
            gst=gst,
            wht=wht,
            # selling_price, effective_price, cogs filled at confirmation
        )

    return invoice


@transaction.atomic
def update_invoice_items(
    *, invoice_id: int, items: list[dict],
    payment_type: str = None, advance_amount: Decimal = None,
    method_allocations: list = None, payment_due_date=None, user,
) -> Invoice:
    """
    Replaces all line items on a DRAFT invoice.
    Only allowed while status=DRAFT.
    Customer is immutable after creation.
    payment_type, advance_amount, and payment_due_date can also be updated
    while in draft. advance_amount changes auto-adjust cash_in_hand.
    Editing the due date while still draft never touches the credit score —
    only a CONFIRMED invoice's due date affects a customer's score (see
    update_invoice_due_date for that path).
    """
    from purchases.selectors import get_product_by_id
    from rest_framework.exceptions import ValidationError

    invoice = get_invoice_by_id(invoice_id)

    if invoice.status != Invoice.Status.DRAFT:
        raise ValidationError({"status": "Only draft invoices can be edited."})

    if not items:
        raise ValidationError({"items": "At least one item is required."})

    validated_items = []
    seen_products = set()
    for item in items:
        product = get_product_by_id(item["product_id"])
        if product.id in seen_products:
            raise ValidationError({"items": f"Duplicate product '{product.name}' in items."})
        seen_products.add(product.id)
        _get_current_selling_price(product)
        _validate_stock(product, item["quantity"])
        validated_items.append((
            product,
            item["quantity"],
            item.get("discount", Decimal("0")),
            item.get("gst",      Decimal("0")),
            item.get("wht",      Decimal("0")),
        ))

    # Replace all existing items
    invoice.items.all().delete()
    for product, quantity, discount, gst, wht in validated_items:
        InvoiceItem.objects.create(
            invoice=invoice,
            product=product,
            quantity=quantity,
            discount=discount,
            gst=gst,
            wht=wht,
        )

    # Handle payment_type change
    if payment_type is not None:
        old_payment_type = invoice.payment_type
        invoice.payment_type = payment_type
        # If switching from advance to after_delivery — refund advance
        if old_payment_type == "advance" and payment_type == "after_delivery":
            old_advance = invoice.advance_amount
            if old_advance > 0:
                _cancel_advance_payment(invoice=invoice, user=user)
                invoice.advance_amount = Decimal("0")

    # Handle advance_amount change
    if advance_amount is not None and invoice.payment_type == "advance":
        if advance_amount < 0:
            raise ValidationError({"advance_amount": "Advance amount cannot be negative."})
        old_advance = invoice.advance_amount
        if advance_amount != old_advance:
            if advance_amount > 0 and not method_allocations:
                raise ValidationError({"method_allocations": "At least one method must be selected for the advance payment."})
            _update_advance_payment(
                invoice=invoice, old_amount=old_advance, new_amount=advance_amount,
                method_allocations=method_allocations, user=user,
            )
            invoice.advance_amount = advance_amount

    if payment_due_date is not None:
        invoice.payment_due_date = payment_due_date

    invoice.updated_by = user
    invoice.save(update_fields=[
        "payment_type", "advance_amount", "payment_due_date", "updated_by", "updated_at",
    ])
    return invoice


@transaction.atomic
def set_invoice_item_shelf_allocations(*, invoice_item_id: int, allocations: list[dict], user) -> InvoiceItem:
    """
    Replaces all shelf consumption allocations for one draft invoice line —
    which shelf(s) this sale is physically fulfilled from. Only shelves
    currently holding stock of this product are valid; confirm_invoice
    re-validates availability at commit time. Duplicate shelf_id entries in
    the input are merged so a double submission doesn't hit the unique
    constraint.
    """
    from rest_framework.exceptions import ValidationError
    from purchases.services import _validate_shelf_ids_exist, validate_shelf_consumption

    invoice_item = get_invoice_item_by_id(invoice_item_id)
    if invoice_item.invoice.status != Invoice.Status.DRAFT:
        raise ValidationError({"status": "Shelf allocations can only be edited on a draft invoice."})

    shelves_by_id = _validate_shelf_ids_exist([a["shelf_id"] for a in allocations])
    merged = {}
    for a in allocations:
        merged[a["shelf_id"]] = merged.get(a["shelf_id"], 0) + a["quantity"]

    total_allocated = sum(merged.values())
    if total_allocated > invoice_item.quantity:
        raise ValidationError({
            "shelf_allocations": (
                f"Allocated quantity ({total_allocated}) exceeds the sale "
                f"quantity ({invoice_item.quantity})."
            )
        })

    validate_shelf_consumption(product=invoice_item.product, allocations=[
        {"shelf": shelves_by_id[shelf_id], "quantity": qty}
        for shelf_id, qty in merged.items() if qty > 0
    ])

    invoice_item.shelf_allocations.all().delete()
    InvoiceItemShelfAllocation.objects.bulk_create([
        InvoiceItemShelfAllocation(invoice_item=invoice_item, shelf_id=shelf_id, quantity=qty)
        for shelf_id, qty in merged.items() if qty > 0
    ])
    return invoice_item


@transaction.atomic
def set_return_item_shelf_allocations(*, return_item_id: int, allocations: list[dict], user) -> ReturnItem:
    """
    Replaces all shelf put-away allocations for one pending invoice return
    item — where the customer-returned quantity is physically placed. Any
    shelf is valid (put-away).
    """
    from rest_framework.exceptions import ValidationError
    from purchases.services import _validate_shelf_ids_exist

    return_item = get_return_item_by_id(return_item_id)
    if return_item.return_record.status != Return.Status.PENDING:
        raise ValidationError({"status": "Shelf allocations can only be edited on a pending return."})

    _validate_shelf_ids_exist([a["shelf_id"] for a in allocations])
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

    return_item.shelf_allocations.all().delete()
    InvoiceReturnItemShelfAllocation.objects.bulk_create([
        InvoiceReturnItemShelfAllocation(return_item=return_item, shelf_id=shelf_id, quantity=qty)
        for shelf_id, qty in merged.items() if qty > 0
    ])
    return return_item


@transaction.atomic
def delete_invoice(*, invoice_id: int, user) -> None:
    """Only DRAFT invoices can be deleted. Refunds advance payment if applicable."""
    from rest_framework.exceptions import ValidationError
    invoice = get_invoice_by_id(invoice_id)
    if invoice.status != Invoice.Status.DRAFT:
        raise ValidationError({"status": "Only draft invoices can be deleted."})

    # Refund advance if this was an advance invoice
    if invoice.payment_type == "advance" and invoice.advance_amount > 0:
        if not _cancel_advance_payment(invoice=invoice, user=user):
            from cash_flow.services import sync_invoice_advance_payment_deleted
            sync_invoice_advance_payment_deleted(advance_amount=invoice.advance_amount, user=user)

    _soft_delete(invoice, user)


@transaction.atomic
def update_invoice_due_date(*, invoice_id: int, new_due_date, user) -> Invoice:
    """
    Extends (or otherwise edits) a CONFIRMED invoice's due date. Draft due-date
    edits go through update_invoice_items instead, and never reach here.
    Allowed on CONFIRMED, PARTIAL (partially returned, may still carry a
    real balance), and RETURNED (harmless — no outstanding balance left to
    matter) — anything except DRAFT.

    Immediately re-runs the customer's credit score so an extension is
    reflected right away rather than waiting for the next catch-up sweep.
    """
    from rest_framework.exceptions import ValidationError

    invoice = get_invoice_by_id(invoice_id)
    if invoice.status == Invoice.Status.DRAFT:
        raise ValidationError({"status": "Draft invoices are edited via the normal invoice edit endpoint."})
    if not new_due_date:
        raise ValidationError({"payment_due_date": "A due date is required."})

    invoice.payment_due_date = new_due_date
    invoice.updated_by = user
    invoice.save(update_fields=["payment_due_date", "updated_by", "updated_at"])

    from credit_score.services import recalculate_credit_score
    recalculate_credit_score(
        customer_id=invoice.customer_id, user=user,
        trigger="due_date_extended", reference=invoice.bill_number,
    )

    return invoice


# ---------------------------------------------------------------------------
# Invoice — advance payment helpers (mirrors purchases.services pattern)
# ---------------------------------------------------------------------------

def _cancel_advance_payment(*, invoice, user) -> bool:
    """
    Cancels any existing advance Payment on this invoice and reverses cash.
    Also removes the linked customer ledger entry (mirrors the supplier-side
    _cancel_advance_payment in purchases.services — the ledger entry was
    previously left orphaned here, silently overstating the customer's
    receivable balance after a draft with an advance was deleted).
    Returns True if an advance payment was found and cancelled.
    """
    advance_payment = Payment.objects.filter(
        invoice=invoice,
        note__startswith=ADVANCE_PAYMENT_NOTE,
        amount__gt=0,
        is_deleted=False,
    ).first()
    if advance_payment:
        from cash_flow.services import reverse_cash_movement, sync_invoice_advance_payment_deleted
        sync_invoice_advance_payment_deleted(advance_amount=advance_payment.amount, user=user)

        from ledger.services import remove_customer_ledger_entry_for_payment
        remove_customer_ledger_entry_for_payment(payment=advance_payment)

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
    *, invoice, old_amount: Decimal, new_amount: Decimal, method_allocations: list, user,
) -> None:
    """
    Updates the advance Payment record and adjusts cash_in_hand. Also keeps
    the linked customer ledger entry's amount in sync (mirrors the
    supplier-side _update_advance_payment in purchases.services — this
    previously updated the real Payment/cash but left the ledger entry at
    its original amount, silently understating the customer's receivable
    balance after the advance was edited).

    method_allocations is the user's NEW split for new_amount — this is
    always a user-driven edit (called only from update_invoice_items), so
    the split is never assumed/reused from the old amount; the caller
    validates it's present whenever new_amount > 0 before calling in.
    """
    advance_payment = Payment.objects.filter(
        invoice=invoice,
        note__startswith=ADVANCE_PAYMENT_NOTE,
        amount__gt=0,
        is_deleted=False,
    ).first()

    from payment_methods.services import derive_legacy_method_label, record_allocations, refresh_allocations

    if advance_payment:
        advance_payment.amount = new_amount
        advance_payment.method = derive_legacy_method_label(method_allocations) if method_allocations else advance_payment.method
        advance_payment.save(update_fields=["amount", "method"])

        from cash_flow.services import refresh_cash_movement
        refresh_cash_movement(advance_payment)

        if method_allocations:
            refresh_allocations(
                advance_payment, direction="inflow", splits=method_allocations,
                total_amount=new_amount, date=advance_payment.payment_date, user=user,
            )

        from ledger.models import CustomerLedgerEntry
        from ledger.services import _get_year_month, _recalculate_customer_snapshots_from
        ledger_entry = CustomerLedgerEntry.objects.filter(payment=advance_payment).first()
        if ledger_entry:
            ledger_entry.credit = new_amount
            ledger_entry.save(update_fields=["credit"])
            from ledger.models import CustomerLedger
            ledger = CustomerLedger.objects.select_for_update().get(pk=ledger_entry.ledger_id)
            _recalculate_customer_snapshots_from(ledger, _get_year_month(ledger_entry.date))
    else:
        adv_payment = Payment.objects.create(
            invoice=invoice,
            reference_number=_generate_payment_reference(),
            amount=new_amount,
            method=derive_legacy_method_label(method_allocations),
            payment_date=timezone.localtime(timezone.now()).date(),
            note=ADVANCE_PAYMENT_NOTE,
            created_by=user,
            updated_by=user,
        )
        from ledger.services import add_customer_advance_entry
        add_customer_advance_entry(
            customer=invoice.customer,
            payment=adv_payment,
            amount=new_amount,
            date=timezone.localtime(timezone.now()).date(),
            user=user,
        )
        from cash_flow.services import record_cash_movement
        record_cash_movement(adv_payment)
        record_allocations(
            adv_payment, direction="inflow", splits=method_allocations,
            total_amount=new_amount, date=adv_payment.payment_date, user=user,
        )

    from cash_flow.services import sync_invoice_advance_payment_updated
    sync_invoice_advance_payment_updated(old_amount=old_amount, new_amount=new_amount, user=user)


# ---------------------------------------------------------------------------
# Confirm Invoice
# ---------------------------------------------------------------------------

@transaction.atomic
def confirm_invoice(*, invoice_id: int, user) -> Invoice:
    """
    Confirms a draft invoice:
    1. Validates stock one final time (race-condition safety)
    2. Snapshots selling price from rate list onto each item
    3. Runs FIFO to consume purchase batches and get blended COGS
    4. Stores line totals, COGS, profit on each item
    5. Deducts quantity from Inventory
    6. Recomputes invoice-level totals
    7. Sets status=CONFIRMED
    """
    from rest_framework.exceptions import ValidationError

    invoice = get_invoice_by_id(invoice_id)
    if invoice.status != Invoice.Status.DRAFT:
        raise ValidationError({"status": "Only draft invoices can be confirmed."})

    from purchases.services import validate_allocations_complete, validate_shelf_consumption

    # Sorted in Python (not .order_by) for two reasons: a deterministic
    # product order means two concurrent confirms lock products in the same
    # sequence (no deadlocks), and sorting the PREFETCHED objects keeps
    # _recalculate_invoice_totals below reading the same in-memory items
    # this loop mutates. The shelf-consumption validation below takes
    # select_for_update() locks, so it must use this SAME sorted order too
    # (previously validated in prefetch/insertion order, which could
    # deadlock against accept_return's/confirm_purchase_order's/this same
    # function's own sorted lock order under concurrent overlapping
    # confirms).
    sorted_items = sorted(invoice.items.all(), key=lambda i: i.product_id)

    # Every sale line must already be fully allocated to shelf(s) it's
    # physically fulfilled from, and each named shelf must currently hold
    # enough of that product — checked before anything else is touched.
    for item in sorted_items:
        validate_allocations_complete(
            product_name=item.product.name,
            allocated=item.allocated_quantity,
            required=item.quantity,
        )
        validate_shelf_consumption(
            product=item.product,
            allocations=[{"shelf": a.shelf, "quantity": a.quantity} for a in item.shelf_allocations.all()],
        )

    for item in sorted_items:
        product = item.product

        # Final stock check inside transaction
        _validate_stock(product, item.quantity)

        # Snapshot selling price from rate list
        selling_price = _get_current_selling_price(product)

        # Run FIFO - consumes purchase batches, returns blended cogs/unit
        cogs_per_unit = _run_fifo(invoice_item=item, quantity=item.quantity, user=user)

        # Compute line financials using shared utils formula
        from .utils import calculate_line_item
        calc = calculate_line_item(
            quantity=item.quantity,
            selling_price=selling_price,
            discount=item.discount,
            gst=item.gst,
            wht=item.wht,
        )
        line_cogs   = cogs_per_unit * item.quantity
        line_profit = calc["line_total"] - line_cogs

        item.selling_price   = selling_price
        item.effective_price = calc["effective_price"]
        item.cogs_per_unit   = cogs_per_unit
        item.line_gross      = calc["line_gross"]
        item.line_gst_amount = calc["line_gst_amount"]
        item.line_wht_amount = calc["line_wht_amount"]
        item.line_total      = calc["line_total"]
        item.line_cogs       = line_cogs
        item.line_profit     = line_profit
        item.save(update_fields=[
            "selling_price", "effective_price", "cogs_per_unit",
            "line_gross", "line_gst_amount", "line_wht_amount",
            "line_total", "line_cogs", "line_profit",
        ])

        # Deduct from inventory (global) and the specific shelf(s) this sale
        # line is fulfilled from — through the shared writers so the
        # inventory stats counters and shelf ledger stay in sync.
        from purchases.services import apply_shelf_allocations, sync_inventory
        from purchases.models import ShelfStockMovement
        sync_inventory(product=product, quantity_delta=-item.quantity, user=user)
        apply_shelf_allocations(
            product=product,
            allocations=[{"shelf": a.shelf, "quantity": a.quantity} for a in item.shelf_allocations.all()],
            sign=-1, reason=ShelfStockMovement.Reason.SALE_CONSUMPTION,
            reference=invoice.bill_number, user=user,
        )

        # Stock Movement Report — bootstrap opening-balance invoices aren't
        # real sales, mirrors every other report's is_data_entry exclusion.
        if not invoice.is_data_entry:
            from purchases.services import _adjust_stock_movement
            _adjust_stock_movement(product_id=item.product_id, sold_delta=item.quantity)

    _recalculate_invoice_totals(invoice)

    invoice.status       = Invoice.Status.CONFIRMED
    invoice.confirmed_by = user
    invoice.confirmed_at = timezone.now()
    invoice.updated_by   = user
    invoice.save(update_fields=["status", "confirmed_by", "confirmed_at", "updated_by", "updated_at"])

    # Auto-credit the customer for whatever isn't already covered by an
    # advance payment. credit_outstanding starts at grand_total minus any
    # advance (advance was already collected at draft creation). Every
    # further payment received reduces this. remaining_amount mirrors it.
    invoice.refresh_from_db(fields=["grand_total", "advance_amount", "payment_type"])
    advance = invoice.advance_amount if invoice.payment_type == "advance" else Decimal("0")

    # Cap advance at grand_total (safety guard — advance was recorded
    # against the draft before line items/totals were locked in). The
    # underlying advance Payment row must be capped too, or a later call to
    # _sync_invoice_payment_summary would sum the uncapped Payment.amount
    # and silently raise cash_received/credit_outstanding back up.
    if advance > invoice.grand_total:
        uncapped_advance = advance
        advance = invoice.grand_total
        invoice.advance_amount = advance
        invoice.save(update_fields=["advance_amount"])

        advance_payment = Payment.objects.filter(
            invoice=invoice, note__startswith=ADVANCE_PAYMENT_NOTE,
            amount__gt=0, is_deleted=False,
        ).first()
        if advance_payment:
            advance_payment.amount = advance
            advance_payment.save(update_fields=["amount"])
            # The FULL uncapped advance went into cash_in_hand when the draft
            # was created (sync_invoice_advance_payment_created). Capping it
            # here used to update the invoice, the Payment row and the drawer
            # event but NOT the cash counter — so the capped-off difference
            # stayed in cash_in_hand permanently, silently, and unbounded
            # (a 5,000 advance on an order later reduced to 850 left cash
            # overstated by 4,150).
            #
            # Treated as "the advance was recorded wrong, correct it" rather
            # than "the customer overpaid and is owed a refund" — the same
            # treatment _update_advance_payment already applies when an
            # advance is edited down on a draft, so confirming is now
            # consistent with editing instead of being a special case.
            #
            # Paired with refresh_cash_movement inside the same
            # `if advance_payment` block and the same atomic transaction:
            # cash-in-hand.md requires an event and its cash sync to move
            # together. (No Payment row means the advance was already
            # reversed by sync_invoice_advance_payment_deleted, so syncing
            # again here would double-subtract.)
            from cash_flow.services import (
                refresh_cash_movement, sync_invoice_advance_payment_updated,
            )
            refresh_cash_movement(advance_payment)
            sync_invoice_advance_payment_updated(
                old_amount=uncapped_advance, new_amount=advance, user=user,
            )

            # Shrink the advance's method split to match, proportionally —
            # this is a system correction, not a user re-pick, so the
            # original split's proportions are preserved via prorate_splits
            # (largest-remainder rounding — the legs must sum to EXACTLY
            # `advance`, the same precision class as the earlier
            # "29,999.996" drift bug).
            from payment_methods.selectors import get_allocations_for_source
            from payment_methods.services import (
                prorate_splits, refresh_allocations, reverse_allocations,
            )
            current_legs = [
                (a.payment_method, a.amount)
                for a in get_allocations_for_source(advance_payment)
            ]
            prorated = prorate_splits(current_legs, advance)
            if prorated:
                refresh_allocations(
                    advance_payment, direction="inflow", splits=prorated,
                    total_amount=advance, date=advance_payment.payment_date, user=user,
                )
            else:
                reverse_allocations(advance_payment)

    credit_outstanding = max(Decimal("0"), invoice.grand_total - advance)
    invoice.cash_received      = advance
    invoice.total_paid         = advance
    invoice.credit_outstanding = credit_outstanding
    invoice.remaining_amount   = credit_outstanding
    invoice.payment_status = (
        Invoice.PaymentStatus.PAID if credit_outstanding == 0
        else Invoice.PaymentStatus.PARTIAL if advance > 0
        else Invoice.PaymentStatus.UNPAID
    )
    invoice.save(update_fields=[
        "cash_received", "total_paid", "credit_outstanding",
        "remaining_amount", "payment_status",
    ])

    # Sync CashFlow: customer owes (grand_total - advance); advance already in cash
    from cash_flow.services import sync_invoice_confirmed
    sync_invoice_confirmed(
        grand_total=invoice.grand_total, advance_amount=advance,
        total_cogs=invoice.total_cogs, gross_profit=invoice.gross_profit, user=user,
    )

    # Ledger entry: sale debit (customer owes us the full grand_total; any
    # advance already collected was separately credited at draft creation)
    from ledger.services import add_sale_entry
    add_sale_entry(
        customer=invoice.customer,
        invoice=invoice,
        amount=invoice.grand_total,
        date=timezone.localtime(invoice.confirmed_at).date(),
        user=user,
    )

    # Sync TaxFlow: GST charged to customer + WHT withheld by customer
    from taxes.services import sync_invoice_tax
    sync_invoice_tax(gst_amount=invoice.gst_total, wht_amount=invoice.wht_total, user=user)

    from credit_score.services import recalculate_credit_score
    recalculate_credit_score(
        customer_id=invoice.customer_id, user=user,
        trigger="invoice_confirmed", reference=invoice.bill_number,
    )

    return invoice


# ---------------------------------------------------------------------------
# Data-entry bootstrap invoice (called from data_entry.services)
# ---------------------------------------------------------------------------

@transaction.atomic
def create_opening_balance_invoice(*, customer, amount: Decimal, user) -> Invoice:
    """
    Creates a CONFIRMED, is_data_entry Invoice with no line items,
    grand_total = credit_outstanding = amount. Exists so normal billing
    payment APIs can work against the customer opening balance.

    IMPORTANT: this deliberately does NOT call sync_invoice_confirmed() or any
    other CashFlow sync. The CashFlow adjustment for a customer opening balance
    is handled separately by
    cash_flow.services.sync_data_entry_customer_opening_balance().

    Still gets the same +7-day payment_due_date default and counts toward
    the customer's credit score like any other confirmed invoice — opening
    balances are real carried-forward debt, not excluded from scoring.
    """
    confirmed_at = timezone.now()
    invoice = Invoice.objects.create(
        bill_number        = _generate_bill_number(),
        customer           = customer,
        status             = Invoice.Status.CONFIRMED,
        is_data_entry      = True,
        subtotal           = amount,
        grand_total        = amount,
        credit_outstanding = amount,
        remaining_amount   = amount,
        payment_status     = Invoice.PaymentStatus.UNPAID,
        payment_due_date   = timezone.localtime(confirmed_at).date() + timedelta(days=DEFAULT_DUE_DATE_DAYS),
        confirmed_by       = user,
        confirmed_at       = confirmed_at,
        created_by         = user,
        updated_by         = user,
    )

    from credit_score.services import recalculate_credit_score
    recalculate_credit_score(
        customer_id=invoice.customer_id, user=user,
        trigger="invoice_confirmed", reference=invoice.bill_number,
    )

    return invoice


# ---------------------------------------------------------------------------
# Payment services
# ---------------------------------------------------------------------------

@transaction.atomic
def create_payment(
    *, invoice_id: int, amount: Decimal,
    method_allocations: list, payment_date, note: str = "", user,
) -> Payment:
    from rest_framework.exceptions import ValidationError

    invoice = get_invoice_by_id(invoice_id)
    if invoice.status == Invoice.Status.DRAFT:
        raise ValidationError({"invoice": "Cannot record payment on a draft invoice."})

    # Prevent overpayment — compare against current credit_outstanding
    invoice.refresh_from_db(fields=["credit_outstanding"])
    if amount > invoice.credit_outstanding:
        raise ValidationError({
            "amount": (
                f"Payment of {amount} exceeds outstanding credit balance. "
                f"Credit outstanding: {invoice.credit_outstanding}."
            )
        })

    from payment_methods.services import derive_legacy_method_label, record_allocations

    payment = Payment.objects.create(
        invoice=invoice,
        reference_number=_generate_payment_reference(),
        amount=amount,
        method=derive_legacy_method_label(method_allocations),
        payment_date=payment_date,
        note=note,
        created_by=user,
        updated_by=user,
    )
    _sync_invoice_payment_summary(invoice)

    # Sync CashFlow: cash in hand increases, customer outstanding decreases
    from cash_flow.services import record_cash_movement, sync_invoice_payment_received
    sync_invoice_payment_received(amount=amount, user=user)
    record_allocations(
        payment, direction="inflow", splits=method_allocations,
        total_amount=amount, date=payment_date, user=user,
    )
    record_cash_movement(payment)

    # Ledger entry: payment credit (customer owes us less)
    from ledger.services import add_customer_payment_entry
    add_customer_payment_entry(
        customer=invoice.customer, payment=payment,
        amount=amount, date=payment.payment_date, user=user,
    )

    from credit_score.services import recalculate_credit_score
    recalculate_credit_score(
        customer_id=invoice.customer_id, user=user,
        trigger="payment_received", reference=invoice.bill_number,
    )

    return payment


@transaction.atomic
def delete_payment(*, payment_id: int, user) -> None:
    payment = get_payment_by_id(payment_id)
    invoice = payment.invoice
    amount  = payment.amount
    _soft_delete(payment, user)
    _sync_invoice_payment_summary(invoice)

    # Reverse CashFlow sync only for positive payments (not credit notes)
    from cash_flow.services import reverse_cash_movement, sync_invoice_payment_deleted
    sync_invoice_payment_deleted(amount=amount, user=user)
    reverse_cash_movement(payment)  # no-op for credit notes (never recorded)

    from payment_methods.services import reverse_allocations
    reverse_allocations(payment)  # no-op for credit notes (never allocated)

    # Reverse ledger entry — no-op for credit-note payments, which were
    # never given a payment-linked entry (they're tracked via the Return
    # instead, see accept_return).
    from ledger.services import remove_customer_ledger_entry_for_payment
    remove_customer_ledger_entry_for_payment(payment=payment)

    from credit_score.services import recalculate_credit_score
    recalculate_credit_score(
        customer_id=invoice.customer_id, user=user,
        trigger="payment_deleted", reference=invoice.bill_number,
    )


# ---------------------------------------------------------------------------
# Return services
# ---------------------------------------------------------------------------

@transaction.atomic
def create_return(*, invoice_id: int, items: list[dict], note: str = "", user) -> Return:
    """
    Creates a PENDING return request.
    items = [{"invoice_item_id": 1, "quantity": 3}, ...]
    Validates quantities don't exceed returnable amounts.
    Does NOT touch inventory or FIFO yet — that happens on acceptance.
    """
    from rest_framework.exceptions import ValidationError

    invoice = get_invoice_by_id(invoice_id)
    if invoice.status not in (Invoice.Status.CONFIRMED, Invoice.Status.PARTIAL):
        raise ValidationError({"invoice": "Only confirmed invoices can have returns."})

    if not items:
        raise ValidationError({"items": "At least one item is required for a return."})

    return_record = Return.objects.create(
        invoice=invoice,
        reference_number=_generate_return_reference(),
        status=Return.Status.PENDING,
        note=note,
        created_by=user,
        updated_by=user,
    )

    for item_data in items:
        invoice_item = get_invoice_item_by_id(item_data["invoice_item_id"])

        if invoice_item.invoice_id != invoice.id:
            raise ValidationError({
                "invoice_item_id": f"Item {invoice_item.id} does not belong to this invoice."
            })
        if item_data["quantity"] > invoice_item.returnable_quantity:
            raise ValidationError({
                "quantity": (
                    f"Cannot return {item_data['quantity']} units of "
                    f"'{invoice_item.product.name}'. "
                    f"Returnable: {invoice_item.returnable_quantity}."
                )
            })

        qty           = item_data["quantity"]
        selling_price = invoice_item.selling_price
        cogs_per_unit = invoice_item.cogs_per_unit
        ReturnItem.objects.create(
            return_record=return_record,
            invoice_item=invoice_item,
            quantity=qty,
            selling_price=selling_price,
            cogs_per_unit=cogs_per_unit,
            line_total=selling_price * qty,
            line_cogs=cogs_per_unit * qty,
        )

    return return_record


@transaction.atomic
def update_return_items(*, return_id: int, items: list[dict], note: str = None, user) -> Return:
    """
    Replaces all line items on a PENDING return. Mirrors create_return's
    item-building exactly (same selling_price/cogs_per_unit snapshot), but
    against the old ReturnItem rows deleted first — cascading their
    shelf_allocations, since those are keyed to the specific item row. A
    return has no side effects until accepted, so there's nothing to
    reverse here; the user re-allocates shelves for the new lines
    afterward, same as when a return is first created.
    """
    from rest_framework.exceptions import ValidationError

    return_record = get_return_by_id(return_id)
    if return_record.status != Return.Status.PENDING:
        raise ValidationError({"status": "Only pending returns can be edited."})

    if not items:
        raise ValidationError({"items": "At least one item is required for a return."})

    return_record.items.all().delete()
    for item_data in items:
        invoice_item = get_invoice_item_by_id(item_data["invoice_item_id"])

        if invoice_item.invoice_id != return_record.invoice_id:
            raise ValidationError({
                "invoice_item_id": f"Item {invoice_item.id} does not belong to this invoice."
            })
        if item_data["quantity"] > invoice_item.returnable_quantity:
            raise ValidationError({
                "quantity": (
                    f"Cannot return {item_data['quantity']} units of "
                    f"'{invoice_item.product.name}'. "
                    f"Returnable: {invoice_item.returnable_quantity}."
                )
            })

        qty           = item_data["quantity"]
        selling_price = invoice_item.selling_price
        cogs_per_unit = invoice_item.cogs_per_unit
        ReturnItem.objects.create(
            return_record=return_record,
            invoice_item=invoice_item,
            quantity=qty,
            selling_price=selling_price,
            cogs_per_unit=cogs_per_unit,
            line_total=selling_price * qty,
            line_cogs=cogs_per_unit * qty,
        )

    if note is not None:
        return_record.note = note
    return_record.updated_by = user
    return_record.save(update_fields=["note", "updated_by", "updated_at"])
    return return_record


def cancel_return(*, return_id: int, user) -> None:
    """
    Cancels a PENDING return — soft delete. A return has no side effects
    until accepted (no inventory/FIFO/payment change happens at
    creation), so cancelling is purely "this never happened." The invoice
    and its items are untouched, and the user is free to create another
    return against the same invoice afterward (returnable_quantity is
    computed from returned_quantity, which a pending-then-cancelled
    return never incremented).
    """
    from rest_framework.exceptions import ValidationError

    return_record = get_return_by_id(return_id)
    if return_record.status != Return.Status.PENDING:
        raise ValidationError({"status": "Only pending returns can be cancelled."})

    _soft_delete(return_record, user)


@transaction.atomic
def accept_return(*, return_id: int, user) -> Return:
    """
    Accepts a pending return (admin/superuser only):
    1. Snapshots prices from original invoice item
    2. Reverses FIFO (restores purchase batch remaining_quantity)
    3. Increments inventory
    4. Updates returned_quantity on invoice items
    5. Updates invoice status (partial/returned)
    6. Adjusts invoice totals
    7. Creates a negative payment entry to reduce customer's outstanding balance
    """
    from rest_framework.exceptions import ValidationError

    return_record = get_return_by_id(return_id)
    if return_record.status != Return.Status.PENDING:
        raise ValidationError({"status": "Only pending returns can be accepted."})

    # Sorted by product_id (mirrors confirm_invoice) so two concurrent
    # accepts touching overlapping shelves always lock in the same order.
    return_items = sorted(return_record.items.all(), key=lambda ri: ri.invoice_item.product_id)

    from purchases.services import validate_allocations_complete

    # Every returned line must be fully allocated to the shelf(s) it's put
    # away on before we touch stock — any shelf is valid (put-away), no
    # availability check needed.
    for return_item in return_items:
        validate_allocations_complete(
            product_name=return_item.invoice_item.product.name,
            allocated=return_item.allocated_quantity,
            required=return_item.quantity,
        )

    total_return_amount = Decimal("0")
    total_return_cogs   = Decimal("0")

    for return_item in return_items:
        invoice_item  = return_item.invoice_item
        qty           = return_item.quantity

        # Snapshot from original invoice item
        selling_price = invoice_item.selling_price
        cogs_per_unit = invoice_item.cogs_per_unit
        line_total    = selling_price * qty
        line_cogs     = cogs_per_unit * qty

        return_item.selling_price = selling_price
        return_item.cogs_per_unit = cogs_per_unit
        return_item.line_total    = line_total
        return_item.line_cogs     = line_cogs
        return_item.save(update_fields=[
            "selling_price", "cogs_per_unit", "line_total", "line_cogs"
        ])

        # Reverse FIFO and restore inventory (global), then put the returned
        # quantity away on the shelf(s) the user chose (any shelf is valid).
        _reverse_fifo(invoice_item=invoice_item, return_quantity=qty)
        from purchases.services import apply_shelf_allocations
        from purchases.models import ShelfStockMovement
        apply_shelf_allocations(
            product=invoice_item.product,
            allocations=[{"shelf": a.shelf, "quantity": a.quantity} for a in return_item.shelf_allocations.all()],
            sign=1, reason=ShelfStockMovement.Reason.INVOICE_RETURN_PUTAWAY,
            reference=return_record.reference_number, user=user,
        )

        # Track returned quantity on invoice item
        invoice_item.returned_quantity += qty
        invoice_item.save(update_fields=["returned_quantity"])

        # Stock Movement Report
        if not invoice_item.invoice.is_data_entry:
            from purchases.services import _adjust_stock_movement
            _adjust_stock_movement(product_id=invoice_item.product_id, sale_returned_delta=qty)

        total_return_amount += line_total
        total_return_cogs   += line_cogs

    # Save return totals
    return_record.total_return_amount = total_return_amount
    return_record.total_return_cogs   = total_return_cogs
    return_record.status              = Return.Status.ACCEPTED
    return_record.accepted_by         = user
    return_record.accepted_at         = timezone.now()
    return_record.updated_by          = user
    return_record.save(update_fields=[
        "total_return_amount", "total_return_cogs",
        "status", "accepted_by", "accepted_at", "updated_by", "updated_at",
    ])

    # Update invoice status
    invoice = return_record.invoice
    all_items      = invoice.items.all()
    total_qty      = sum(i.quantity for i in all_items)
    total_returned = sum(i.returned_quantity for i in all_items)

    if total_returned >= total_qty:
        invoice.status = Invoice.Status.RETURNED
    else:
        invoice.status = Invoice.Status.PARTIAL

    invoice.updated_by = user
    invoice.save(update_fields=["status", "updated_by", "updated_at"])

    # Recalculate invoice totals
    _recalculate_invoice_totals(invoice)

    # Credit note: negative payment entry to reduce outstanding balance
    Payment.objects.create(
        invoice=invoice,
        reference_number=_generate_payment_reference(),
        amount=-total_return_amount,
        method=Payment.Method.CASH,  # credit note — reduces customer outstanding
        payment_date=timezone.localtime(timezone.now()).date(),
        note=f"Auto credit note for Return {return_record.reference_number}",
        created_by=user,
        updated_by=user,
    )
    _sync_invoice_payment_summary(invoice)

    # Sync CashFlow: customer outstanding reduces, total_customer_returns_value/cogs increase
    from cash_flow.services import sync_invoice_return_accepted
    sync_invoice_return_accepted(
        return_amount=total_return_amount, return_cogs=total_return_cogs, user=user,
    )

    # Ledger entry: return credit (reduces what the customer owes) — linked
    # to the Return itself, not the auto-generated negative credit-note
    # Payment above (that Payment is written directly via .objects.create(),
    # never through create_payment(), so it never double-fires this hook).
    from ledger.services import add_customer_return_entry
    add_customer_return_entry(
        customer=invoice.customer,
        customer_return=return_record,
        amount=total_return_amount,
        date=timezone.localtime(return_record.accepted_at).date(),
        user=user,
    )

    from credit_score.services import recalculate_credit_score
    recalculate_credit_score(
        customer_id=invoice.customer_id, user=user,
        trigger="return_accepted", reference=return_record.reference_number,
    )

    return return_record