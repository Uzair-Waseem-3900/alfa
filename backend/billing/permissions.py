from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsAuthenticated(BasePermission):
    """All authenticated users — used for draft create/edit/delete and customer CRUD."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


class IsAdminOrSuperuser(BasePermission):
    """
    Admin (is_staff=True) or superuser only.
    Used for: confirm invoice, accept return.
    """

    message = "Only admins or superusers can perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_staff
        )


class IsAdminOrSuperuserOrReadOnly(BasePermission):
    """Read for all authenticated, write for admin/superuser. Used for payments."""

    message = "Only admins or superusers can record payments."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.is_staff