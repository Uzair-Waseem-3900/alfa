from django.shortcuts import get_object_or_404

from .models import User


def get_user_by_email(email: str) -> User:
    """Return a single User by email or raise 404."""
    return get_object_or_404(User, email=email)


def get_all_users() -> "QuerySet[User]":
    """Return all users ordered by email (model default)."""
    return User.objects.all()


def get_users_by_role(role: str) -> "QuerySet[User]":
    """
    Return users filtered by role string.
    Keeps role-to-flag mapping in ONE place.
    """
    role_filter = {
        "user": {"is_staff": False, "is_superuser": False},
        "admin": {"is_staff": True, "is_superuser": False},
        "superuser": {"is_staff": True, "is_superuser": True},
    }
    if role not in role_filter:
        return User.objects.none()
    return User.objects.filter(**role_filter[role])


def authenticate_user(email: str, password: str) -> User | None:
    """
    Return the User if credentials are valid and the account is active,
    otherwise return None.
    """
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return None

    if not user.check_password(password):
        return None
    if not user.is_active:
        return None
    return user