from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Backfills purchases.ShelfStock from existing Inventory rows — every "
        "product with Inventory.quantity > 0 gets one ShelfStock row on the "
        "default shelf (get_default_shelf(), the earliest non-deleted shelf), "
        "via apply_shelf_delta (single writer, logs a ShelfStockMovement audit "
        "row with reason=BACKFILL). Idempotent/resumable: a product that "
        "already has ANY ShelfStock row was already processed by a prior "
        "(possibly interrupted) run of this command, so re-running skips it — "
        "safe to resume after a kill/timeout instead of double-counting "
        "quantity on already-backfilled products."
    )

    def handle(self, *args, **kwargs):
        from purchases.models import Inventory, ShelfStockMovement
        from purchases.services import apply_shelf_delta, get_default_shelf

        self.stdout.write("Starting shelf_stock backfill...\n")

        default_shelf = get_default_shelf()

        # Resumable: skip products that already have ANY ShelfStock row —
        # re-applying apply_shelf_delta on top of an existing row would
        # double-count quantity, so this backfill is meant to run exactly
        # once per product.
        candidates = Inventory.objects.filter(
            quantity__gt=0,
        ).exclude(
            product__shelf_stock_rows__isnull=False,
        ).select_related("product")

        total_to_process = candidates.count()
        already_done = Inventory.objects.filter(quantity__gt=0).count() - total_to_process

        created = 0
        for i, inventory in enumerate(candidates.iterator(), start=1):
            apply_shelf_delta(
                shelf=default_shelf,
                product=inventory.product,
                delta=inventory.quantity,
                reason=ShelfStockMovement.Reason.BACKFILL,
                reference="backfill_shelf_stock",
                user=None,
            )
            created += 1
            if i % 50 == 0 or i == total_to_process:
                self.stdout.write(f"  ...{i}/{total_to_process} products processed")

        self.stdout.write(f"  ShelfStock rows created this run: {created}")
        self.stdout.write(f"  products already done (skipped): {already_done}")
        self.stdout.write(self.style.SUCCESS("\nshelf_stock backfill complete."))
