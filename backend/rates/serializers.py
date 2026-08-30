from rest_framework import serializers

from purchases.serializers import ProductReadSerializer

from .models import ProductRate, ProductRateHistory


# ---------------------------------------------------------------------------
# ProductRateHistory serializer (read-only — append-only model)
# ---------------------------------------------------------------------------

class ProductRateHistorySerializer(serializers.ModelSerializer):
    changed_by = serializers.StringRelatedField(read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_code = serializers.CharField(source="product.code", read_only=True)

    class Meta:
        model = ProductRateHistory
        fields = [
            "id", "product_name", "product_code",
            "selling_price", "changed_by", "changed_at", "note",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# ProductRate read serializer
# ---------------------------------------------------------------------------

class ProductRateReadSerializer(serializers.ModelSerializer):
    product = ProductReadSerializer(read_only=True)
    updated_by = serializers.StringRelatedField(read_only=True)
    created_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = ProductRate
        fields = [
            "id", "product", "selling_price",
            "created_by", "updated_by", "created_at", "updated_at",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# ProductRate write serializers — separate for create vs update (DRY via base)
# ---------------------------------------------------------------------------

class ProductRateBaseWriteSerializer(serializers.Serializer):
    """
    Shared fields between create and update.
    Declared as a plain Serializer (not ModelSerializer) so both
    create and update serializers can inherit without model conflicts.
    """
    selling_price = serializers.DecimalField(max_digits=14, decimal_places=4)
    note = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        default="",
        help_text="Optional reason for price change.",
    )

    def validate_selling_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Selling price must be greater than zero.")
        return value


class ProductRateCreateSerializer(ProductRateBaseWriteSerializer):
    """Used for POST — requires product_id."""
    product_id = serializers.IntegerField()

    def validate_product_id(self, value):
        from purchases.models import Product
        if not Product.objects.filter(pk=value, is_deleted=False).exists():
            raise serializers.ValidationError("Product not found or has been deleted.")
        return value


class ProductRateUpdateSerializer(ProductRateBaseWriteSerializer):
    """Used for PATCH — only selling_price + note, product is immutable."""
    pass