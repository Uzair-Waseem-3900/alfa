from decimal import Decimal
from django.conf import settings
from django.db import models

from .utils import calculate_total_price


# ---------------------------------------------------------------------------
# Shared managers
# ---------------------------------------------------------------------------

class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class AllObjectsManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset()


# ---------------------------------------------------------------------------
# Audit mixin — full trail + soft delete on every model
# ---------------------------------------------------------------------------

class AuditMixin(models.Model):
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="%(class)s_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="%(class)s_updated",
    )
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="%(class)s_deleted",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False, db_index=True)

    objects     = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# Lookup tables
# ---------------------------------------------------------------------------

class Category(AuditMixin):
    name        = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, default="")

    class Meta:
        verbose_name        = "Category"
        verbose_name_plural = "Categories"
        ordering            = ["name"]

    def __str__(self):
        return self.name


class Shelf(AuditMixin):
    name        = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, default="")

    class Meta:
        verbose_name        = "Shelf"
        verbose_name_plural = "Shelves"
        ordering            = ["name"]

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Supplier
# ---------------------------------------------------------------------------

class Supplier(AuditMixin):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name        = "Supplier"
        verbose_name_plural = "Suppliers"
        ordering            = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------

class Product(AuditMixin):
    name     = models.CharField(max_length=255)
    code     = models.CharField(max_length=100, unique=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")

    class Meta:
        verbose_name        = "Product"
        verbose_name_plural = "Products"
        ordering            = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


# ---------------------------------------------------------------------------
# Purchase Order (header) — renamed from Purchase
# ---------------------------------------------------------------------------

class PurchaseOrder(AuditMixin):
    """
    Header of a purchase. Mirrors billing.Invoice.
    Draft → no inventory/debt effect.
    Confirmed → inventory increases, supplier debt auto-created.
    """

    class Status(models.TextChoices):
        DRAFT     = "draft",     "Draft"
        CONFIRMED = "confirmed", "Confirmed"

    class PaymentStatus(models.TextChoices):
        UNPAID  = "unpaid",  "Unpaid"
        PARTIAL = "partial", "Partial"
        PAID    = "paid",    "Paid"

    class PaymentType(models.TextChoices):
        ADVANCE        = "advance",        "Advance Payment"
        AFTER_DELIVERY = "after_delivery", "Payment After Delivery"

    order_number = models.CharField(max_length=30, unique=True, editable=False)
    supplier     = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchase_orders")
    # Overrides AuditMixin.created_at to add an index — every order list view
    # sorts by -created_at and filters by date range, so without this the DB
    # re-sorts the whole table on each request. Same pattern as
    # LostInventoryRecord.created_at.
    created_at   = models.DateTimeField(auto_now_add=True, db_index=True)
    is_data_entry = models.BooleanField(
        default=False, db_index=True,
        help_text="True for bootstrap opening-balance / opening-stock orders. Hidden from normal list views.",
    )
    status       = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    description  = models.TextField(blank=True, default="", help_text="Optional notes about this purchase order.")
    payment_type = models.CharField(
        max_length=20, choices=PaymentType.choices,
        default=PaymentType.AFTER_DELIVERY,
        help_text="Advance payment or payment after delivery.",
    )
    advance_amount = models.DecimalField(
        max_digits=18, decimal_places=4, default=0,
        help_text=(
            "Amount paid in advance (only when payment_type=advance). "
            "Immediately deducted from cash_in_hand on draft creation. "
            "Capped at net_payable on confirmation."
        ),
    )

    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="confirmed_purchase_orders",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True, db_index=True)

    # Totals — computed and stored on confirmation
    gross_amount = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    gst_total    = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    wht_total    = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    net_payable  = models.DecimalField(max_digits=18, decimal_places=4, default=0)

    # Supplier payable tracking — updated on every payment / return
    payable_outstanding = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    total_paid          = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    payment_status      = models.CharField(
        max_length=10, choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID, db_index=True,
    )

    class Meta:
        verbose_name        = "Purchase Order"
        verbose_name_plural = "Purchase Orders"
        ordering            = ["-created_at"]

    def __str__(self):
        return self.order_number


# ---------------------------------------------------------------------------
# Purchase Item (line item) — renamed from Purchase
# ---------------------------------------------------------------------------

class PurchaseItem(AuditMixin):
    """
    One line item inside a PurchaseOrder.
    remaining_quantity tracks FIFO consumption from billing.
    All financial fields auto-calculated on save.
    """

    order      = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="items")
    product    = models.ForeignKey(Product,       on_delete=models.PROTECT, related_name="purchase_items")
    quantity   = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=14, decimal_places=4)
    gst        = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                     help_text="GST percentage e.g. 18.5 means 18.5%")
    wht        = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                     help_text="WHT percentage e.g. 1.5 means 1.5%")
    description = models.TextField(blank=True, default="", help_text="Optional description for this line item.")

    # Auto-calculated — never entered by user
    gross_amount = models.DecimalField(max_digits=18, decimal_places=4, default=0, editable=False)
    gst_amount   = models.DecimalField(max_digits=18, decimal_places=4, default=0, editable=False)
    wht_amount   = models.DecimalField(max_digits=18, decimal_places=4, default=0, editable=False)
    total_price  = models.DecimalField(max_digits=18, decimal_places=4, default=0, editable=False)

    # FIFO tracking — set on confirmation, consumed by billing
    remaining_quantity = models.PositiveIntegerField(default=0)

    # Tracks how much of this line has been returned to supplier
    returned_quantity = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name        = "Purchase Item"
        verbose_name_plural = "Purchase Items"
        unique_together     = [("order", "product")]
        ordering            = ["id"]

    @property
    def allocated_quantity(self):
        # Sums the in-memory prefetch cache when the caller prefetched
        # shelf_allocations (the normal list/detail path) — .aggregate()
        # would bypass that cache and re-query per item (N+1).
        return sum(a.quantity for a in self.shelf_allocations.all())

    def save(self, *args, **kwargs):
        result = calculate_total_price(
            quantity=self.quantity,
            unit_price=self.unit_price,
            gst=self.gst,
            wht=self.wht,
        )
        self.gross_amount = result["gross_amount"]
        self.gst_amount   = result["gst_amount"]
        self.wht_amount   = result["wht_amount"]
        self.total_price  = result["total_price"]
        # Set remaining_quantity on first creation only (confirmation sets it via service)
        super().save(*args, **kwargs)

    @property
    def returnable_quantity(self):
        # Bounded by remaining_quantity, not just quantity - returned_quantity
        # — you can only return to the supplier what's still physically in
        # stock. A unit already sold to a customer or lost isn't returnable
        # to the supplier just because it hasn't been "returned" before.
        return min(self.quantity - self.returned_quantity, self.remaining_quantity)

    def __str__(self):
        return f"{self.order.order_number} — {self.product.name}"


class PurchaseItemShelfAllocation(models.Model):
    """
    Draft put-away plan for one PurchaseItem: which shelf(s) the purchased
    quantity will land on once the order is confirmed. Purely planning state
    until confirm_purchase_order runs — nothing is applied to ShelfStock
    until then. confirm_purchase_order blocks unless every item's
    allocations sum exactly to its quantity. Any shelf is allowed (put-away).
    """
    purchase_item = models.ForeignKey(PurchaseItem, on_delete=models.CASCADE, related_name="shelf_allocations")
    shelf         = models.ForeignKey(Shelf, on_delete=models.PROTECT, related_name="purchase_item_allocations")
    quantity      = models.PositiveIntegerField()
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "Purchase Item Shelf Allocation"
        verbose_name_plural = "Purchase Item Shelf Allocations"
        unique_together     = [("purchase_item", "shelf")]

    def __str__(self):
        return f"{self.purchase_item} → {self.shelf.name}: {self.quantity}"


# ---------------------------------------------------------------------------
# Purchase Return
# ---------------------------------------------------------------------------

class PurchaseReturn(AuditMixin):
    """
    Return of goods to supplier. Always a new record — previous PurchaseOrder untouched.
    Accepted only by admin/superuser.
    On acceptance:
        - Inventory decreases (FIFO reversal on remaining_quantity)
        - Supplier payable_outstanding decreases
    """

    class Status(models.TextChoices):
        PENDING  = "pending",  "Pending"
        ACCEPTED = "accepted", "Accepted"

    order            = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name="returns")
    reference_number = models.CharField(max_length=30, unique=True, editable=False,
                        #    default="", blank=True,
                           help_text="Auto-generated e.g. RTN-2026-0001")
    status           = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    note             = models.TextField(blank=True, default="")
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="accepted_purchase_returns",
    )
    accepted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    # Overrides AuditMixin.created_at to add an index — the returns list sorts
    # by -created_at and filters by date range. Same pattern as PurchaseOrder.
    created_at  = models.DateTimeField(auto_now_add=True, db_index=True)

    # Totals — computed on acceptance
    total_return_gross  = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    total_return_gst    = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    total_return_wht    = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    total_return_amount = models.DecimalField(max_digits=18, decimal_places=4, default=0)

    class Meta:
        verbose_name        = "Purchase Return"
        verbose_name_plural = "Purchase Returns"
        ordering            = ["-created_at"]

    def __str__(self):
        return f"Return for {self.order.order_number}"


class PurchaseReturnItem(models.Model):
    """
    One line item per product being returned in a PurchaseReturn.
    GST and WHT are optional (default 0) on return items.
    """

    return_record  = models.ForeignKey(PurchaseReturn, on_delete=models.CASCADE, related_name="items")
    purchase_item  = models.ForeignKey(PurchaseItem,   on_delete=models.PROTECT, related_name="return_items")
    quantity       = models.PositiveIntegerField()
    gst            = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                         help_text="GST on return (optional, default 0)")
    wht            = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                         help_text="WHT on return (optional, default 0)")

    # Snapshotted on acceptance from original purchase item
    unit_price   = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    gross_amount = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    gst_amount   = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    wht_amount   = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    total_amount = models.DecimalField(max_digits=18, decimal_places=4, default=0)

    class Meta:
        verbose_name        = "Purchase Return Item"
        verbose_name_plural = "Purchase Return Items"
        unique_together     = [("return_record", "purchase_item")]

    def __str__(self):
        return f"{self.return_record} — {self.purchase_item.product.name} x {self.quantity}"

    @property
    def allocated_quantity(self):
        # Sums the in-memory prefetch cache when the caller prefetched
        # shelf_allocations (the normal list/detail path) — .aggregate()
        # would bypass that cache and re-query per item (N+1).
        return sum(a.quantity for a in self.shelf_allocations.all())


class PurchaseReturnItemShelfAllocation(models.Model):
    """
    Draft plan for which shelf(s) the returned-to-supplier quantity is
    physically pulled from. Consumption, not put-away — only shelves that
    currently hold stock of this product are valid choices (enforced by the
    selector that lists candidate shelves + the service-layer quantity
    check). accept_purchase_return blocks unless every item's allocations
    sum exactly to its quantity.
    """
    return_item = models.ForeignKey(PurchaseReturnItem, on_delete=models.CASCADE, related_name="shelf_allocations")
    shelf       = models.ForeignKey(Shelf, on_delete=models.PROTECT, related_name="purchase_return_item_allocations")
    quantity    = models.PositiveIntegerField()
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "Purchase Return Item Shelf Allocation"
        verbose_name_plural = "Purchase Return Item Shelf Allocations"
        unique_together     = [("return_item", "shelf")]

    def __str__(self):
        return f"{self.return_item} ← {self.shelf.name}: {self.quantity}"


# ---------------------------------------------------------------------------
# Lost Inventory
# ---------------------------------------------------------------------------

class LostInventoryRecord(AuditMixin):
    """
    A batch event where one or more products are marked as lost from inventory
    (damaged, expired, stolen, misplaced, etc.). Takes effect immediately on
    creation — unlike PurchaseReturn there is no pending/accept step.

    On creation:
        - Cost per unit is snapshotted from FIFO purchase batches (same
          costing logic as billing._run_fifo).
        - Inventory decreases immediately.
    """

    reference_number = models.CharField(max_length=30, unique=True, editable=False,
                           help_text="Auto-generated e.g. LOSS-2026-0001")
    note = models.TextField(blank=True, default="", help_text="Optional overall note for this batch.")

    # Computed and stored on creation
    total_lost_amount = models.DecimalField(max_digits=18, decimal_places=4, default=0)

    # Overrides AuditMixin.created_at to add an index — this is the field the
    # Lost Inventory report filters/orders by. PurchaseOrder and PurchaseReturn
    # carry the same override; AuditMixin's other users (Category, Shelf,
    # Supplier, Product, SupplierPayment) stay unindexed on purpose.
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name        = "Lost Inventory Record"
        verbose_name_plural = "Lost Inventory Records"
        ordering            = ["-created_at"]

    def __str__(self):
        return self.reference_number


class LostInventoryItem(models.Model):
    """
    One product lost within a LostInventoryRecord.
    unit_cost is the blended FIFO cost snapshotted at creation time — immutable.

    found_quantity tracks how much of this line has since been marked "found"
    (product turned up again) via mark_lost_inventory_found — supports partial
    recovery across multiple separate find events, mirroring the
    quantity/returned_quantity pattern already used on PurchaseItem/InvoiceItem.
    """

    record   = models.ForeignKey(LostInventoryRecord, on_delete=models.CASCADE, related_name="items")
    product  = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="lost_inventory_items")
    quantity = models.PositiveIntegerField()
    reason   = models.CharField(max_length=255, blank=True, default="",
                   help_text="Optional reason e.g. damaged, expired, stolen, misplaced.")

    # Snapshotted from FIFO purchase batches at creation
    unit_cost  = models.DecimalField(max_digits=14, decimal_places=4, default=0, editable=False)
    total_cost = models.DecimalField(max_digits=18, decimal_places=4, default=0, editable=False)

    # How much of this loss has been reversed via "mark as found"
    found_quantity = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name        = "Lost Inventory Item"
        verbose_name_plural = "Lost Inventory Items"
        unique_together     = [("record", "product")]

    @property
    def returnable_quantity(self):
        return self.quantity - self.found_quantity

    @property
    def recovered_amount(self):
        return self.unit_cost * self.found_quantity

    @property
    def net_amount(self):
        return self.total_cost - self.recovered_amount

    def __str__(self):
        return f"{self.record.reference_number} — {self.product.name} x {self.quantity}"


class LostInventoryRecovery(models.Model):
    """
    One row per "mark as found" action — the dated counterpart to
    LostInventoryItem.found_quantity (which is just a running counter with
    no timestamp). This is what lets the Monthly Profit report correctly
    attribute a recovery to the month it ACTUALLY happened in, instead of
    silently folding it into the month the original loss was recorded in
    (which breaks once that month is already finalized/frozen).

    recovered_amount is snapshotted at creation (unit_cost × quantity for
    that specific find event) — immutable, same "snapshot at lock-in"
    convention as everything else in this app.
    """
    lost_item        = models.ForeignKey(LostInventoryItem, on_delete=models.CASCADE, related_name="recoveries")
    quantity          = models.PositiveIntegerField()
    recovered_amount  = models.DecimalField(max_digits=18, decimal_places=4, editable=False)
    recovered_at      = models.DateField(db_index=True)
    recovered_by      = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="lost_inventory_recoveries",
    )
    created_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Lost Inventory Recovery"
        verbose_name_plural = "Lost Inventory Recoveries"
        ordering            = ["-recovered_at", "-id"]

    def __str__(self):
        return f"{self.lost_item.product.name} — {self.quantity} recovered on {self.recovered_at}"


class LostInventoryFIFOConsumption(models.Model):
    """
    Records exactly which purchase batch(es) a LostInventoryItem's quantity
    was drawn from at the moment it was marked lost — mirrors billing.FIFOLedger.
    A single loss can span multiple batches (FIFO may need to pull from more
    than one PurchaseItem to cover the lost quantity), so this is one row per
    batch actually touched, not one row per LostInventoryItem.

    Enables mark_lost_inventory_found to restore the EXACT original batches
    instead of an approximation. restored_quantity tracks how much of THIS
    specific consumption has already been reversed (supports partial finds
    that only partially restore a given row before moving to the next).
    """

    lost_item     = models.ForeignKey(LostInventoryItem, on_delete=models.CASCADE, related_name="fifo_consumptions")
    purchase_item = models.ForeignKey(PurchaseItem, on_delete=models.PROTECT, related_name="lost_inventory_consumptions")
    quantity      = models.PositiveIntegerField(help_text="Quantity originally drawn from this batch when marked lost.")
    unit_cost     = models.DecimalField(max_digits=14, decimal_places=4, help_text="Tax-inclusive unit cost of this batch at the time of loss.")
    restored_quantity = models.PositiveIntegerField(default=0)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Lost Inventory FIFO Consumption"
        verbose_name_plural = "Lost Inventory FIFO Consumptions"
        ordering            = ["id"]

    @property
    def restorable_quantity(self):
        return self.quantity - self.restored_quantity

    def __str__(self):
        return f"{self.lost_item} ← {self.purchase_item} x {self.quantity}"


# ---------------------------------------------------------------------------
# Supplier Payment
# ---------------------------------------------------------------------------

class SupplierPayment(AuditMixin):
    """
    Payment made to a supplier against a PurchaseOrder.
    One order can have multiple partial payments over time.
    payment_type is stored for future use (no logic difference currently).
    """

    class Method(models.TextChoices):
        """
        Legacy label choices, kept for get_method_display()/backward
        compatibility. Since payment_methods.PaymentMethod (a real account,
        possibly user-created) replaced this as the actual source of truth,
        `method` can hold any account's name (lower-cased) or "multiple" for
        a split payment — values outside this list are still accepted at
        the ORM level (Django doesn't enforce `choices` on save()), they
        just fall back to showing the raw value via get_method_display().
        """
        CASH      = "cash",      "Cash"
        JAZZCASH  = "jazzcash",  "JazzCash"
        EASYPAISA = "easypaisa", "Easypaisa"
        BANK      = "bank",      "Bank Transfer"
        MULTIPLE  = "multiple",  "Multiple Methods"

    order            = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name="payments")
    reference_number = models.CharField(max_length=30, unique=True, editable=False,
                        #    default="", blank=True,
                           help_text="Auto-generated e.g. SPY-2026-0001")
    amount           = models.DecimalField(max_digits=18, decimal_places=4)
    method           = models.CharField(
        max_length=100, choices=Method.choices,
        help_text="Derived display label — see payment_methods.PaymentAllocation for the real split.",
    )
    payment_date     = models.DateField(db_index=True)
    note             = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        verbose_name        = "Supplier Payment"
        verbose_name_plural = "Supplier Payments"
        ordering            = ["-payment_date"]

    def __str__(self):
        return f"{self.order.order_number} — {self.method} {self.amount}"


# ---------------------------------------------------------------------------
# Saved Purchase Order PDF
# ---------------------------------------------------------------------------

class SavedPurchaseOrderPDF(models.Model):
    """
    Tracks every PDF saved for a confirmed PurchaseOrder.
    Mirrors billing.SavedInvoicePDF — same pattern.
    """

    order      = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name="saved_pdfs")
    file_name  = models.CharField(max_length=255)
    file_path  = models.CharField(max_length=500)
    saved_by   = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="saved_purchase_pdfs",
    )
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="deleted_purchase_pdfs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False, db_index=True)

    objects     = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        verbose_name        = "Saved Purchase Order PDF"
        verbose_name_plural = "Saved Purchase Order PDFs"
        ordering            = ["-created_at"]

    def __str__(self):
        return f"{self.order.order_number} — {self.file_name}"


# ---------------------------------------------------------------------------
# Inventory (auto-managed — unchanged)
# ---------------------------------------------------------------------------

class Inventory(models.Model):
    product         = models.OneToOneField(Product, on_delete=models.PROTECT, related_name="inventory")
    # Indexed — the low-stock / out-of-stock breakdown endpoints filter on
    # quantity thresholds.
    quantity        = models.PositiveIntegerField(default=0, db_index=True)
    last_updated_at = models.DateTimeField(auto_now=True)
    last_updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="inventory_updates",
    )

    class Meta:
        verbose_name        = "Inventory"
        verbose_name_plural = "Inventories"
        ordering            = ["product__name"]

    def __str__(self):
        return f"{self.product.name} — qty: {self.quantity}"


class ShelfStock(models.Model):
    """
    Live physical quantity of one product on one shelf. This is the
    per-location breakdown of the same total tracked globally by
    Inventory.quantity — the two must always agree in total
    (sum(ShelfStock.quantity for product) == Inventory.quantity for that
    product). Only ever mutated through services.apply_shelf_delta (the
    single writer, mirroring sync_inventory's role for Inventory).
    """
    shelf           = models.ForeignKey(Shelf, on_delete=models.PROTECT, related_name="stock_rows")
    product         = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="shelf_stock_rows")
    quantity        = models.PositiveIntegerField(default=0)
    last_updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "Shelf Stock"
        verbose_name_plural = "Shelf Stock"
        unique_together     = [("shelf", "product")]

    def __str__(self):
        return f"{self.shelf.name} — {self.product.name}: {self.quantity}"


class ShelfStockMovement(models.Model):
    """
    Append-only audit ledger — one row per shelf-quantity change, whatever
    caused it. This is the human-readable trail behind every ShelfStock
    number: which purchase/sale/return/loss/move touched this shelf, when,
    by whom. Never read for live totals (ShelfStock.quantity is the O(1)
    stored figure) — this is drill-down/audit only.
    """
    class Reason(models.TextChoices):
        PURCHASE_PUTAWAY     = "purchase_putaway",     "Purchase Put-Away"
        SALE_CONSUMPTION     = "sale_consumption",     "Sale Consumption"
        INVOICE_RETURN_PUTAWAY = "invoice_return_putaway", "Invoice Return Put-Away"
        PURCHASE_RETURN_CONSUMPTION = "purchase_return_consumption", "Purchase Return Consumption"
        LOST_CONSUMPTION     = "lost_consumption",     "Lost Inventory Consumption"
        LOST_FOUND_PUTAWAY   = "lost_found_putaway",   "Lost Inventory Found Put-Away"
        MOVE_OUT             = "move_out",             "Manual Move (Out)"
        MOVE_IN              = "move_in",              "Manual Move (In)"
        BACKFILL             = "backfill",              "Backfill"

    shelf      = models.ForeignKey(Shelf, on_delete=models.PROTECT, related_name="movements")
    product    = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="shelf_movements")
    delta      = models.IntegerField(help_text="Positive = added to shelf, negative = removed from shelf.")
    reason     = models.CharField(max_length=30, choices=Reason.choices, db_index=True)
    reference  = models.CharField(max_length=30, blank=True, default="", help_text="e.g. PO-2026-0001, BILL-2026-0001")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="shelf_stock_movements",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name        = "Shelf Stock Movement"
        verbose_name_plural = "Shelf Stock Movements"
        ordering            = ["-created_at"]
        indexes = [
            models.Index(fields=["shelf", "-created_at"]),
            models.Index(fields=["product", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.shelf.name} — {self.product.name}: {self.delta:+d} ({self.reason})"


class ProductStockMovement(models.Model):
    """
    Per-product running quantity totals for the Stock Movement Report —
    one row per product, updated live via _adjust_stock_movement() in
    services.py. All six fields only ever increase: none of the six
    source events (PO confirm, purchase return accept, invoice confirm,
    customer return accept, lost inventory record, mark-as-found) are
    ever undone in this codebase.
    """
    product                 = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="stock_movement")
    total_purchased         = models.PositiveIntegerField(default=0)
    total_purchase_returned = models.PositiveIntegerField(default=0)
    total_sold               = models.PositiveIntegerField(default=0)
    total_sale_returned      = models.PositiveIntegerField(default=0)
    total_lost                = models.PositiveIntegerField(default=0)
    total_found               = models.PositiveIntegerField(default=0)
    last_updated_at          = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "Product Stock Movement"
        verbose_name_plural = "Product Stock Movement"

    def __str__(self):
        return f"{self.product.name} — purchased {self.total_purchased}, sold {self.total_sold}"


class StockMovementFlow(models.Model):
    """
    Single live record — the all-time, all-product totals for the Stock
    Movement Report header. Same six fields as ProductStockMovement,
    summed across every product, kept in sync by the same
    _adjust_stock_movement() calls.
    """
    total_purchased         = models.PositiveIntegerField(default=0)
    total_purchase_returned = models.PositiveIntegerField(default=0)
    total_sold               = models.PositiveIntegerField(default=0)
    total_sale_returned      = models.PositiveIntegerField(default=0)
    total_lost                = models.PositiveIntegerField(default=0)
    total_found               = models.PositiveIntegerField(default=0)
    last_updated_at          = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "Stock Movement Flow"
        verbose_name_plural = "Stock Movement Flow"

    def __str__(self):
        return f"StockMovementFlow — purchased {self.total_purchased}, sold {self.total_sold}"

    @classmethod
    def get_instance(cls):
        instance, _ = cls.objects.get_or_create(pk=1)
        return instance


# Products with 0 < quantity <= LOW_STOCK_THRESHOLD count as "low stock";
# quantity <= 0 counts as "out of stock". Single source of truth for the
# stats singleton, the breakdown selectors, and the backfill command.
LOW_STOCK_THRESHOLD = 5


class InventoryStatsFlow(models.Model):
    """
    Single live record — O(1) inventory stats for the Inventory page cards
    (total products, low stock, out of stock). Counts cover inventory rows
    of non-deleted products only, matching what the inventory list shows.
    Kept in sync by services.sync_inventory() (the ONLY quantity writer,
    used by purchases AND billing) and services.delete_product(); rebuilt
    from live data by backfill_inventory_stats.
    """
    total_products     = models.PositiveIntegerField(default=0)
    low_stock_count    = models.PositiveIntegerField(default=0)
    out_of_stock_count = models.PositiveIntegerField(default=0)
    last_updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "Inventory Stats Flow"
        verbose_name_plural = "Inventory Stats Flow"

    def __str__(self):
        return (
            f"InventoryStatsFlow — total {self.total_products}, "
            f"low {self.low_stock_count}, out {self.out_of_stock_count}"
        )

    @classmethod
    def get_instance(cls):
        instance, _ = cls.objects.get_or_create(pk=1)
        return instance


# ---------------------------------------------------------------------------
# Document reference counters
# ---------------------------------------------------------------------------

class DocumentCounter(models.Model):
    """
    One row per document type per year holding the last sequence number used
    (PO-2026-#### / SPY / RTN / LOSS). Reference generation locks this row
    (select_for_update), increments, and formats — O(1) and race-safe, unlike
    the old "sort existing references as text" approach, which was O(N) per
    create, collided under concurrency, and broke permanently at sequence
    10000 (text sort puts '9999' after '10000'). Seeded lazily from the
    numeric max of existing references the first time a (doc_type, year)
    is used.
    """
    doc_type    = models.CharField(max_length=10)
    year        = models.PositiveIntegerField()
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name        = "Document Counter"
        verbose_name_plural = "Document Counters"
        unique_together     = [("doc_type", "year")]

    def __str__(self):
        return f"{self.doc_type}-{self.year} — last {self.last_number}"