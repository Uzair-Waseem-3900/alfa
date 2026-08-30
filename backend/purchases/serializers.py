from rest_framework import serializers

from payment_methods.serializers import MethodAllocationInputSerializer

from .models import (
    Category, Inventory, LostInventoryItem, LostInventoryRecord, Product,
    PurchaseItem, PurchaseItemShelfAllocation, PurchaseOrder, PurchaseReturn,
    PurchaseReturnItem, PurchaseReturnItemShelfAllocation,
    SavedPurchaseOrderPDF, Shelf, ShelfStock, Supplier, SupplierPayment,
)


# ---------------------------------------------------------------------------
# Shared audit mixin for read serializers
# ---------------------------------------------------------------------------

class AuditReadMixin(serializers.Serializer):
    created_by = serializers.StringRelatedField(read_only=True)
    updated_by = serializers.StringRelatedField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------

class CategoryReadSerializer(AuditReadMixin, serializers.ModelSerializer):
    class Meta:
        model  = Category
        fields = ["id", "name", "description", "created_by", "updated_by", "created_at", "updated_at"]


class CategoryWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Category
        fields = ["name", "description"]

    def validate_name(self, value):
        qs = Category.objects.filter(name__iexact=value.strip(), is_deleted=False)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A category with this name already exists.")
        return value.strip()


# ---------------------------------------------------------------------------
# Shelf
# ---------------------------------------------------------------------------

class ShelfReadSerializer(AuditReadMixin, serializers.ModelSerializer):
    class Meta:
        model  = Shelf
        fields = ["id", "name", "description", "created_by", "updated_by", "created_at", "updated_at"]


class ShelfWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Shelf
        fields = ["name", "description"]

    def validate_name(self, value):
        qs = Shelf.objects.filter(name__iexact=value.strip(), is_deleted=False)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A shelf with this name already exists.")
        return value.strip()


class ShelfLiteSerializer(serializers.ModelSerializer):
    """Minimal shelf shape for nesting inside allocation rows — id/name only."""
    class Meta:
        model  = Shelf
        fields = ["id", "name"]


class CandidateShelfSerializer(serializers.ModelSerializer):
    """
    Dropdown source for consumption allocations (sale/return/loss) — shelves
    that currently hold stock of a given product, with the quantity
    available on each (from the selector's annotation).
    """
    available_quantity = serializers.IntegerField(read_only=True)

    class Meta:
        model  = Shelf
        fields = ["id", "name", "available_quantity"]


class AutoAllocateShelvesRequestSerializer(serializers.Serializer):
    product_id        = serializers.IntegerField()
    quantity          = serializers.IntegerField(min_value=1)
    exclude_shelf_ids = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)


class AutoAllocatedShelfSerializer(serializers.Serializer):
    shelf_id   = serializers.IntegerField()
    shelf_name = serializers.CharField()
    quantity   = serializers.IntegerField()


class AutoAllocateShelvesResponseSerializer(serializers.Serializer):
    allocations = AutoAllocatedShelfSerializer(many=True)
    shortfall   = serializers.IntegerField()


class ShelfAllocationInputSerializer(serializers.Serializer):
    """Reusable input row for every 'set shelf allocations' request body."""
    shelf_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)


class SetShelfAllocationsSerializer(serializers.Serializer):
    allocations = ShelfAllocationInputSerializer(many=True)

    def validate_allocations(self, value):
        if not value:
            raise serializers.ValidationError("At least one allocation is required.")
        shelf_ids = [a["shelf_id"] for a in value]
        if len(shelf_ids) != len(set(shelf_ids)):
            raise serializers.ValidationError("Duplicate shelf_id entries are not allowed.")
        return value


class MoveStockSerializer(serializers.Serializer):
    from_shelf_id = serializers.IntegerField()
    to_shelf_id   = serializers.IntegerField()
    product_id    = serializers.IntegerField()
    quantity      = serializers.IntegerField(min_value=1)


# ---------------------------------------------------------------------------
# Supplier
# ---------------------------------------------------------------------------

class SupplierReadSerializer(AuditReadMixin, serializers.ModelSerializer):
    class Meta:
        model  = Supplier
        fields = ["id", "name", "code", "created_by", "updated_by", "created_at", "updated_at"]


class SupplierWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Supplier
        fields = ["name", "code"]

    def validate_code(self, value):
        qs = Supplier.objects.filter(code__iexact=value.strip(), is_deleted=False)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A supplier with this code already exists.")
        return value.strip().upper()

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Supplier name cannot be blank.")
        return value.strip()


class SupplierWithOutstandingSerializer(serializers.ModelSerializer):
    outstanding = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)

    class Meta:
        model  = Supplier
        fields = ["id", "name", "code", "outstanding"]


class SupplierPayableSummarySerializer(serializers.Serializer):
    supplier_id               = serializers.IntegerField()
    total_net_payable         = serializers.DecimalField(max_digits=18, decimal_places=4)
    total_paid                = serializers.DecimalField(max_digits=18, decimal_places=4)
    total_payable_outstanding = serializers.DecimalField(max_digits=18, decimal_places=4)


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------

class ProductReadSerializer(AuditReadMixin, serializers.ModelSerializer):
    category = CategoryReadSerializer(read_only=True)

    class Meta:
        model  = Product
        fields = ["id", "name", "code", "category",
                  "created_by", "updated_by", "created_at", "updated_at"]


class ProductLiteSerializer(serializers.ModelSerializer):
    """Minimal product shape for nesting inside bulk-listed rows (shelf stock)."""
    class Meta:
        model  = Product
        fields = ["id", "name", "code"]


class ProductWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Product
        fields = ["name", "code", "category"]

    def validate_code(self, value):
        qs = Product.objects.filter(code__iexact=value.strip(), is_deleted=False)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A product with this code already exists.")
        return value.strip().upper()

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Product name cannot be blank.")
        return value.strip()

    def validate_category(self, value):
        if value.is_deleted:
            raise serializers.ValidationError("Selected category has been deleted.")
        return value


# ---------------------------------------------------------------------------
# PurchaseItem (line item)
# ---------------------------------------------------------------------------

class PurchaseItemShelfAllocationReadSerializer(serializers.ModelSerializer):
    shelf      = ShelfLiteSerializer(read_only=True)

    class Meta:
        model  = PurchaseItemShelfAllocation
        fields = ["id", "shelf", "quantity"]
        read_only_fields = fields


class PurchaseItemReadSerializer(serializers.ModelSerializer):
    product_name        = serializers.CharField(source="product.name", read_only=True)
    product_code        = serializers.CharField(source="product.code", read_only=True)
    returnable_quantity = serializers.IntegerField(read_only=True)
    allocated_quantity  = serializers.IntegerField(read_only=True)
    shelf_allocations   = PurchaseItemShelfAllocationReadSerializer(many=True, read_only=True)

    class Meta:
        model  = PurchaseItem
        fields = [
            "id", "product", "product_name", "product_code",
            "quantity", "remaining_quantity", "returned_quantity", "returnable_quantity",
            "unit_price", "gst", "wht", "description",
            "gross_amount", "gst_amount", "wht_amount", "total_price",
            "allocated_quantity", "shelf_allocations",
        ]
        read_only_fields = fields


class PurchaseItemWriteSerializer(serializers.Serializer):
    """Nested inside PurchaseOrder create/update."""
    product_id  = serializers.IntegerField()
    quantity    = serializers.IntegerField(min_value=1)
    unit_price  = serializers.DecimalField(max_digits=14, decimal_places=4)
    gst         = serializers.DecimalField(max_digits=5, decimal_places=2, default=0, required=False)
    wht         = serializers.DecimalField(max_digits=5, decimal_places=2, default=0, required=False)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")

    def validate_unit_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Unit price must be greater than zero.")
        return value

    def validate_gst(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("GST must be between 0 and 100.")
        return value

    def validate_wht(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("WHT must be between 0 and 100.")
        return value


# ---------------------------------------------------------------------------
# PurchaseOrder
# ---------------------------------------------------------------------------

class PurchaseOrderReadSerializer(serializers.ModelSerializer):
    supplier             = SupplierReadSerializer(read_only=True)
    items                = PurchaseItemReadSerializer(many=True, read_only=True)
    created_by           = serializers.StringRelatedField(read_only=True)
    updated_by           = serializers.StringRelatedField(read_only=True)
    confirmed_by         = serializers.StringRelatedField(read_only=True)
    deleted_by           = serializers.StringRelatedField(read_only=True)
    payment_status_display = serializers.CharField(source="get_payment_status_display", read_only=True)
    draft_preview        = serializers.SerializerMethodField()

    class Meta:
        model  = PurchaseOrder
        fields = [
            "id", "order_number", "supplier", "status", "description", "payment_type", "advance_amount",
            "gross_amount", "gst_total", "wht_total", "net_payable",
            "payable_outstanding", "total_paid", "payment_status", "payment_status_display",
            "draft_preview",
            "items",
            "confirmed_by", "confirmed_at",
            "created_by", "updated_by", "deleted_by",
            "created_at", "updated_at", "deleted_at",
        ]
        read_only_fields = fields

    def get_draft_preview(self, obj):
        """
        Shows calculated totals on draft orders without storing anything.
        Returns None for confirmed orders (real numbers already stored).
        """
        if obj.status != PurchaseOrder.Status.DRAFT:
            return None
        from .utils import calculate_total_price
        from decimal import Decimal

        items_preview = []
        total_gross = Decimal("0")
        total_gst   = Decimal("0")
        total_wht   = Decimal("0")
        total_net   = Decimal("0")

        # .all() reuses the selector's prefetch cache (already filtered to
        # live items via SoftDeleteManager) — .filter() here would throw the
        # cache away and re-query per order AND per item (N+1).
        for item in obj.items.all():
            calc = calculate_total_price(
                quantity=item.quantity,
                unit_price=item.unit_price,
                gst=item.gst,
                wht=item.wht,
            )
            total_gross += calc["gross_amount"]
            total_gst   += calc["gst_amount"]
            total_wht   += calc["wht_amount"]
            total_net   += calc["total_price"]
            items_preview.append({
                "product_name"  : item.product.name,
                "product_code"  : item.product.code,
                "quantity"      : item.quantity,
                "unit_price"    : str(item.unit_price),
                "gst"           : str(item.gst),
                "wht"           : str(item.wht),
                "gross_amount"  : str(calc["gross_amount"]),
                "gst_amount"    : str(calc["gst_amount"]),
                "wht_amount"    : str(calc["wht_amount"]),
                "total_price"   : str(calc["total_price"]),
            })

        return {
            "items"       : items_preview,
            "gross_amount": str(total_gross),
            "gst_total"   : str(total_gst),
            "wht_total"   : str(total_wht),
            "net_payable" : str(total_net),
            "note"        : "Preview only — no inventory or debt effect until confirmed.",
        }


class PurchaseOrderCreateSerializer(serializers.Serializer):
    supplier_id    = serializers.IntegerField()
    description    = serializers.CharField(required=False, allow_blank=True, default="")
    payment_type   = serializers.ChoiceField(
        choices=["advance", "after_delivery"],
        default="after_delivery",
        required=False,
        help_text="advance: paid before delivery. after_delivery: paid after.",
    )
    advance_amount = serializers.DecimalField(
        max_digits=18, decimal_places=4, default=0, required=False,
        help_text="Required when payment_type=advance. Immediately deducted from cash in hand.",
    )
    method_allocations = MethodAllocationInputSerializer(
        many=True, required=False,
        help_text="Required when payment_type=advance — which method(s) the advance was paid from, and how much of each.",
    )
    items = PurchaseItemWriteSerializer(many=True)

    def validate(self, attrs):
        payment_type   = attrs.get("payment_type", "after_delivery")
        advance_amount = attrs.get("advance_amount", 0)
        if payment_type == "after_delivery" and advance_amount and advance_amount > 0:
            raise serializers.ValidationError(
                {"advance_amount": "advance_amount must be 0 when payment_type is after_delivery."}
            )
        if payment_type == "advance" and (not advance_amount or advance_amount <= 0):
            raise serializers.ValidationError(
                {"advance_amount": "advance_amount is required and must be > 0 when payment_type is advance."}
            )
        if payment_type == "advance" and advance_amount > 0 and not attrs.get("method_allocations"):
            raise serializers.ValidationError(
                {"method_allocations": "At least one method must be selected for the advance payment."}
            )
        return attrs

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item is required.")
        return value


class PurchaseOrderUpdateSerializer(serializers.Serializer):
    description    = serializers.CharField(required=False, allow_blank=True)
    payment_type   = serializers.ChoiceField(
        choices=["advance", "after_delivery"],
        required=False,
    )
    advance_amount = serializers.DecimalField(
        max_digits=18, decimal_places=4, required=False,
        help_text="Update the advance amount. Only valid when payment_type=advance.",
    )
    method_allocations = MethodAllocationInputSerializer(
        many=True, required=False,
        help_text="Required whenever advance_amount is being set to a value > 0 — the new split is never reused from the old amount.",
    )
    items = PurchaseItemWriteSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item is required.")
        return value


# ---------------------------------------------------------------------------
# Supplier Payment
# ---------------------------------------------------------------------------

class SupplierPaymentReadSerializer(serializers.ModelSerializer):
    created_by     = serializers.StringRelatedField(read_only=True)
    method_display = serializers.CharField(source="get_method_display", read_only=True)
    allocations    = serializers.SerializerMethodField()
    order_number   = serializers.CharField(source="order.order_number", read_only=True)
    supplier_name  = serializers.CharField(source="order.supplier.name", read_only=True)

    class Meta:
        model  = SupplierPayment
        fields = [
            "id", "order", "order_number", "supplier_name", "reference_number", "amount",
            "method", "method_display", "allocations", "payment_date", "note",
            "created_by", "created_at",
        ]
        read_only_fields = fields

    def get_allocations(self, obj):
        from payment_methods.serializers import PaymentAllocationReadSerializer

        # Prefer the batch-prefetched map (list/nested contexts — see
        # SupplierPaymentListCreateView.list() / PurchaseOrderPaymentSummaryView)
        # over a live per-object query, which would N+1 across every
        # payment on the page/order.
        prefetched = self.context.get("supplier_payment_allocations")
        if prefetched is not None:
            rows = prefetched.get(obj.id, [])
        else:
            from payment_methods.selectors import get_allocations_for_source
            rows = get_allocations_for_source(obj)
        return PaymentAllocationReadSerializer(rows, many=True).data


class SupplierPaymentWriteSerializer(serializers.ModelSerializer):
    method_allocations = MethodAllocationInputSerializer(many=True)

    class Meta:
        model  = SupplierPayment
        fields = ["order", "amount", "method_allocations", "payment_date", "note"]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Payment amount must be greater than zero.")
        return value

    def validate_method_allocations(self, value):
        if not value:
            raise serializers.ValidationError("At least one method must be selected.")
        return value


# ---------------------------------------------------------------------------
# Purchase Order Payment Summary
# ---------------------------------------------------------------------------

class PurchaseOrderPaymentSummarySerializer(serializers.ModelSerializer):
    supplier_name          = serializers.CharField(source="supplier.name", read_only=True)
    supplier_code          = serializers.CharField(source="supplier.code", read_only=True)
    payment_status_display = serializers.CharField(source="get_payment_status_display", read_only=True)
    payments               = SupplierPaymentReadSerializer(many=True, read_only=True)

    class Meta:
        model  = PurchaseOrder
        fields = [
            "id", "order_number", "supplier_name", "supplier_code",
            "status", "payment_type", "advance_amount", "net_payable",
            "payable_outstanding", "total_paid",
            "payment_status", "payment_status_display",
            "payments",
            "confirmed_at", "created_at",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Purchase Return
# ---------------------------------------------------------------------------

class PurchaseReturnItemWriteSerializer(serializers.Serializer):
    purchase_item_id = serializers.IntegerField()
    quantity         = serializers.IntegerField(min_value=1)
    gst              = serializers.DecimalField(max_digits=5, decimal_places=2, default=0, required=False)
    wht              = serializers.DecimalField(max_digits=5, decimal_places=2, default=0, required=False)

    def validate_gst(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("GST must be between 0 and 100.")
        return value

    def validate_wht(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("WHT must be between 0 and 100.")
        return value


class PurchaseReturnCreateSerializer(serializers.Serializer):
    order_id = serializers.IntegerField()
    items    = PurchaseReturnItemWriteSerializer(many=True)
    note     = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item is required.")
        return value


class PurchaseReturnUpdateSerializer(serializers.Serializer):
    items = PurchaseReturnItemWriteSerializer(many=True)
    note  = serializers.CharField(max_length=500, required=False, allow_blank=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item is required.")
        return value


class PurchaseReturnItemShelfAllocationReadSerializer(serializers.ModelSerializer):
    shelf = ShelfLiteSerializer(read_only=True)

    class Meta:
        model  = PurchaseReturnItemShelfAllocation
        fields = ["id", "shelf", "quantity"]
        read_only_fields = fields


class PurchaseReturnItemReadSerializer(serializers.ModelSerializer):
    product            = serializers.IntegerField(source="purchase_item.product_id", read_only=True)
    product_name       = serializers.CharField(source="purchase_item.product.name", read_only=True)
    product_code       = serializers.CharField(source="purchase_item.product.code", read_only=True)
    allocated_quantity = serializers.IntegerField(read_only=True)
    shelf_allocations  = PurchaseReturnItemShelfAllocationReadSerializer(many=True, read_only=True)

    class Meta:
        model  = PurchaseReturnItem
        fields = [
            "id", "product", "product_name", "product_code", "quantity",
            "gst", "wht", "unit_price",
            "gross_amount", "gst_amount", "wht_amount", "total_amount",
            "allocated_quantity", "shelf_allocations",
        ]
        read_only_fields = fields


class PurchaseReturnReadSerializer(serializers.ModelSerializer):
    items                = PurchaseReturnItemReadSerializer(many=True, read_only=True)
    created_by           = serializers.StringRelatedField(read_only=True)
    accepted_by          = serializers.StringRelatedField(read_only=True)
    order_number         = serializers.CharField(source="order.order_number", read_only=True)
    supplier_name        = serializers.CharField(source="order.supplier.name", read_only=True)

    class Meta:
        model  = PurchaseReturn
        fields = [
            "id", "order", "order_number", "supplier_name", "reference_number", "status",
            "total_return_gross", "total_return_gst", "total_return_wht", "total_return_amount",
            "items", "note",
            "accepted_by", "accepted_at",
            "created_by", "created_at", "updated_at",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Lost Inventory
# ---------------------------------------------------------------------------

class LostInventoryItemWriteSerializer(serializers.Serializer):
    product_id        = serializers.IntegerField()
    quantity          = serializers.IntegerField(min_value=1)
    reason            = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    shelf_allocations = ShelfAllocationInputSerializer(many=True)


class LostInventoryCreateSerializer(serializers.Serializer):
    items = LostInventoryItemWriteSerializer(many=True)
    note  = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item is required.")
        return value


class LostInventoryItemReadSerializer(serializers.ModelSerializer):
    product_name        = serializers.CharField(source="product.name", read_only=True)
    product_code        = serializers.CharField(source="product.code", read_only=True)
    returnable_quantity = serializers.IntegerField(read_only=True)
    recovered_amount     = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)
    net_amount           = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)

    class Meta:
        model  = LostInventoryItem
        fields = [
            "id", "product", "product_name", "product_code",
            "quantity", "reason", "unit_cost", "total_cost",
            "found_quantity", "returnable_quantity", "recovered_amount", "net_amount",
        ]
        read_only_fields = fields


class MarkLostInventoryFoundSerializer(serializers.Serializer):
    quantity          = serializers.IntegerField(min_value=1)
    shelf_allocations = ShelfAllocationInputSerializer(many=True)


class LostInventoryFifoPreviewQuerySerializer(serializers.Serializer):
    """Validates query params for the FIFO cost preview endpoint."""
    product_id = serializers.IntegerField()
    quantity   = serializers.IntegerField(min_value=1)


class LostInventoryFifoPreviewSerializer(serializers.Serializer):
    product_id         = serializers.IntegerField()
    quantity           = serializers.IntegerField()
    available_quantity = serializers.IntegerField()
    unit_cost          = serializers.DecimalField(max_digits=14, decimal_places=4)
    total_cost         = serializers.DecimalField(max_digits=18, decimal_places=4)
    sufficient_stock   = serializers.BooleanField()


class LostInventoryReadSerializer(serializers.ModelSerializer):
    items       = LostInventoryItemReadSerializer(many=True, read_only=True)
    created_by  = serializers.StringRelatedField(read_only=True)
    updated_by  = serializers.StringRelatedField(read_only=True)

    class Meta:
        model  = LostInventoryRecord
        fields = [
            "id", "reference_number", "note", "total_lost_amount",
            "items", "created_by", "updated_by", "created_at", "updated_at",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Saved PDF
# ---------------------------------------------------------------------------

class SavedPurchaseOrderPDFSerializer(serializers.ModelSerializer):
    saved_by   = serializers.StringRelatedField(read_only=True)
    deleted_by = serializers.StringRelatedField(read_only=True)
    file_url   = serializers.SerializerMethodField()

    class Meta:
        model  = SavedPurchaseOrderPDF
        fields = [
            "id", "order", "file_name", "file_url",
            "saved_by", "created_at", "deleted_by", "deleted_at", "is_deleted",
        ]
        read_only_fields = fields

    def get_file_url(self, obj):
        if not obj.file_path:
            return None
        from django.conf import settings
        path = obj.file_path.replace("\\", "/")
        return f"{settings.BACKEND_URL}{settings.MEDIA_URL}{path}"


class SavePurchaseOrderPDFRequestSerializer(serializers.Serializer):
    """Only confirmed orders can be saved."""
    file_name = serializers.CharField(
        max_length=255, required=False,
        help_text="Custom file name. Defaults to order number if not provided.",
    )

    def validate_file_name(self, value):
        return value.strip() if value else value


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

class InventoryReadSerializer(serializers.ModelSerializer):
    product          = ProductReadSerializer(read_only=True)
    last_updated_by  = serializers.StringRelatedField(read_only=True)

    class Meta:
        model  = Inventory
        fields = ["id", "product", "quantity", "last_updated_at", "last_updated_by"]
        read_only_fields = fields


class InventoryStatsSerializer(serializers.Serializer):
    """O(1) stats cards — read straight off the InventoryStatsFlow singleton."""
    total_products     = serializers.IntegerField(read_only=True)
    low_stock_count    = serializers.IntegerField(read_only=True)
    out_of_stock_count = serializers.IntegerField(read_only=True)
    last_updated_at    = serializers.DateTimeField(read_only=True)


# ---------------------------------------------------------------------------
# Shelf Stock (per-location breakdown)
# ---------------------------------------------------------------------------

class ShelfStockReadSerializer(serializers.ModelSerializer):
    """
    Products + quantities currently on one shelf. Nests a lightweight
    product shape (id/name/code) rather than the full ProductReadSerializer
    — these rows are listed in bulk and don't need category/audit fields.
    """
    product = ProductLiteSerializer(read_only=True)

    class Meta:
        model  = ShelfStock
        fields = ["id", "product", "quantity", "last_updated_at"]
        read_only_fields = fields