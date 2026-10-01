from rest_framework.permissions import BasePermission


class IsAdminOrSuperuser(BasePermission):
    """
    Admins (is_staff=True) and superusers only — the whole b2b app is an
    admin-level concern. Same permission model as payment_methods.
    """
    message = "Only admins or superusers can perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_staff
        )
