from decimal import Decimal

from rest_framework import serializers

from payment_methods.serializers import MethodAllocationInputSerializer

from .models import (
    Customer, Invoice, InvoiceItem, InvoiceItemShelfAllocation,
    InvoiceReturnItemShelfAllocation, Payment, Return, ReturnItem,
)


def _is_staff_request(context) -> bool:
    """
    Admin/superuser check for hiding cost/profit fields from the API
    response — same is_staff flag IsAdminOrSuperuser checks everywhere
    else. Fails closed (hidden) when there's no request in context, e.g. a
    serializer instantiated without one — better to under-show than leak.
    """
    request = context.get("request")
    return bool(request and request.user and request.user.is_staff)


# ---------------------------------------------------------------------------
# Draft preview helper — pure read, zero DB writes
# ---------------------------------------------------------------------------

def _build_draft_preview(invoice: Invoice) -> dict | None:
    """
    Computes a live price preview for DRAFT invoices only.
    Reads current rate list price and oldest available purchase cost (FIFO peek).
    Never writes anything — purely informational.
    Returns None for non-draft invoices (confirmed invoices have real numbers).
    """
    if invoice.status != Invoice.Status.DRAFT:
        return None

    from purchases.models import PurchaseItem

    preview_items     = []
    total_subtotal    = Decimal("0")
    total_cogs        = Decimal("0")
    has_missing_rate  = False
    has_missing_stock = False

    items = list(invoice.items.all())

    # One batches query for the whole invoice instead of one per line item,
    # grouped per product in Python. Same filter and created_at ordering as
    # the old per-item query, so per-product batch order (and therefore the
    # peeked cost) is identical.
    batches_by_product = {}
    all_batches = (
        PurchaseItem.objects
        .filter(
            product_id__in=[item.product_id for item in items],
            is_deleted=False,
            remaining_quantity__gt=0,
        )
        .order_by("created_at")
    )
    for batch in all_batches:
        batches_by_product.setdefault(batch.product_id, []).append(batch)

    for item in items:
        product = item.product

        # --- Selling price from rate list ---
        try:
            selling_price = product.rate.selling_price
        except Exception:
            selling_price    = None
            has_missing_rate = True

        # --- FIFO peek: blended cost from oldest batches (read-only) ---
        batches = batches_by_product.get(product.id, [])
        available_qty  = sum(b.remaining_quantity for b in batches)
        qty_to_consume = item.quantity
        remaining      = qty_to_consume
        total_cost     = Decimal("0")
        stock_ok       = available_qty >= qty_to_consume

        if not stock_ok:
            has_missing_stock = True
            cogs_per_unit     = None
        else:
            for batch in batches:
                if remaining <= 0:
                    break
                consume = min(batch.remaining_quantity, remaining)
                # Tax-inclusive unit cost mirrors _run_fifo: total_price / quantity
                tax_inclusive = (
                    batch.total_price / batch.quantity
                    if batch.quantity > 0 else batch.unit_price
                )
                total_cost += consume * tax_inclusive
                remaining  -= consume
            cogs_per_unit = (
                total_cost / Decimal(str(qty_to_consume))
                if qty_to_consume else Decimal("0")
            )

        # --- Line totals ---
        if selling_price is not None and cogs_per_unit is not None:
            line_total      = selling_price * item.quantity
            line_cogs       = cogs_per_unit * item.quantity
            line_profit     = line_total - line_cogs
            total_subtotal += line_total
            total_cogs     += line_cogs
        else:
            line_total = line_cogs = line_profit = None

        p = Decimal("0.0001")
        preview_items.append({
            "invoice_item_id"    : item.id,
            "product_name"       : product.name,
            "product_code"       : product.code,
            "quantity"           : item.quantity,
            "available_stock"    : available_qty,
            "selling_price"      : str(selling_price) if selling_price is not None else None,
            "cogs_per_unit"      : str(cogs_per_unit.quantize(p)) if cogs_per_unit is not None else None,
            "line_total"         : str(line_total.quantize(p)) if line_total is not None else None,
            "line_cogs"          : str(line_cogs.quantize(p)) if line_cogs is not None else None,
            "line_profit"        : str(line_profit.quantize(p)) if line_profit is not None else None,
            "rate_missing"       : selling_price is None,
            "stock_insufficient" : not stock_ok,
        })

    p = Decimal("0.0001")
    return {
        "items"        : preview_items,
        "subtotal"     : str(total_subtotal.quantize(p)),
        "total_cogs"   : str(total_cogs.quantize(p)),
        "gross_profit" : str((total_subtotal - total_cogs).quantize(p)),
        "warnings"     : {
            "missing_rate" : has_missing_rate,
            "missing_stock": has_missing_stock,
        },
        "note": "Preview only — no stock reserved, no prices committed. Confirm to finalise.",
    }


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------

class CustomerReadSerializer(serializers.ModelSerializer):
    created_by = serializers.StringRelatedField(read_only=True)
    updated_by = serializers.StringRelatedField(read_only=True)
    credit_score = serializers.SerializerMethodField()
    credit_tier = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = [
            "id", "name", "code", "address", "mobile",
            "credit_score", "credit_tier",
            "created_by", "updated_by", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_by", "updated_by", "created_at", "updated_at"]

    def get_credit_score(self, obj):
        # obj.credit_score is the OneToOne reverse accessor (credit_score
        # app's CustomerCreditScore.customer related_name) — already
        # select_related() by get_all_customers, so this is never an extra
        # per-row query.
        score = getattr(obj, "credit_score", None)
        return score.score if score else None

    def get_credit_tier(self, obj):
        score = getattr(obj, "credit_score", None)
        return score.tier if score else None


class CustomerWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["name", "code", "address", "mobile"]

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Customer name cannot be blank.")
        return value.strip()

    def validate_mobile(self, value):
        if value and not value.replace("+", "").replace("-", "").replace(" ", "").isdigit():
            raise serializers.ValidationError("Enter a valid mobile number.")
        return value


# ---------------------------------------------------------------------------
# Shelf allocations — invoice line consumption / return line put-away
# ---------------------------------------------------------------------------

class CandidateShelfSerializer(serializers.Serializer):
    """
    Dropdown source for consumption allocations (sale lines) — shelves that
    currently hold stock of a given product, with the quantity available on
    each (from purchases.selectors.get_candidate_shelves_for_product's
    annotation). Defined locally to avoid coupling to purchases' serializer
    module, which is being changed in parallel.
    """
    id = serializers.IntegerField()
    name = serializers.CharField()
    available_quantity = serializers.IntegerField()


class AutoAllocateShelvesRequestSerializer(serializers.Serializer):
    """
    Body for POST /billing/shelves/auto-allocate/ — thin pass-through to
    purchases.selectors.compute_auto_shelf_allocation, same pattern as
    CandidateShelfSerializer above (own copy, same shared backend function).
    """
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
    shelf_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)


class SetShelfAllocationsSerializer(serializers.Serializer):
    allocations = ShelfAllocationInputSerializer(many=True)

    def validate_allocations(self, value):
        if not value:
            raise serializers.ValidationError("At least one allocation is required.")
        shelf_ids = [a["shelf_id"] for a in value]
        if len(shelf_ids) != len(set(shelf_ids)):
            raise serializers.ValidationError("Duplicate shelf_id in allocations.")
        return value


class InvoiceItemShelfAllocationReadSerializer(serializers.ModelSerializer):
    shelf_id   = serializers.IntegerField(read_only=True)
    shelf_name = serializers.CharField(source="shelf.name", read_only=True)

    class Meta:
        model = InvoiceItemShelfAllocation
        fields = ["id", "shelf_id", "shelf_name", "quantity"]
        read_only_fields = fields


class ReturnItemShelfAllocationReadSerializer(serializers.ModelSerializer):
    shelf_id   = serializers.IntegerField(read_only=True)
    shelf_name = serializers.CharField(source="shelf.name", read_only=True)

    class Meta:
        model = InvoiceReturnItemShelfAllocation
        fields = ["id", "shelf_id", "shelf_name", "quantity"]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Invoice Item — nested inside invoice
# ---------------------------------------------------------------------------

class InvoiceItemReadSerializer(serializers.ModelSerializer):
    product_name        = serializers.CharField(source="product.name", read_only=True)
    product_code        = serializers.CharField(source="product.code", read_only=True)
    returnable_quantity = serializers.IntegerField(read_only=True)
    allocated_quantity  = serializers.IntegerField(read_only=True)
    shelf_allocations   = InvoiceItemShelfAllocationReadSerializer(many=True, read_only=True)

    class Meta:
        model = InvoiceItem
        fields = [
            "id", "product", "product_name", "product_code",
            "quantity", "returned_quantity", "returnable_quantity",
            "allocated_quantity", "shelf_allocations",
            # User-supplied per line
            "discount", "gst", "wht",
            # Computed at confirmation
            "selling_price", "effective_price", "cogs_per_unit",
            "line_gross", "line_gst_amount", "line_wht_amount",
            "line_total", "line_cogs", "line_profit",
        ]
        read_only_fields = fields

    # Cost/margin fields are admin-and-superuser-only — a normal user
    # legitimately needs selling_price/line_total to work an invoice, but
    # cogs_per_unit/line_cogs/line_profit reveal exact supplier cost and
    # profit margin. Stripped here (not just hidden in the frontend) so
    # they never leave the server for a non-staff request.
    _STAFF_ONLY_FIELDS = ("cogs_per_unit", "line_cogs", "line_profit")

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not _is_staff_request(self.context):
            for field in self._STAFF_ONLY_FIELDS:
                data.pop(field, None)
        return data


class InvoiceItemWriteSerializer(serializers.Serializer):
    """Used inside invoice create/update — not a standalone endpoint."""
    product_id = serializers.IntegerField()
    quantity   = serializers.IntegerField(min_value=1)
    discount   = serializers.DecimalField(max_digits=10, decimal_places=4, default=0, required=False)
    gst        = serializers.DecimalField(max_digits=5, decimal_places=2, default=0, required=False)
    wht        = serializers.DecimalField(max_digits=5, decimal_places=2, default=0, required=False)

    def validate_gst(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("GST must be between 0 and 100.")
        return value

    def validate_wht(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("WHT must be between 0 and 100.")
        return value


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------

class InvoiceReadSerializer(serializers.ModelSerializer):
    customer               = CustomerReadSerializer(read_only=True)
    items                  = InvoiceItemReadSerializer(many=True, read_only=True)
    created_by             = serializers.StringRelatedField(read_only=True)
    updated_by             = serializers.StringRelatedField(read_only=True)
    confirmed_by           = serializers.StringRelatedField(read_only=True)
    deleted_by             = serializers.StringRelatedField(read_only=True)
    draft_preview          = serializers.SerializerMethodField()
    print_preview          = serializers.SerializerMethodField()
    payment_status_display = serializers.CharField(source="get_payment_status_display", read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id", "bill_number", "customer", "status",
            "payment_type", "advance_amount", "payment_due_date",
            "subtotal", "gst_total", "wht_total", "grand_total",
            "total_cogs", "gross_profit",
            # payment summary inline on every invoice response
            "cash_received", "credit_outstanding", "total_paid",
            "remaining_amount", "payment_status", "payment_status_display",
            "draft_preview", "print_preview",
            "items",
            "confirmed_by", "confirmed_at",
            "created_by", "updated_by", "deleted_by",
            "created_at", "updated_at", "deleted_at",
        ]
        read_only_fields = fields

    _STAFF_ONLY_FIELDS = ("total_cogs", "gross_profit")

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not _is_staff_request(self.context):
            for field in self._STAFF_ONLY_FIELDS:
                data.pop(field, None)
        return data

    def get_draft_preview(self, obj):
        return _build_draft_preview(obj)

    def get_print_preview(self, obj):
        # Draft only — a confirmed invoice's real items/grand_total (already
        # in this same response) ARE its print content, no live calc needed.
        # Same shared get_invoice_print_context() the PDF itself renders
        # from (billing/utils.py), so the Invoice Preview page's draft
        # numbers can never drift from what actually prints — unlike
        # draft_preview above, which is a DIFFERENT, pre-discount/tax number
        # meant for staff profit-margin eyeballing, not customer-facing print.
        if obj.status != Invoice.Status.DRAFT:
            return None
        from .utils import get_invoice_print_context
        ctx = get_invoice_print_context(obj)
        return {
            "items": [
                {
                    **item,
                    "effective_price": str(item["effective_price"]) if item["effective_price"] is not None else None,
                    "line_total"     : str(item["line_total"]) if item["line_total"] is not None else None,
                }
                for item in ctx["items"]
            ],
            "grand_total": str(ctx["grand_total"]) if ctx["grand_total"] is not None else None,
        }


class InvoiceCreateSerializer(serializers.Serializer):
    customer_id    = serializers.IntegerField()
    payment_type   = serializers.ChoiceField(
        choices=["advance", "after_delivery"],
        default="after_delivery",
        required=False,
        help_text="advance: received before delivery. after_delivery: received after.",
    )
    advance_amount = serializers.DecimalField(
        max_digits=18, decimal_places=4, default=0, required=False,
        help_text="Required when payment_type=advance. Immediately added to cash in hand.",
    )
    method_allocations = MethodAllocationInputSerializer(
        many=True, required=False,
        help_text="Required when payment_type=advance — which method(s) the advance was received into, and how much of each.",
    )
    payment_due_date = serializers.DateField(
        required=False, allow_null=True,
        help_text="Defaults to today + 7 days if omitted.",
    )
    items = InvoiceItemWriteSerializer(many=True)

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


class InvoiceUpdateSerializer(serializers.Serializer):
    """Items, payment_type, and advance_amount can be changed on a draft invoice."""
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
    payment_due_date = serializers.DateField(required=False)
    items = InvoiceItemWriteSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item is required.")
        return value


class InvoiceDueDateUpdateSerializer(serializers.Serializer):
    """Used only by InvoiceDueDateUpdateView (confirmed invoices, admin-only)."""
    payment_due_date = serializers.DateField()


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------

class PaymentReadSerializer(serializers.ModelSerializer):
    created_by     = serializers.StringRelatedField(read_only=True)
    method_display = serializers.CharField(source="get_method_display", read_only=True)
    allocations    = serializers.SerializerMethodField()
    bill_number    = serializers.CharField(source="invoice.bill_number", read_only=True)
    customer_name  = serializers.CharField(source="invoice.customer.name", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id", "invoice", "bill_number", "customer_name", "reference_number", "amount",
            "method", "method_display", "allocations", "payment_date", "note",
            "created_by", "created_at",
        ]
        read_only_fields = fields

    def get_allocations(self, obj):
        from payment_methods.serializers import PaymentAllocationReadSerializer

        # Prefer the batch-prefetched map (list/nested contexts — see
        # PaymentListCreateView.list() / InvoicePaymentSummaryView) over a
        # live per-object query, which would N+1 across every payment on
        # the page/invoice.
        prefetched = self.context.get("payment_allocations")
        if prefetched is not None:
            rows = prefetched.get(obj.id, [])
        else:
            from payment_methods.selectors import get_allocations_for_source
            rows = get_allocations_for_source(obj)
        return PaymentAllocationReadSerializer(rows, many=True).data


class PaymentWriteSerializer(serializers.ModelSerializer):
    method_allocations = MethodAllocationInputSerializer(many=True)

    class Meta:
        model = Payment
        fields = ["invoice", "amount", "method_allocations", "payment_date", "note"]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Payment amount must be greater than zero.")
        return value

    def validate_method_allocations(self, value):
        if not value:
            raise serializers.ValidationError("At least one method must be selected.")
        return value


# ---------------------------------------------------------------------------
# Return
# ---------------------------------------------------------------------------

class ReturnItemWriteSerializer(serializers.Serializer):
    invoice_item_id = serializers.IntegerField()
    quantity        = serializers.IntegerField(min_value=1)


class ReturnCreateSerializer(serializers.Serializer):
    invoice_id = serializers.IntegerField()
    items      = ReturnItemWriteSerializer(many=True)
    note       = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item is required for a return.")
        return value


class ReturnUpdateSerializer(serializers.Serializer):
    items = ReturnItemWriteSerializer(many=True)
    note  = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item is required for a return.")
        return value


class ReturnItemReadSerializer(serializers.ModelSerializer):
    product_name       = serializers.CharField(source="invoice_item.product.name", read_only=True)
    product_code       = serializers.CharField(source="invoice_item.product.code", read_only=True)
    allocated_quantity = serializers.IntegerField(read_only=True)
    shelf_allocations  = ReturnItemShelfAllocationReadSerializer(many=True, read_only=True)

    class Meta:
        model = ReturnItem
        fields = [
            "id", "product_name", "product_code",
            "quantity", "selling_price", "cogs_per_unit",
            "line_total", "line_cogs",
            "allocated_quantity", "shelf_allocations",
        ]
        read_only_fields = fields

    _STAFF_ONLY_FIELDS = ("cogs_per_unit", "line_cogs")

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not _is_staff_request(self.context):
            for field in self._STAFF_ONLY_FIELDS:
                data.pop(field, None)
        return data


class ReturnReadSerializer(serializers.ModelSerializer):
    items               = ReturnItemReadSerializer(many=True, read_only=True)
    created_by          = serializers.StringRelatedField(read_only=True)
    accepted_by         = serializers.StringRelatedField(read_only=True)
    invoice_bill_number = serializers.CharField(source="invoice.bill_number", read_only=True)
    customer_name       = serializers.CharField(source="invoice.customer.name", read_only=True)

    class Meta:
        model = Return
        fields = [
            "id", "invoice", "invoice_bill_number", "customer_name", "reference_number", "status",
            "total_return_amount", "total_return_cogs",
            "items", "note",
            "accepted_by", "accepted_at",
            "created_by", "created_at", "updated_at",
        ]
        read_only_fields = fields

    _STAFF_ONLY_FIELDS = ("total_return_cogs",)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not _is_staff_request(self.context):
            for field in self._STAFF_ONLY_FIELDS:
                data.pop(field, None)
        return data


# ---------------------------------------------------------------------------
# Payment summary serializers
# ---------------------------------------------------------------------------

class InvoicePaymentSummarySerializer(serializers.ModelSerializer):
    """
    Full payment breakdown for a single invoice.
    Shows what was paid in cash, what in credit, what remains.
    """
    customer_name       = serializers.CharField(source="customer.name", read_only=True)
    customer_code       = serializers.CharField(source="customer.code", read_only=True)
    payment_status_display = serializers.CharField(source="get_payment_status_display", read_only=True)
    payments            = PaymentReadSerializer(many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id", "bill_number", "customer_name", "customer_code",
            "status", "subtotal", "grand_total",
            "cash_received", "credit_outstanding", "total_paid", "remaining_amount",
            "payment_status", "payment_status_display",
            "payments",
            "confirmed_at", "created_at",
        ]
        read_only_fields = fields


class CustomerOutstandingSerializer(serializers.Serializer):
    """Summary of what a customer owes across all their invoices."""
    customer_id          = serializers.IntegerField()
    total_billed         = serializers.DecimalField(max_digits=18, decimal_places=4)
    total_cash_received  = serializers.DecimalField(max_digits=18, decimal_places=4)
    total_credit_outstanding = serializers.DecimalField(max_digits=18, decimal_places=4)
    total_paid           = serializers.DecimalField(max_digits=18, decimal_places=4)
    total_remaining      = serializers.DecimalField(max_digits=18, decimal_places=4)


class CustomerWithOutstandingSerializer(serializers.ModelSerializer):
    """Used in the customer outstanding list — includes annotated outstanding field."""
    outstanding = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)

    class Meta:
        model = Customer
        fields = ["id", "name", "code", "mobile", "address", "outstanding"]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Saved PDF serializers
# ---------------------------------------------------------------------------

class SavedInvoicePDFSerializer(serializers.ModelSerializer):
    saved_by   = serializers.StringRelatedField(read_only=True)
    deleted_by = serializers.StringRelatedField(read_only=True)
    file_url   = serializers.SerializerMethodField()

    class Meta:
        from .models import SavedInvoicePDF
        model  = SavedInvoicePDF
        fields = [
            "id", "invoice", "file_name", "file_url", "is_draft",
            "saved_by", "created_at", "deleted_by", "deleted_at", "is_deleted",
        ]
        read_only_fields = fields

    def get_file_url(self, obj):
        if not obj.file_path:
            return None
        from django.conf import settings
        # Normalize any backslashes (Windows Path()) to forward slashes so the
        # URL is well-formed, and build off BACKEND_URL — not the request's
        # Host header — so this stays correct behind proxies and on deploy.
        path = obj.file_path.replace("\\", "/")
        return f"{settings.BACKEND_URL}{settings.MEDIA_URL}{path}"


class SavePDFRequestSerializer(serializers.Serializer):
    """
    Only confirmed invoices can be saved.
    Draft invoices can only be printed (use /print/?is_draft=true).
    """
    file_name = serializers.CharField(
        max_length=255, required=False,
        help_text="Custom file name. Defaults to bill number if not provided.",
    )

    def validate_file_name(self, value):
        return value.strip() if value else value