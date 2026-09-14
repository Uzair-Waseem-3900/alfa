from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsAdminOrSuperuser(BasePermission):
    """
    Full access for admins (is_staff=True) and superusers only — stricter
    than IsAdminOrSuperuserOrReadOnly below. Used for the product cost
    (COGS) endpoint: cost is more sensitive than the public price-history
    trail, and this is only ever hit from the already-admin-only
    set/edit-price modal.
    """
    message = "Only admins or superusers can view product cost."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_staff
        )


class IsAdminOrSuperuserOrReadOnly(BasePermission):
    """
    Read  → any authenticated user.
    Write → admin (is_staff=True) or superuser only.
    Reuses the same role logic established in purchases/permissions.py.
    Kept here to keep each app self-contained and independently deployable.
    """

    message = "Only admins or superusers can modify rate lists."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.is_staff