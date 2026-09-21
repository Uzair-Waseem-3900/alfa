from django.conf import settings
from django.db import models


# ---------------------------------------------------------------------------
# Shared soft-delete infrastructure (mirrors billing.models/purchases.models
# pattern — each app keeps its own copy rather than importing another app's).
# ---------------------------------------------------------------------------

class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class AllObjectsManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset()


class AuditMixin(models.Model):
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="%(class)s_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="%(class)s_updated",
    )
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="%(class)s_deleted",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False, db_index=True)

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# SalesMan
# ---------------------------------------------------------------------------

class SalesMan(AuditMixin):
    """
    A sales man can own multiple SalesManLinkName rows (one-to-many). Each
    link name is permanently owned by whichever sales man created it — never
    reassigned to a different sales man, only added (new link name) or
    removed (soft-deleted, gated on zero linked customers — see services.py).

    total_customers/total_outstanding are stored O(1) fields, maintained by
    _adjust_sales_man_stats — the only writer for either field. Never
    recomputed live via Sum()/Count() on a read path (architecture.md).
    """

    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, unique=True, help_text="Internal unique employee code.")
    address = models.TextField(blank=True, default="")
    phone = models.CharField(max_length=20, blank=True, default="")

    total_customers = models.PositiveIntegerField(default=0)
    total_outstanding = models.DecimalField(max_digits=18, decimal_places=4, default=0)

    class Meta:
        verbose_name = "Sales Man"
        verbose_name_plural = "Sales Men"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


# ---------------------------------------------------------------------------
# SalesManLinkName
# ---------------------------------------------------------------------------

class SalesManLinkName(AuditMixin):
    """
    The middle segment of a customer code: PREFIX-<name>-suffix. Immutable
    once created (never renamed, never moved to a different SalesMan) —
    only created (add) or soft-deleted (remove, gated on zero non-deleted
    customers currently assigned to it — see services.delete_link_name).
    """

    name = models.CharField(max_length=50, unique=True, help_text="Stored upper-cased, e.g. FSD.")
    sales_man = models.ForeignKey(
        SalesMan, on_delete=models.PROTECT, related_name="link_names",
    )

    class Meta:
        verbose_name = "Sales Man Link Name"
        verbose_name_plural = "Sales Man Link Names"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} -> {self.sales_man.name}"
