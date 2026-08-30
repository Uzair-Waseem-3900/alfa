from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsAdminOrSuperuser(BasePermission):
    """Same rule as every app's own permissions.py."""
    message = "Only admins or superusers can perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_staff
        )


class IsAdminOrSuperuserOrReadOnly(BasePermission):
    """Any authenticated user can view credit-score data; only admins/
    superusers can trigger a write (manual recalculation, due-date edits
    live in billing and already gate through billing's own permission)."""
    message = "Only admins or superusers can perform this action."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user.is_staff)
