from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum

from cash_flow.models import CashFlow, CashMovement
from payment_methods.models import PaymentAllocation, PaymentMethod


class Command(BaseCommand):
    """
    Phase 1 bootstrap for the new accounts system:

    1. Seeds the protected `Cash` PaymentMethod row (get_or_create — safe
       to re-run).
    2. Sets Cash.balance = CashFlow.cash_in_hand. Accurate as-is: every
       historical payment was already normalized onto "cash" by
       normalize_payment_methods_to_cash before this app existed.
    3. Backfills one PaymentAllocation per active CashMovement row,
       pointing at Cash, mirroring amount/direction/source_model/
       source_id/date — so historical transactions are itemized, not left
       as an unexplained lump sum. get_or_create keyed on
       (source_model, source_id, payment_method) makes re-runs a no-op.
    4. Prints the three-way cross-check: Cash.balance, CashFlow.cash_in_hand,
       and sum(active PaymentAllocation for Cash) — must all agree.
    """

    help = "Seeds the protected Cash payment method and backfills historical CashMovement rows as allocations."

    @transaction.atomic
    def handle(self, *args, **options):
        cf = CashFlow.get_instance()

        cash, created = PaymentMethod.objects.get_or_create(
            name="Cash",
            defaults={"is_protected": True, "balance": cf.cash_in_hand},
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created protected 'Cash' method (id={cash.pk})."))
        else:
            if not cash.is_protected:
                cash.is_protected = True
            cash.balance = cf.cash_in_hand
            cash.save(update_fields=["is_protected", "balance"])
            self.stdout.write(f"'Cash' method already existed (id={cash.pk}) — balance re-synced.")

        existing_keys = set(
            PaymentAllocation.objects.filter(payment_method=cash).values_list("source_model", "source_id")
        )

        created_count = 0
        skipped_count = 0
        batch = []
        BATCH_SIZE = 500

        def flush(batch):
            nonlocal created_count
            if batch:
                PaymentAllocation.objects.bulk_create(batch)
                created_count += len(batch)
                batch.clear()

        for m in CashMovement.objects.filter(is_deleted=False).iterator(chunk_size=2000):
            key = (m.source_model, m.source_id)
            if key in existing_keys:
                skipped_count += 1
                continue
            existing_keys.add(key)
            batch.append(PaymentAllocation(
                payment_method=cash,
                source_model=m.source_model,
                source_id=m.source_id,
                direction=m.direction,
                amount=m.amount,
                date=m.date,
            ))
            if len(batch) >= BATCH_SIZE:
                flush(batch)
        flush(batch)

        self.stdout.write(f"PaymentAllocation rows created: {created_count}, already present: {skipped_count}")

        alloc_sum_in = PaymentAllocation.objects.filter(
            payment_method=cash, is_deleted=False, direction=PaymentAllocation.Direction.INFLOW,
        ).aggregate(total=Sum("amount"))["total"] or 0
        alloc_sum_out = PaymentAllocation.objects.filter(
            payment_method=cash, is_deleted=False, direction=PaymentAllocation.Direction.OUTFLOW,
        ).aggregate(total=Sum("amount"))["total"] or 0
        alloc_net = alloc_sum_in - alloc_sum_out

        self.stdout.write(self.style.SUCCESS(
            f"\nCross-check — Cash.balance: {cash.balance} | "
            f"CashFlow.cash_in_hand: {cf.cash_in_hand} | "
            f"sum(Cash allocations, inflow - outflow): {alloc_net}"
        ))
        if cash.balance == cf.cash_in_hand == alloc_net:
            self.stdout.write(self.style.SUCCESS("All three agree."))
        else:
            self.stdout.write(self.style.WARNING("Mismatch — investigate before proceeding to Phase 2."))
