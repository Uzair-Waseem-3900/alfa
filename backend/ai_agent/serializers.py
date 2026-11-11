from pydantic import ValidationError as PydanticValidationError
from rest_framework import serializers

from .models import Chat, ChatItem
from .schemas.requests import ChatTitleIn, SendMessageIn


class ChatSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chat
        fields = ["id", "title", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ChatTitleSerializer(serializers.Serializer):
    """Validated by the pydantic model so the rule lives in schemas/ only."""
    title = serializers.CharField()

    def validate(self, attrs):
        try:
            return ChatTitleIn(**attrs).model_dump()
        except PydanticValidationError as exc:
            raise serializers.ValidationError({"title": [e["msg"] for e in exc.errors()]})


class MessageSerializer(serializers.ModelSerializer):
    role = serializers.CharField(source="kind", read_only=True)

    class Meta:
        model = ChatItem
        fields = ["id", "role", "text", "created_at"]


class SendMessageSerializer(serializers.Serializer):
    content = serializers.CharField()

    def validate(self, attrs):
        try:
            return SendMessageIn(**attrs).model_dump()
        except PydanticValidationError as exc:
            raise serializers.ValidationError(
                {"content": [e["msg"].removeprefix("Value error, ") for e in exc.errors()]}
            )
