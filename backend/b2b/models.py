import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class PurchaseRequest(models.Model):
    """
    A request THIS software has made to buy items from a partner software.

    Local-first: the row (with its private shelf plan) is saved before the
    partner is told, and `sent_at` stays null until the partner has confirmed
    it received it — so a request is never lost, and catch-up simply re-sends
    any unsent one (the partner treats a repeat of the same request_uuid as a
    no-op). Rows are never deleted once delivered; a cancelled request is just
    status=cancelled.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        DENIED = "denied", "Not accepted"
        CANCELLED = "cancelled", "Cancelled"

    provider_name = models.CharField(max_length=255)
    request_uuid = models.UUIDField(default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    note = models.CharField(max_length=500, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+",
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    # Null until the partner has acknowledged receipt.
    sent_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    # The confirmed purchase order created once an accepted request is imported.
    order = models.OneToOneField(
        "purchases.PurchaseOrder", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="b2b_purchase_request",
    )
    order_number = models.CharField(max_length=30, blank=True, default="")
    # Why the last attempt to import an accepted request failed ("" when fine).
    import_error = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "Purchase Request"
        verbose_name_plural = "Purchase Requests"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["provider_name", "request_uuid"], name="b2b_my_request_uuid_uniq"),
        ]
        indexes = [
            # Catch-up asks "is anything outstanding?" on every run; this partial index
            # holds ONLY the outstanding rows, so the answer stays instant however many
            # finished requests pile up.
            models.Index(
                fields=["created_at", "id"], name="b2b_my_req_outstanding_idx",
                condition=Q(status="pending") | Q(status="accepted", order__isnull=True),
            ),
        ]

    def __str__(self):
        return f"{self.provider_name} — {self.request_uuid} ({self.status})"


class PurchaseRequestItem(models.Model):
    request = models.ForeignKey(PurchaseRequest, on_delete=models.PROTECT, related_name="items")
    product = models.ForeignKey("purchases.Product", on_delete=models.PROTECT, related_name="+")
    # Snapshots of what was sent (the partner matches on code AND name).
    product_code = models.CharField(max_length=100)
    product_name = models.CharField(max_length=255)
    requested_quantity = models.PositiveIntegerField()
    discount = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    gst = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    wht = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    # Filled from the partner's decision. 0 = not supplied.
    accepted_quantity = models.PositiveIntegerField(null=True, blank=True)
    # The partner's effective unit price (selling price minus discount) — becomes
    # this software's purchase price so both ledgers agree.
    unit_price = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["request", "product"], name="b2b_my_request_item_product_uniq"),
        ]

    def __str__(self):
        return f"{self.product_code} x {self.requested_quantity}"


class PurchaseRequestShelf(models.Model):
    """
    This software's PRIVATE put-away plan for one requested line — which shelf
    the goods go to on arrival. Never sent to the partner.
    """
    item = models.ForeignKey(PurchaseRequestItem, on_delete=models.CASCADE, related_name="shelves")
    shelf = models.ForeignKey("purchases.Shelf", on_delete=models.PROTECT, related_name="+")
    quantity = models.PositiveIntegerField()

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["item", "shelf"], name="b2b_my_request_shelf_uniq"),
        ]


class SyncState(models.Model):
    """
    One row (pk=1). Marker for the catch-up phase: when the partner was last
    asked about undecided requests, so repeated catch-up calls never hit the
    partner more than once a minute. Same pattern as the other catch-up markers.
    """
    last_checked_at = models.DateTimeField(null=True, blank=True)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
