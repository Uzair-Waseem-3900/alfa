from decimal import Decimal

from rest_framework import serializers

from . import config
from .models import PurchaseRequest, PurchaseRequestItem


class ShelfAllocationInputSerializer(serializers.Serializer):
    shelf_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1)


class RequestItemInputSerializer(serializers.Serializer):
    product_id = serializers.IntegerField(min_value=1)       # THIS software's product
    quantity = serializers.IntegerField(min_value=1, max_value=1_000_000)
    discount = serializers.DecimalField(max_digits=10, decimal_places=4, default=Decimal("0"))
    gst = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100, default=Decimal("0"))
    wht = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100, default=Decimal("0"))
    shelf_allocations = ShelfAllocationInputSerializer(many=True, allow_empty=False, max_length=200)


class CreateRequestSerializer(serializers.Serializer):
    # Chosen by the form when it opens: a double-click or a retried POST then returns
    # the request that already exists instead of creating a second one.
    request_uuid = serializers.UUIDField(required=False)
    note = serializers.CharField(max_length=500, allow_blank=True, default="")
    items = RequestItemInputSerializer(many=True, allow_empty=False, max_length=config.MAX_REQUEST_ITEMS)

    def validate_items(self, items):
        if len(items) > config.MAX_REQUEST_ITEMS:
            raise serializers.ValidationError(f"At most {config.MAX_REQUEST_ITEMS} items per request.")
        return items


class PurchaseRequestListSerializer(serializers.ModelSerializer):
    created_by = serializers.StringRelatedField(read_only=True)
    item_count = serializers.IntegerField(read_only=True)
    delivered = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseRequest
        fields = [
            "id", "provider_name", "request_uuid", "status", "note", "created_by", "created_at",
            "decided_at", "order", "order_number", "import_error", "item_count", "delivered",
        ]
        read_only_fields = fields

    def get_delivered(self, request):
        return request.sent_at is not None


class RequestItemSerializer(serializers.ModelSerializer):
    shelves = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseRequestItem
        fields = [
            "id", "product", "product_code", "product_name", "requested_quantity",
            "accepted_quantity", "discount", "gst", "wht", "unit_price", "shelves",
        ]
        read_only_fields = fields

    def get_shelves(self, item):
        # Read as prefetched (selector select_related the shelf) — no extra queries.
        return [
            {"shelf_id": s.shelf_id, "shelf_name": s.shelf.name, "quantity": s.quantity}
            for s in item.shelves.all()
        ]


class PurchaseRequestDetailSerializer(PurchaseRequestListSerializer):
    items = RequestItemSerializer(many=True, read_only=True)

    class Meta(PurchaseRequestListSerializer.Meta):
        fields = PurchaseRequestListSerializer.Meta.fields + ["items"]
        read_only_fields = fields
