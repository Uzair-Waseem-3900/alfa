from rest_framework.permissions import BasePermission


class IsSuperuser(BasePermission):
    """
    Grants access only to superusers (is_staff=True AND is_superuser=True).
    """

    message = "Only superusers can perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_staff
            and request.user.is_superuser
        )


class IsAdminOrSuperuser(BasePermission):
    """
    Grants access to admins (is_staff=True) and superusers.
    """

    message = "Only admins or superusers can perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_staff
        )


class IsOwnerOrSuperuser(BasePermission):
    """
    Object-level permission: allows the object owner or a superuser.
    The view's queryset must expose a `email` field (or any PK) that
    maps to `request.user.email`.
    """

    message = "You can only modify your own account."

    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser and request.user.is_staff:
            return True
        return obj.email == request.user.email