from django.db import IntegrityError, transaction
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError

from .models import User
from .permissions import IsOwnerOrSuperuser, IsSuperuser
from .selectors import authenticate_user, get_all_users
from .serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    ProfileUpdateSerializer,
    SuperuserChangePasswordSerializer,
    UserCreateSerializer,
    UserReadSerializer,
)
from .services import (
    change_password,
    create_user,
    delete_user,
    generate_tokens_for_user,
    logout_user,
    superuser_change_password,
    update_profile,
)

# Re-export alias used in urls.py — keeps urls.py import clean
__all__ = [
    "LoginView",
    "LogoutView",
    "TokenRefreshView",
    "UserListCreateView",
    "UserDeleteView",
    "SuperuserChangePasswordView",
    "ProfileRetrieveUpdateView",
    "SelfChangePasswordView",
]


# ---------------------------------------------------------------------------
# Auth views
# ---------------------------------------------------------------------------

class LoginView(APIView):
    """
    POST /auth/login/
    Public endpoint. Returns JWT pair + user info including role.
    """

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate_user(
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if not user:
            return Response(
                {"detail": "Invalid credentials or inactive account."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        tokens = generate_tokens_for_user(user)
        user_data = UserReadSerializer(user).data
        return Response({**user_data, **tokens}, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """
    POST /auth/logout/
    Blacklists the refresh token. Requires authentication.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"detail": "Refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            logout_user(refresh_token)
        except TokenError:
            return Response(
                {"detail": "Token is invalid or already blacklisted."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"detail": "Successfully logged out."}, status=status.HTTP_200_OK)


class TokenRefreshView(APIView):
    """
    POST /auth/token/refresh/
    Thin wrapper — delegates to SimpleJWT's RefreshToken so we keep
    one consistent URL namespace under /auth/.
    """

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        from rest_framework_simplejwt.serializers import TokenRefreshSerializer

        serializer = TokenRefreshSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError:
            return Response(
                {"detail": "Refresh token is invalid, expired, or already blacklisted."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Superuser-only: user management
# ---------------------------------------------------------------------------

class UserListCreateView(generics.ListCreateAPIView):
    """
    GET  /users/ — superuser lists all users.
    POST /users/ — superuser creates a new admin or normal user.
    """

    permission_classes = [IsSuperuser]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return UserCreateSerializer
        return UserReadSerializer

    def get_queryset(self):
        return get_all_users()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            # The serializer's exists() check can race a concurrent create —
            # the PK constraint is the real guard, so a duplicate insert must
            # surface as a 400, not a 500. atomic() keeps the failed insert
            # on a savepoint so any surrounding transaction stays usable.
            with transaction.atomic():
                user = create_user(
                    email=data["email"],
                    first_name=data["first_name"],
                    last_name=data["last_name"],
                    password=data["password"],
                    role=data["role"],
                )
        except IntegrityError:
            return Response(
                {"email": ["A user with this email already exists."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(UserReadSerializer(user).data, status=status.HTTP_201_CREATED)


class UserDeleteView(generics.DestroyAPIView):
    """
    DELETE /users/<email>/
    Superuser deletes any user (except themselves).
    """

    permission_classes = [IsSuperuser]
    lookup_field = "email"

    def get_queryset(self):
        return User.objects.all()

    def destroy(self, request, *args, **kwargs):
        target_email = kwargs.get("email")
        try:
            delete_user(target_email=target_email, requesting_user=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "User deleted successfully."}, status=status.HTTP_200_OK)


class SuperuserChangePasswordView(generics.UpdateAPIView):
    """
    PATCH /users/change-password/
    Superuser changes any user's password by supplying their email.
    """

    serializer_class = SuperuserChangePasswordSerializer
    permission_classes = [IsSuperuser]
    http_method_names = ["patch"]

    def patch(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        superuser_change_password(
            target_email=serializer.validated_data["email"],
            new_password=serializer.validated_data["new_password"],
        )
        return Response({"detail": "Password updated successfully."}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Self-service views (any authenticated user on their own account)
# ---------------------------------------------------------------------------

class ProfileRetrieveUpdateView(generics.RetrieveUpdateAPIView):
    """
    GET  /users/me/  — retrieve own profile
    PATCH /users/me/ — update own first_name / last_name
    """

    permission_classes = [IsAuthenticated, IsOwnerOrSuperuser]
    http_method_names = ["get", "patch"]

    def get_serializer_class(self):
        if self.request.method == "GET":
            return UserReadSerializer
        return ProfileUpdateSerializer

    def get_object(self):
        user = self.request.user
        self.check_object_permissions(self.request, user)
        return user

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", True)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        updated_user = update_profile(
            user=instance,
            first_name=serializer.validated_data.get("first_name"),
            last_name=serializer.validated_data.get("last_name"),
        )
        return Response(UserReadSerializer(updated_user).data, status=status.HTTP_200_OK)


class SelfChangePasswordView(generics.UpdateAPIView):
    """
    PATCH /users/me/change-password/
    Any authenticated user changes their OWN password.
    """

    serializer_class = ChangePasswordSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["patch"]

    def patch(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        change_password(
            user=request.user,
            new_password=serializer.validated_data["new_password"],
        )
        return Response({"detail": "Password updated successfully."}, status=status.HTTP_200_OK)