from rest_framework.permissions import BasePermission


class IsAdminOrSuperuser(BasePermission):
    """Admin (is_staff=True) or superuser only. Reports are admin/superuser-only."""

    message = "Only admins or superusers can access reports."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_staff
        )
