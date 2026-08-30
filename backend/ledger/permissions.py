from rest_framework.permissions import BasePermission


class IsAdminOrSuperuser(BasePermission):
    message = "Only admins or superusers can access ledger data."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_staff
        )