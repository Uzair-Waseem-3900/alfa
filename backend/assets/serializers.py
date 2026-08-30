from rest_framework import serializers

from payment_methods.serializers import MethodAllocationInputSerializer

from .models import Asset, AssetCategory, AssetDisposal, AssetPayment, AssetValuationEntry


def _allocations_field(obj, context, context_key):
    """Shared body for every get_allocations method below — prefer the
    batch-prefetched map (list contexts) over a live per-object query,
    which would N+1 across every row on the page."""
    from payment_methods.serializers import PaymentAllocationReadSerializer

    prefetched = context.get(context_key)
    if prefetched is not None:
        rows = prefetched.get(obj.id, [])
    else:
        from payment_methods.selectors import get_allocations_for_source
        rows = get_allocations_for_source(obj)
    return PaymentAllocationReadSerializer(rows, many=True).data


class AssetStatsSerializer(serializers.Serializer):
    """Read-only serializer for the 6 asset stats."""
    total_asset_cost               = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_current_worth            = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_accumulated_depreciation = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_disposed_count           = serializers.IntegerField()
    total_gain_on_disposal         = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_loss_on_disposal         = serializers.DecimalField(max_digits=20, decimal_places=4)


# ---------------------------------------------------------------------------
# AssetCategory
# ---------------------------------------------------------------------------

class AssetCategoryReadSerializer(serializers.ModelSerializer):
    created_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model  = AssetCategory
        fields = ["id", "name", "valuation_method", "depreciation_rate", "created_by", "created_at", "updated_at"]
        read_only_fields = fields


class AssetCategoryCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = AssetCategory
        fields = ["name", "valuation_method", "depreciation_rate"]


class AssetCategoryUpdateSerializer(serializers.Serializer):
    """No valuation_method field — permanently locked after creation."""
    name              = serializers.CharField(max_length=255, required=False)
    depreciation_rate = serializers.DecimalField(max_digits=5, decimal_places=4, required=False)


# ---------------------------------------------------------------------------
# Asset
# ---------------------------------------------------------------------------

class AssetReadSerializer(serializers.ModelSerializer):
    category_name      = serializers.CharField(source="category.name", read_only=True)
    valuation_method    = serializers.CharField(source="category.valuation_method", read_only=True)
    created_by          = serializers.StringRelatedField(read_only=True)
    updated_by          = serializers.StringRelatedField(read_only=True)
    allocations         = serializers.SerializerMethodField()

    class Meta:
        model  = Asset
        fields = [
            "id", "name", "category", "category_name", "valuation_method",
            "acquisition_type", "cost", "acquisition_date", "current_worth",
            "note", "is_disposed", "allocations",
            "created_by", "updated_by", "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_allocations(self, obj):
        return _allocations_field(obj, self.context, "asset_allocations")


class AssetCreateSerializer(serializers.Serializer):
    name                = serializers.CharField(max_length=255)
    category            = serializers.PrimaryKeyRelatedField(queryset=AssetCategory.objects.all())
    acquisition_type    = serializers.ChoiceField(choices=Asset.AcquisitionType.choices)
    cost                = serializers.DecimalField(max_digits=18, decimal_places=4)
    acquisition_date    = serializers.DateField()
    method_allocations  = MethodAllocationInputSerializer(
        many=True, required=False,
        help_text="Required when acquisition_type=new. Not used for 'existing' — no cash moves.",
    )
    note                = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if attrs.get("acquisition_type") == Asset.AcquisitionType.NEW and not attrs.get("method_allocations"):
            raise serializers.ValidationError(
                {"method_allocations": "At least one method must be selected for a new (cash-purchased) asset."}
            )
        return attrs


# ---------------------------------------------------------------------------
# AssetValuationEntry
# ---------------------------------------------------------------------------

class AssetValuationEntryReadSerializer(serializers.ModelSerializer):
    asset_name = serializers.CharField(source="asset.name", read_only=True)
    created_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model  = AssetValuationEntry
        fields = [
            "id", "asset", "asset_name", "entry_type", "period", "rate_applied",
            "worth_before", "worth_after", "amount", "note",
            "created_by", "created_at",
        ]
        read_only_fields = fields


class AssetRevalueSerializer(serializers.Serializer):
    new_worth         = serializers.DecimalField(max_digits=18, decimal_places=4)
    revaluation_date  = serializers.DateField()
    note              = serializers.CharField(required=False, allow_blank=True, default="")


# ---------------------------------------------------------------------------
# AssetDisposal
# ---------------------------------------------------------------------------

class AssetDisposalReadSerializer(serializers.ModelSerializer):
    asset_name    = serializers.CharField(source="asset.name", read_only=True)
    category_name = serializers.CharField(source="asset.category.name", read_only=True)
    created_by    = serializers.StringRelatedField(read_only=True)
    allocations   = serializers.SerializerMethodField()

    class Meta:
        model  = AssetDisposal
        fields = [
            "id", "asset", "asset_name", "category_name", "disposal_type", "disposal_date",
            "sale_amount", "worth_at_disposal", "gain_loss", "reason", "allocations",
            "created_by", "created_at",
        ]
        read_only_fields = fields

    def get_allocations(self, obj):
        return _allocations_field(obj, self.context, "asset_disposal_allocations")


class AssetPaymentReadSerializer(serializers.ModelSerializer):
    asset_name    = serializers.CharField(source="asset.name", read_only=True)
    category_name = serializers.CharField(source="asset.category.name", read_only=True)
    created_by    = serializers.StringRelatedField(read_only=True)
    allocations   = serializers.SerializerMethodField()
    gain_loss     = serializers.SerializerMethodField()
    reason        = serializers.SerializerMethodField()

    class Meta:
        model  = AssetPayment
        fields = [
            "id", "asset", "asset_name", "category_name", "payment_type", "direction",
            "amount", "date", "gain_loss", "reason", "allocations",
            "created_by", "created_at",
        ]
        read_only_fields = fields

    def get_gain_loss(self, obj):
        if obj.payment_type != AssetPayment.PaymentType.SALE:
            return None
        disposal = getattr(obj.asset, "disposal", None)
        return disposal.gain_loss if disposal else None

    def get_reason(self, obj):
        if obj.payment_type != AssetPayment.PaymentType.SALE:
            return None
        disposal = getattr(obj.asset, "disposal", None)
        return disposal.reason if disposal else ""

    def get_allocations(self, obj):
        from payment_methods.serializers import PaymentAllocationReadSerializer

        # Prefer the batch-prefetched map (list context — see
        # AssetPaymentListView.list()) over a live per-object query. Keyed
        # by AssetPayment.id, NOT source_id — Asset.pk and AssetDisposal.pk
        # are independent sequences and can collide.
        prefetched = self.context.get("asset_payment_allocations")
        if prefetched is not None:
            rows = prefetched.get(obj.id, [])
        else:
            from payment_methods.models import PaymentAllocation
            rows = PaymentAllocation.objects.filter(
                source_model=obj.source_model, source_id=obj.source_id, is_deleted=False,
            ).select_related("payment_method").order_by("id")
        return PaymentAllocationReadSerializer(rows, many=True).data


class AssetDisposeSerializer(serializers.Serializer):
    disposal_type       = serializers.ChoiceField(choices=AssetDisposal.DisposalType.choices)
    disposal_date       = serializers.DateField()
    sale_amount         = serializers.DecimalField(max_digits=18, decimal_places=4, required=False, allow_null=True)
    method_allocations  = MethodAllocationInputSerializer(
        many=True, required=False,
        help_text="Required when disposal_type=sold. Not used for 'scrapped' — no cash moves.",
    )
    reason              = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if attrs.get("disposal_type") == AssetDisposal.DisposalType.SOLD and not attrs.get("method_allocations"):
            raise serializers.ValidationError(
                {"method_allocations": "At least one method must be selected for a sold asset."}
            )
        return attrs
