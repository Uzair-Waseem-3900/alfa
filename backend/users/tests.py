from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)

from backend.views import TriggerAllCatchUpsView

from .models import TokenFlushState, User
from .services import flush_expired_tokens
from .views import SuperuserChangePasswordView, UserListCreateView


def make_superuser(email="boss@example.com"):
    return User.objects.create_superuser(
        email=email, password="Sup3r-secret!", first_name="Boss", last_name="User"
    )


def make_user(email="worker@example.com"):
    return User.objects.create_user(
        email=email, password="N0rmal-secret!", first_name="Normal", last_name="User"
    )


def make_outstanding_token(user, *, expired, jti):
    now = timezone.now()
    return OutstandingToken.objects.create(
        user=user,
        jti=jti,
        token="x",
        created_at=now - timedelta(days=40),
        expires_at=now - timedelta(days=1) if expired else now + timedelta(days=30),
    )


class FlushExpiredTokensTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_flush_deletes_only_expired_tokens_and_cascades_blacklist(self):
        expired = make_outstanding_token(self.user, expired=True, jti="expired-1")
        BlacklistedToken.objects.create(token=expired)
        valid = make_outstanding_token(self.user, expired=False, jti="valid-1")

        deleted = flush_expired_tokens()

        self.assertGreater(deleted, 0)
        self.assertFalse(OutstandingToken.objects.filter(jti="expired-1").exists())
        self.assertFalse(BlacklistedToken.objects.filter(token=expired).exists())
        self.assertTrue(OutstandingToken.objects.filter(pk=valid.pk).exists())
        self.assertIsNotNone(TokenFlushState.get_instance().last_flushed_at)

    def test_flush_is_throttled_within_interval(self):
        flush_expired_tokens()
        make_outstanding_token(self.user, expired=True, jti="expired-2")

        self.assertEqual(flush_expired_tokens(), 0)
        self.assertTrue(OutstandingToken.objects.filter(jti="expired-2").exists())

    def test_flush_runs_again_after_interval_and_with_force(self):
        state = TokenFlushState.get_instance()
        state.last_flushed_at = timezone.now() - timedelta(hours=25)
        state.save(update_fields=["last_flushed_at"])
        make_outstanding_token(self.user, expired=True, jti="expired-3")

        self.assertGreater(flush_expired_tokens(), 0)

        make_outstanding_token(self.user, expired=True, jti="expired-4")
        self.assertGreater(flush_expired_tokens(force=True), 0)


class CatchUpEndpointTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = TriggerAllCatchUpsView.as_view()

    def test_non_admin_gets_403(self):
        request = self.factory.get("/api/system/catch-up/")
        force_authenticate(request, user=make_user())
        self.assertEqual(self.view(request).status_code, 403)

    def test_superuser_triggers_token_flush(self):
        superuser = make_superuser()
        make_outstanding_token(superuser, expired=True, jti="expired-catchup")

        request = self.factory.get("/api/system/catch-up/")
        force_authenticate(request, user=superuser)
        response = self.view(request)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["tokens_error"])
        self.assertGreater(response.data["tokens_flushed"], 0)
        self.assertFalse(OutstandingToken.objects.filter(jti="expired-catchup").exists())


class UserCreateIntegrityTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = UserListCreateView.as_view()
        self.superuser = make_superuser()
        self.payload = {
            "email": "worker@example.com",
            "first_name": "Dup",
            "last_name": "User",
            "password": "Str0ng-enough!",
            "role": "user",
        }

    def _post(self):
        request = self.factory.post("/users/", self.payload, format="json")
        force_authenticate(request, user=self.superuser)
        return self.view(request)

    def test_create_returns_created_user_without_refetch(self):
        response = self._post()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["email"], self.payload["email"])
        self.assertEqual(response.data["role"], "user")
        self.assertTrue(User.objects.filter(email=self.payload["email"]).exists())

    def test_duplicate_email_returns_400_from_serializer(self):
        make_user()
        response = self._post()
        self.assertEqual(response.status_code, 400)

    def test_duplicate_email_race_returns_400_not_500(self):
        make_user()
        # Bypass the serializer's exists() pre-check to simulate the
        # concurrent-create race, forcing the insert to hit the PK
        # constraint — the view must translate IntegrityError to a 400.
        with patch(
            "users.serializers.UserCreateSerializer.validate_email",
            side_effect=lambda self, value: value,
            autospec=True,
        ):
            response = self._post()
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)


class SuperuserChangePasswordTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = SuperuserChangePasswordView.as_view()
        self.superuser = make_superuser()

    def _patch(self, email):
        request = self.factory.patch(
            "/users/change-password/",
            {"email": email, "new_password": "N3w-secret-pw!", "confirm_password": "N3w-secret-pw!"},
            format="json",
        )
        force_authenticate(request, user=self.superuser)
        return self.view(request)

    def test_known_email_changes_password(self):
        target = make_user()
        response = self._patch(target.email)
        self.assertEqual(response.status_code, 200)
        target.refresh_from_db()
        self.assertTrue(target.check_password("N3w-secret-pw!"))

    def test_unknown_email_returns_404(self):
        response = self._patch("ghost@example.com")
        self.assertEqual(response.status_code, 404)
