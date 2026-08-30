from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsAdminOrSuperuser(BasePermission):
    """
    Full access for admins (is_staff=True) and superusers.
    Used for all purchase order writes, confirmations, returns, payments.
    Normal users have zero access to purchases.
    """
    message = "Only admins or superusers can perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_staff
        )


class IsAdminOrSuperuserOrReadOnly(BasePermission):
    """
    Read access for all authenticated users.
    Write access only for admins and superusers.
    Used exclusively for Inventory — normal users can view stock levels.
    """
    message = "Only admins or superusers can modify this resource."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.is_staff