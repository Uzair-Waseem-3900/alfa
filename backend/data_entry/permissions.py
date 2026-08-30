from rest_framework.permissions import BasePermission


class IsSuperuser(BasePermission):
    """
    Superuser-only access. Every data-entry endpoint requires is_superuser=True.
    """
    message = "Only the superuser can access data-entry endpoints."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_superuser
        )
