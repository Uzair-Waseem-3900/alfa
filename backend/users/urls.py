from django.urls import path

from .views import (
    LoginView,
    LogoutView,
    ProfileRetrieveUpdateView,
    SelfChangePasswordView,
    SuperuserChangePasswordView,
    TokenRefreshView,
    UserDeleteView,
    UserListCreateView,
)

# URL design:
#   /auth/*  → authentication (login, logout, token refresh)
#   /users/  → user management

auth_urlpatterns = [
    path("login/", LoginView.as_view(), name="auth-login"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("token/refresh/", TokenRefreshView.as_view(), name="auth-token-refresh"),
]

user_urlpatterns = [
    # Superuser-only
    path("", UserListCreateView.as_view(), name="user-list-create"),          # GET + POST
    path("<str:email>/delete/", UserDeleteView.as_view(), name="user-delete"),
    path("change-password/", SuperuserChangePasswordView.as_view(), name="superuser-change-password"),

    # Self-service (any authenticated user)
    path("me/", ProfileRetrieveUpdateView.as_view(), name="user-me"),
    path("me/change-password/", SelfChangePasswordView.as_view(), name="self-change-password"),
]