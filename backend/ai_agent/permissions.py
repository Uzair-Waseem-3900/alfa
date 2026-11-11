from rest_framework.permissions import BasePermission


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
