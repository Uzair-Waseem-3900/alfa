from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import (
    CustomerOpeningBalance, OpeningCashEntry, SupplierOpeningBalance,
)


# ---------------------------------------------------------------------------
# Feature 1 — Supplier Opening Balance
# ---------------------------------------------------------------------------

@transaction.atomic
def create_supplier_opening_balance(*, supplier_id: int, amount: Decimal, note: str = "", user) -> SupplierOpeningBalance:
    """
    One-time opening balance for a supplier (what we owed before go-live).
    Permanently locked after creation. Touches:
        - PurchaseOrder  : confirmed, is_data_entry=True, net_payable=amount
        - CashFlow       : supplier_payable_outstanding += amount, total_purchases_cash += amount
        - SupplierLedger : ONE opening_balance credit entry
        - SupplierOpeningBalance record
    """
    from purchases.selectors import get_supplier_by_id
    from purchases.services import create_opening_balance_order
    from cash_flow.services import sync_data_entry_supplier_opening_balance
    from ledger.services import add_opening_balance_entry

    supplier = get_supplier_by_id(supplier_id)   # 404 if missing / soft-deleted

    if amount is None or amount <= 0:
        raise ValidationError({"amount": "Amount must be greater than zero."})
    if SupplierOpeningBalance.objects.filter(supplier=supplier).exists():
        raise ValidationError({"supplier": "This supplier already has an opening balance."})

    order = create_opening_balance_order(supplier=supplier, amount=amount, user=user)

    sync_data_entry_supplier_opening_balance(amount=amount, user=user)

    add_opening_balance_entry(
        supplier=supplier,
        amount=amount,
        date=timezone.localtime(timezone.now()).date(),
        reference=f"OB-{supplier.code}",
        details="Opening Balance",
        user=user,
    )

    try:
        # Savepoint: the OneToOneField already guarantees at most one
        # opening balance per supplier at the DB level — this converts a
        # rare check-then-act race (two near-simultaneous creates for the
        # same supplier) into the same friendly ValidationError the .exists()
        # check above raises, instead of an unhandled IntegrityError (500).
        with transaction.atomic():
            return SupplierOpeningBalance.objects.create(
                supplier=supplier, amount=amount, note=note or "",
                purchase_order=order, created_by=user,
            )
    except IntegrityError:
        raise ValidationError({"supplier": "This supplier already has an opening balance."})


# ---------------------------------------------------------------------------
# Feature 2 — Customer Opening Balance
# ---------------------------------------------------------------------------

@transaction.atomic
def create_customer_opening_balance(*, customer_id: int, amount: Decimal, note: str = "", user) -> CustomerOpeningBalance:
    """
    One-time opening balance for a customer (what they owed before go-live).
    Permanently locked after creation. Touches:
        - Invoice  : confirmed, is_data_entry=True, grand_total=amount, credit_outstanding=amount
        - CashFlow : customer_outstanding += amount ONLY (no cash received)
        - CustomerOpeningBalance record

    NOTE: create_opening_balance_invoice() creates the Invoice directly and does
    NOT run any CashFlow sync. The single CashFlow adjustment is performed here
    via sync_data_entry_customer_opening_balance().
    """
    from billing.selectors import get_customer_by_id
    from billing.services import create_opening_balance_invoice
    from cash_flow.services import sync_data_entry_customer_opening_balance
    from ledger.services import add_customer_opening_balance_entry

    customer = get_customer_by_id(customer_id)   # 404 if missing / soft-deleted

    if amount is None or amount <= 0:
        raise ValidationError({"amount": "Amount must be greater than zero."})
    if CustomerOpeningBalance.objects.filter(customer=customer).exists():
        raise ValidationError({"customer": "This customer already has an opening balance."})

    invoice = create_opening_balance_invoice(customer=customer, amount=amount, user=user)

    sync_data_entry_customer_opening_balance(amount=amount, user=user)

    add_customer_opening_balance_entry(
        customer=customer,
        invoice=invoice,
        amount=amount,
        date=timezone.localtime(timezone.now()).date(),
        reference=f"OB-{customer.code}",
        details="Opening Balance",
        user=user,
    )

    try:
        # Same IntegrityError guard as create_supplier_opening_balance —
        # the OneToOneField already prevents a real duplicate; this just
        # keeps a rare check-then-act race from surfacing as a 500.
        with transaction.atomic():
            return CustomerOpeningBalance.objects.create(
                customer=customer, amount=amount, note=note or "",
                invoice=invoice, created_by=user,
            )
    except IntegrityError:
        raise ValidationError({"customer": "This customer already has an opening balance."})


# ---------------------------------------------------------------------------
# Feature 3 — Opening Cash
# ---------------------------------------------------------------------------

@transaction.atomic
def create_opening_cash(*, amount: Decimal, user) -> OpeningCashEntry:
    """
    Seeds starting cash on hand. Can be called multiple times.
        - CashFlow : cash_in_hand += amount, total_invoices_cash += amount
        - OpeningCashEntry record (shown in cash-in-hand breakdown as an inflow)

    No method picker here (unlike every other Phase 5 source) — this is a
    one-time store-setup bootstrap that runs before any real accounts exist
    to choose from, so it lands on the protected Cash account automatically,
    same as a profit reinvest's silent legs.
    """
    from cash_flow.services import sync_data_entry_opening_cash

    if amount is None or amount <= 0:
        raise ValidationError({"amount": "Amount must be greater than zero."})

    entry = OpeningCashEntry.objects.create(amount=amount, added_by=user)
    sync_data_entry_opening_cash(amount=amount, user=user)

    from cash_flow.services import record_cash_movement
    record_cash_movement(entry)

    from payment_methods.models import PaymentMethod
    from payment_methods.services import record_allocations
    cash, _ = PaymentMethod.objects.get_or_create(name="Cash", defaults={"is_protected": True})
    record_allocations(
        entry, direction="inflow", splits=[(cash, amount)],
        total_amount=amount, date=entry.added_at.date(), user=user,
    )

    return entry


# ---------------------------------------------------------------------------
# Feature 4 — Opening Stock
# ---------------------------------------------------------------------------

@transaction.atomic
def create_opening_stock(*, items: list, user):
    """
    Adds opening stock for multiple products via the system supplier.
    Can be called multiple times.
        - PurchaseOrder : confirmed, is_data_entry=True, supplier=SYS-OPENING
        - PurchaseItem  : one per product, remaining_quantity=quantity (FIFO ready)
        - Inventory     : quantity += amount per product
        - ShelfStock    : quantity += amount on the shelf chosen for that item
        - CashFlow      : NO change (not a financial transaction)

    Each item dict MUST include a `shelf_id` (the shelf the caller chose for
    that product's opening stock) — forwarded as-is to
    purchases.services.create_opening_stock_order, which requires it and
    raises ValidationError if missing. No default is invented here; the
    user must pick a shelf for every item.
    """
    from purchases.models import Supplier
    from purchases.selectors import get_product_by_id
    from purchases.services import create_opening_stock_order

    system_supplier = Supplier.objects.filter(code="SYS-OPENING", is_deleted=False).first()
    if not system_supplier:
        raise ValidationError({
            "system_supplier": "System supplier not found. Run "
                               "`python manage.py create_system_supplier` first.",
        })

    if not items:
        raise ValidationError({"items": "At least one item is required."})

    seen_products = set()
    for item in items:
        product_id = item["product_id"]
        if product_id in seen_products:
            raise ValidationError({"items": f"Duplicate product id {product_id}."})
        seen_products.add(product_id)
        get_product_by_id(product_id)   # 404 if missing / soft-deleted
        if item["quantity"] <= 0:
            raise ValidationError({"quantity": "Quantity must be greater than zero."})
        if item["unit_price"] <= 0:
            raise ValidationError({"unit_price": "Unit price must be greater than zero."})

    return create_opening_stock_order(supplier=system_supplier, items=items, user=user)


# ---------------------------------------------------------------------------
# Feature 5 — Opening Investor Investment
# ---------------------------------------------------------------------------

@transaction.atomic
def create_opening_investor_investment(*, investor_id: int, amount: Decimal, note: str = "", user):
    """
    Records capital an investor put in BEFORE this system existed — the cash
    isn't sitting in the till (already spent, or never tracked here), so
    unlike a normal investment it must NOT move CashFlow.cash_in_hand.
    Can be called multiple times per investor (no uniqueness constraint,
    same as Opening Cash / Opening Stock).
        - Investor            : total_invested/net_stake/current_worth += amount
        - CashManagementFlow  : total_investor_capital/net_worth += amount
        - InvestorTransaction : type=investment, is_data_entry=True
        - CashFlow            : NO change (not a real cash movement)

    Stored as a flagged InvestorTransaction in cash_management (not a
    data_entry-owned model) so the record survives if this app is ever
    removed post-go-live — same reasoning as Feature 4 (Opening Stock).
    """
    from cash_management.models import InvestorTransaction
    from cash_management.services import create_investor_transaction

    if amount is None or amount <= 0:
        raise ValidationError({"amount": "Amount must be greater than zero."})

    return create_investor_transaction(
        investor_id=investor_id,
        transaction_type=InvestorTransaction.TransactionType.INVESTMENT,
        amount=amount,
        transaction_date=timezone.localtime(timezone.now()).date(),
        note=note or "Opening investor investment (data entry)",
        user=user,
        is_data_entry=True,
    )
