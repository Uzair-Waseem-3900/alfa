from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import User


# ---------------------------------------------------------------------------
# Read serializers
# ---------------------------------------------------------------------------

class UserReadSerializer(serializers.ModelSerializer):
    """
    Safe, read-only representation of a user — includes derived `role`.
    Reused across list, retrieve, and auth responses.
    """

    role = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "is_active", "role", "date_joined"]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Auth serializers
# ---------------------------------------------------------------------------

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


# ---------------------------------------------------------------------------
# Write serializers
# ---------------------------------------------------------------------------

class UserCreateSerializer(serializers.ModelSerializer):
    """
    Used exclusively by superusers to create new users (admin or normal).
    Password is write-only and validated against Django's AUTH_PASSWORD_VALIDATORS.
    """

    password = serializers.CharField(write_only=True, validators=[validate_password])
    role = serializers.ChoiceField(
        choices=["user", "admin"],
        write_only=True,
        help_text="'user' → normal user, 'admin' → staff admin.",
    )

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "password", "role"]

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value


class ProfileUpdateSerializer(serializers.ModelSerializer):
    """
    Allows any authenticated user to update their own first_name and last_name.
    Email (PK) is intentionally excluded.
    """

    class Meta:
        model = User
        fields = ["first_name", "last_name"]

    def validate_first_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("First name cannot be blank.")
        return value.strip()

    def validate_last_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Last name cannot be blank.")
        return value.strip()


class ChangePasswordSerializer(serializers.Serializer):
    """
    Validates a new-password + confirm-password pair.
    No current-password required per business logic.
    """

    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match."}
            )
        return attrs


class SuperuserChangePasswordSerializer(ChangePasswordSerializer):
    """
    Extends ChangePasswordSerializer with a target `email` field so a
    superuser can change another user's password by supplying their email.
    Inherits all password validation logic — no duplication.

    No existence check here: the service's get_user_by_email() already
    404s on an unknown email, and a serializer-level exists() would just
    re-fetch the same row.
    """

    email = serializers.EmailField()