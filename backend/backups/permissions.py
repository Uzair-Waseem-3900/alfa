from rest_framework.permissions import BasePermission


class IsAdminOrSuperuser(BasePermission):
    """
    Full access for admins (is_staff=True) and superusers.
    Normal users have zero access to the backups app.
    """
    message = "Only admins or superusers can access backups."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_staff
        )
