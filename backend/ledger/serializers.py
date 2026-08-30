from rest_framework import serializers

from .models import CustomerLedger, SavedCustomerLedgerPDF, SavedLedgerPDF, SupplierLedger


class SupplierLedgerReadSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(read_only=True)
    supplier_code = serializers.CharField(read_only=True)
    supplier_is_deleted = serializers.BooleanField(source="supplier.is_deleted", read_only=True)

    class Meta:
        model  = SupplierLedger
        fields = ["id", "supplier", "supplier_name", "supplier_code", "supplier_is_deleted", "created_at"]
        read_only_fields = fields


class LedgerEntrySerializer(serializers.Serializer):
    """Read-only — entries are computed dicts, not model instances."""
    date        = serializers.DateField()
    details     = serializers.CharField()
    reference   = serializers.CharField()
    entry_type  = serializers.CharField()
    debit       = serializers.DecimalField(max_digits=18, decimal_places=4)
    credit      = serializers.DecimalField(max_digits=18, decimal_places=4)
    balance     = serializers.DecimalField(max_digits=18, decimal_places=4)


class LedgerResponseSerializer(serializers.Serializer):
    """Wraps entries + closing balance in one response."""
    ledger          = SupplierLedgerReadSerializer()
    entries         = LedgerEntrySerializer(many=True)
    closing_balance = serializers.DecimalField(max_digits=18, decimal_places=4)
    date_from       = serializers.DateField(allow_null=True)
    date_to         = serializers.DateField(allow_null=True)


class SavedLedgerPDFSerializer(serializers.ModelSerializer):
    saved_by   = serializers.StringRelatedField(read_only=True)
    deleted_by = serializers.StringRelatedField(read_only=True)
    file_url   = serializers.SerializerMethodField()

    class Meta:
        model  = SavedLedgerPDF
        fields = [
            "id", "ledger", "file_name", "file_url",
            "date_from", "date_to",
            "saved_by", "created_at", "deleted_by", "deleted_at", "is_deleted",
        ]
        read_only_fields = fields

    def get_file_url(self, obj):
        if not obj.file_path:
            return None
        from django.conf import settings
        path = obj.file_path.replace("\\", "/")
        return f"{settings.BACKEND_URL}{settings.MEDIA_URL}{path}"


class SaveLedgerPDFRequestSerializer(serializers.Serializer):
    file_name = serializers.CharField(
        max_length=255, required=False,
        help_text="Custom file name. Defaults to supplier code if not provided.",
    )
    date_from = serializers.DateField(required=False, allow_null=True, default=None)
    date_to   = serializers.DateField(required=False, allow_null=True, default=None)

    def validate(self, attrs):
        df = attrs.get("date_from")
        dt = attrs.get("date_to")
        if df and dt and df > dt:
            raise serializers.ValidationError({"date_to": "date_to must be after date_from."})
        return attrs

    def validate_file_name(self, value):
        return value.strip() if value else value


# ---------------------------------------------------------------------------
# Customer ledger — mirrors the supplier serializers above.
# ---------------------------------------------------------------------------

class CustomerLedgerReadSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(read_only=True)
    customer_code = serializers.CharField(read_only=True)
    customer_is_deleted = serializers.BooleanField(source="customer.is_deleted", read_only=True)

    class Meta:
        model  = CustomerLedger
        fields = ["id", "customer", "customer_name", "customer_code", "customer_is_deleted", "created_at"]
        read_only_fields = fields


class CustomerLedgerResponseSerializer(serializers.Serializer):
    """Wraps entries + closing balance in one response."""
    ledger          = CustomerLedgerReadSerializer()
    entries         = LedgerEntrySerializer(many=True)
    closing_balance = serializers.DecimalField(max_digits=18, decimal_places=4)
    date_from       = serializers.DateField(allow_null=True)
    date_to         = serializers.DateField(allow_null=True)


class SavedCustomerLedgerPDFSerializer(serializers.ModelSerializer):
    saved_by   = serializers.StringRelatedField(read_only=True)
    deleted_by = serializers.StringRelatedField(read_only=True)
    file_url   = serializers.SerializerMethodField()

    class Meta:
        model  = SavedCustomerLedgerPDF
        fields = [
            "id", "ledger", "file_name", "file_url",
            "date_from", "date_to",
            "saved_by", "created_at", "deleted_by", "deleted_at", "is_deleted",
        ]
        read_only_fields = fields

    def get_file_url(self, obj):
        if not obj.file_path:
            return None
        from django.conf import settings
        path = obj.file_path.replace("\\", "/")
        return f"{settings.BACKEND_URL}{settings.MEDIA_URL}{path}"