from rest_framework.permissions import BasePermission


class IsAdminOrSuperuser(BasePermission):
    """
    Full access for admins (is_staff=True) and superusers.
    Used for every endpoint in this app — financial statements are
    admin/superuser only, same rule as taxes/assets/cash_management.
    """
    message = "Only admins or superusers can perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_staff
        )
