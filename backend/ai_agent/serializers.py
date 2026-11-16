from pydantic import ValidationError as PydanticValidationError
from rest_framework import serializers

from .models import Chat, ChatItem
from .schemas.requests import ChatTitleIn, SendMessageIn


class ChatSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chat
        fields = ["id", "title", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ChatOwnerSerializer(serializers.Serializer):
    """One row of the superuser 'team chats' user list (built from a values()/annotate() dict)."""
    email = serializers.EmailField(source="user")
    name = serializers.SerializerMethodField()
    is_superuser = serializers.BooleanField(source="user__is_superuser")
    chat_count = serializers.IntegerField()
    last_active = serializers.DateTimeField()

    def get_name(self, row):
        return f"{row['user__first_name']} {row['user__last_name']}".strip() or row["user"]


class TeamChatSerializer(ChatSerializer):
    """A chat plus who owns it (read-only superuser view)."""
    owner_email = serializers.EmailField(source="user_id", read_only=True)
    owner_name = serializers.SerializerMethodField()

    class Meta(ChatSerializer.Meta):
        fields = ChatSerializer.Meta.fields + ["owner_email", "owner_name"]
        read_only_fields = fields

    def get_owner_name(self, chat):
        return chat.user.full_name or chat.user_id


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
