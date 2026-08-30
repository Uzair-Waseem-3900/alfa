from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class UserManager(BaseUserManager):
    """
    Custom manager for User model where email is the unique identifier.
    """

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Email is required.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if not extra_fields.get("is_staff"):
            raise ValueError("Superuser must have is_staff=True.")
        if not extra_fields.get("is_superuser"):
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model using email as the primary key.

    Role mapping (no separate role table):
        - Normal user : is_staff=False, is_superuser=False
        - Admin       : is_staff=True,  is_superuser=False
        - Superuser   : is_staff=True,  is_superuser=True
    """

    email = models.EmailField(primary_key=True, unique=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = UserManager()

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["email"]

    def __str__(self):
        return self.email

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def role(self):
        if self.is_superuser and self.is_staff:
            return "superuser"
        if self.is_staff:
            return "admin"
        return "user"


# ---------------------------------------------------------------------------
# TokenFlushState  (singleton — mirrors CashFlow/TaxFlow/AssetFlow/ProfitFlow)
# ---------------------------------------------------------------------------

class TokenFlushState(models.Model):
    """
    Single live record tracking when expired JWT tokens were last flushed
    from SimpleJWT's OutstandingToken/BlacklistedToken tables. Those tables
    grow on every login and refresh (ROTATE_REFRESH_TOKENS +
    BLACKLIST_AFTER_ROTATION) and nothing else ever prunes them — the flush
    runs as a throttled catch-up via GET /api/system/catch-up/, and this
    row makes the "already flushed recently?" check O(1).
    """

    last_flushed_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When expired tokens were last flushed. Null = never flushed.",
    )

    class Meta:
        verbose_name = "Token Flush State"
        verbose_name_plural = "Token Flush State"

    def __str__(self):
        return f"TokenFlushState — last_flushed_at: {self.last_flushed_at}"

    @classmethod
    def get_instance(cls):
        """Always returns the single TokenFlushState record, creating it if needed."""
        instance, _ = cls.objects.get_or_create(pk=1)
        return instance
