from django.db import models


class ScoreTier(models.TextChoices):
    GOOD    = "good",    "Good (70+)"
    AVERAGE = "average", "Average (31-69)"
    POOR    = "poor",    "Poor (<=30)"


class CustomerCreditScore(models.Model):
    """
    Current-state snapshot — one row per customer, always exists (created
    immediately on customer creation, see credit_score.services.
    initialize_credit_score). Never queried live-aggregated; every read is
    an indexed lookup or an indexed tier filter (report/list pages).
    """

    customer = models.OneToOneField(
        "billing.Customer", on_delete=models.PROTECT, related_name="credit_score",
    )
    score = models.PositiveSmallIntegerField(default=50)
    tier = models.CharField(
        max_length=10, choices=ScoreTier.choices, default=ScoreTier.AVERAGE, db_index=True,
    )
    factor_breakdown = models.JSONField(
        default=dict, blank=True,
        help_text="Snapshot of each factor's contribution as of last_calculated_at.",
    )
    last_calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Customer Credit Score"
        verbose_name_plural = "Customer Credit Scores"

    def __str__(self):
        return f"{self.customer_id} — {self.score} ({self.tier})"


class CreditScoreHistory(models.Model):
    """
    Append-only event log — one row per recalculation. Never edited or
    deleted. Answers "why did this customer's score change" (current
    CustomerCreditScore.factor_breakdown only answers "what is it now").
    Always queried customer-scoped + paginated (indexed on customer,
    -created_at) — never a full-table scan regardless of how many
    customers or how long history grows.
    """

    customer = models.ForeignKey(
        "billing.Customer", on_delete=models.PROTECT, related_name="credit_score_history",
    )
    score_before = models.PositiveSmallIntegerField(null=True, blank=True)
    score_after = models.PositiveSmallIntegerField()
    tier_before = models.CharField(max_length=10, choices=ScoreTier.choices, null=True, blank=True)
    tier_after = models.CharField(max_length=10, choices=ScoreTier.choices)
    trigger = models.CharField(
        max_length=30,
        help_text="e.g. customer_created, invoice_confirmed, payment_received, "
                   "payment_deleted, return_accepted, due_date_extended, overdue_catchup",
    )
    reference = models.CharField(max_length=50, blank=True, default="")
    factor_breakdown = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["customer", "-created_at"])]
        verbose_name = "Credit Score History"
        verbose_name_plural = "Credit Score History"

    def __str__(self):
        return f"{self.customer_id}: {self.score_before}→{self.score_after} ({self.trigger})"


class CreditScoreFlow(models.Model):
    """
    Singleton catch-up marker. The Due Invoices tab itself needs no
    catch-up (it's a live filter on Invoice.payment_due_date, always
    correct) — this marker exists solely so a customer's STORED score
    gets corrected the first time it's read after an invoice quietly aged
    into "overdue" with no write event to trigger recalculation.
    """

    overdue_caught_up_through = models.DateField(null=True, blank=True)
    last_updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Credit Score Flow"
        verbose_name_plural = "Credit Score Flow"

    def __str__(self):
        return f"CreditScoreFlow — caught up through {self.overdue_caught_up_through}"

    @classmethod
    def get_instance(cls):
        instance, _ = cls.objects.get_or_create(pk=1)
        return instance
