from rest_framework.permissions import BasePermission


class IsSuperuserOnly(BasePermission):
    """
    Superuser only — deliberately stricter than IsAdminOrSuperuser (used
    everywhere else in this project for "admin or superuser"). The activity
    log surfaces every user's actions across the whole system, including
    admins'; an admin auditing themselves defeats the point.
    """
    message = "Only superusers can view the activity log."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_superuser
        )
