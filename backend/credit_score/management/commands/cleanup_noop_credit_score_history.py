from django.core.management.base import BaseCommand
from django.db.models import F

from credit_score.models import CreditScoreHistory

_BATCH_SIZE = 500


class Command(BaseCommand):
    help = (
        "Deletes existing CreditScoreHistory rows that recorded zero actual "
        "change (score_before == score_after and tier_before == tier_after) "
        "— the no-op rows written before recalculate_credit_score was fixed "
        "(2026-08-31) to skip the write when nothing changed. Idempotent: "
        "safe to re-run, finds nothing to delete once cleaned. Dry-run by "
        "default — pass --apply to actually delete."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Actually delete the rows. Without this, only reports what would be deleted.",
        )

    def handle(self, *args, **kwargs):
        apply = kwargs.get("apply", False)

        # score_before/tier_before are null on the very first "customer_created"
        # row for every customer — F() comparison against a non-null
        # score_after/tier_after is never true for those, so they're safely
        # excluded without an extra isnull filter.
        noop_qs = CreditScoreHistory.objects.filter(
            score_before=F("score_after"), tier_before=F("tier_after"),
        )

        # Read ids in bounded chunks (read-only, no lock held across the
        # delete) rather than one unbounded query, per architecture.md's
        # batch-delete rule — this table is an append-only event log that
        # can grow into the hundreds of thousands of rows.
        ids = list(noop_qs.order_by("pk").values_list("pk", flat=True).iterator(chunk_size=_BATCH_SIZE))
        total = len(ids)

        if not apply:
            self.stdout.write(f"DRY RUN — would delete {total} no-op history row(s). Pass --apply to delete.")
            return

        deleted = 0
        for i in range(0, total, _BATCH_SIZE):
            batch = ids[i:i + _BATCH_SIZE]
            count, _ = CreditScoreHistory.objects.filter(pk__in=batch).delete()
            deleted += count
            self.stdout.write(f"  ...deleted {min(i + _BATCH_SIZE, total)}/{total}")

        self.stdout.write(self.style.SUCCESS(f"\nDeleted {deleted} no-op credit score history row(s)."))
