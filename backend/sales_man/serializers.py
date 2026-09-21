from rest_framework import serializers

from .models import SalesMan, SalesManLinkName


class SalesManLinkNameReadSerializer(serializers.ModelSerializer):
    sales_man_name = serializers.CharField(source="sales_man.name", read_only=True)

    class Meta:
        model = SalesManLinkName
        fields = ["id", "name", "sales_man", "sales_man_name", "created_at"]
        read_only_fields = fields


class SalesManLinkNameCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=50)


class SalesManReadSerializer(serializers.ModelSerializer):
    created_by = serializers.StringRelatedField(read_only=True)
    updated_by = serializers.StringRelatedField(read_only=True)
    link_names = SalesManLinkNameReadSerializer(many=True, read_only=True)

    class Meta:
        model = SalesMan
        fields = [
            "id", "name", "code", "address", "phone",
            "total_customers", "total_outstanding", "link_names",
            "created_by", "updated_by", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "total_customers", "total_outstanding", "link_names",
            "created_by", "updated_by", "created_at", "updated_at",
        ]


class SalesManWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesMan
        fields = ["name", "code", "address", "phone"]

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Sales man name cannot be blank.")
        return value.strip()

    def validate_code(self, value):
        if not value.strip():
            raise serializers.ValidationError("Sales man code cannot be blank.")
        return value.strip()
