from rest_framework.permissions import BasePermission


class IsSuperuser(BasePermission):
    """Read-only oversight of every user's assistant chats (team chats)."""
    message = "Only superusers can view other users' chats."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_active
            and request.user.is_superuser
        )


class IsAdminOrSuperuser(BasePermission):
    """
    The business assistant reads financial data, so it is an admin-level
    feature only — same rule as every other app's permissions.py.
    """
    message = "Only admins or superusers can use the assistant."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_staff
        )
