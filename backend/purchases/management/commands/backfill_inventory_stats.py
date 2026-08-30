from django.core.management.base import BaseCommand
from django.db.models import Count, Q

from purchases.models import LOW_STOCK_THRESHOLD, Inventory, InventoryStatsFlow


class Command(BaseCommand):
    """
    Rebuilds the InventoryStatsFlow singleton from live Inventory data.

    Idempotent — recomputes absolute counts (never adds deltas), so running
    it any number of times converges to the same result. Counts cover
    inventory rows of non-deleted products only, matching the inventory
    list's product__is_deleted=False filter and the live maintenance in
    services.sync_inventory()/delete_product().
    """

    help = "Recompute InventoryStatsFlow (total/low-stock/out-of-stock counts) from live inventory."

    def handle(self, *args, **options):
        counts = Inventory.objects.filter(product__is_deleted=False).aggregate(
            total=Count("id"),
            low=Count("id", filter=Q(quantity__gt=0, quantity__lte=LOW_STOCK_THRESHOLD)),
            out=Count("id", filter=Q(quantity__lte=0)),
        )

        flow = InventoryStatsFlow.get_instance()
        flow.total_products     = counts["total"]
        flow.low_stock_count    = counts["low"]
        flow.out_of_stock_count = counts["out"]
        flow.save(update_fields=[
            "total_products", "low_stock_count", "out_of_stock_count", "last_updated_at",
        ])

        self.stdout.write(self.style.SUCCESS(
            f"InventoryStatsFlow rebuilt — total: {counts['total']}, "
            f"low stock: {counts['low']}, out of stock: {counts['out']}."
        ))
