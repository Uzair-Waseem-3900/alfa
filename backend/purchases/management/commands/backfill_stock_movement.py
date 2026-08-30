from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.db.models.functions import Coalesce


class Command(BaseCommand):
    help = "Backfills ProductStockMovement and StockMovementFlow from existing purchases/returns/invoices/returns."

    def handle(self, *args, **kwargs):
        from purchases.models import (
            LostInventoryItem, LostInventoryRecovery, Product, ProductStockMovement,
            PurchaseItem, PurchaseReturnItem, StockMovementFlow,
        )
        from billing.models import Invoice, InvoiceItem, ReturnItem

        self.stdout.write("Starting stock movement backfill...\n")

        # Idempotent — reset every product's row (and the flow singleton)
        # before resumming, same discipline as every other backfill command.
        ProductStockMovement.objects.all().delete()
        StockMovementFlow.objects.all().delete()

        zero = 0

        # Opening stock (is_data_entry PurchaseOrders) DOES count here,
        # unlike every other is_data_entry exclusion in this file — it's
        # real physical quantity, already reflected in Inventory.quantity.
        # Mirrors purchases.services.create_opening_stock_order's live sync.
        purchased_by_product = dict(
            PurchaseItem.objects.filter(
                is_deleted=False, order__is_deleted=False, order__status="confirmed",
            ).values("product_id").annotate(total=Coalesce(Sum("quantity"), zero)).values_list("product_id", "total")
        )

        purchase_returned_by_product = {}
        for row in PurchaseReturnItem.objects.filter(
            return_record__is_deleted=False, return_record__status="accepted",
            purchase_item__order__is_data_entry=False,
        ).values("purchase_item__product_id").annotate(total=Coalesce(Sum("quantity"), zero)):
            purchase_returned_by_product[row["purchase_item__product_id"]] = row["total"]

        sold_by_product = dict(
            InvoiceItem.objects.filter(
                invoice__is_deleted=False, invoice__is_data_entry=False,
            ).exclude(invoice__status="draft").values("product_id")
            .annotate(total=Coalesce(Sum("quantity"), zero)).values_list("product_id", "total")
        )

        sale_returned_by_product = {}
        for row in ReturnItem.objects.filter(
            return_record__is_deleted=False, return_record__status="accepted",
            invoice_item__invoice__is_data_entry=False,
        ).values("invoice_item__product_id").annotate(total=Coalesce(Sum("quantity"), zero)):
            sale_returned_by_product[row["invoice_item__product_id"]] = row["total"]

        # Lost/found — no is_data_entry concept here (LostInventoryRecord has
        # no such flag; every loss/recovery is a real operational event).
        lost_by_product = dict(
            LostInventoryItem.objects.filter(record__is_deleted=False)
            .values("product_id").annotate(total=Coalesce(Sum("quantity"), zero)).values_list("product_id", "total")
        )
        found_by_product = dict(
            LostInventoryRecovery.objects.all()
            .values("lost_item__product_id").annotate(total=Coalesce(Sum("quantity"), zero))
            .values_list("lost_item__product_id", "total")
        )

        product_ids = set(purchased_by_product) | set(purchase_returned_by_product) \
            | set(sold_by_product) | set(sale_returned_by_product) \
            | set(lost_by_product) | set(found_by_product)

        flow_purchased = flow_purchase_returned = flow_sold = flow_sale_returned = 0
        flow_lost = flow_found = 0

        rows = []
        for product_id in product_ids:
            purchased = purchased_by_product.get(product_id, 0)
            purchase_returned = purchase_returned_by_product.get(product_id, 0)
            sold = sold_by_product.get(product_id, 0)
            sale_returned = sale_returned_by_product.get(product_id, 0)
            lost = lost_by_product.get(product_id, 0)
            found = found_by_product.get(product_id, 0)

            rows.append(ProductStockMovement(
                product_id=product_id,
                total_purchased=purchased,
                total_purchase_returned=purchase_returned,
                total_sold=sold,
                total_sale_returned=sale_returned,
                total_lost=lost,
                total_found=found,
            ))

            flow_purchased += purchased
            flow_purchase_returned += purchase_returned
            flow_sold += sold
            flow_sale_returned += sale_returned
            flow_lost += lost
            flow_found += found

        ProductStockMovement.objects.bulk_create(rows)

        flow = StockMovementFlow.get_instance()
        flow.total_purchased = flow_purchased
        flow.total_purchase_returned = flow_purchase_returned
        flow.total_sold = flow_sold
        flow.total_sale_returned = flow_sale_returned
        flow.total_lost = flow_lost
        flow.total_found = flow_found
        flow.save()

        self.stdout.write(f"  products with movement: {len(rows)}")
        self.stdout.write(f"  total_purchased: {flow_purchased}")
        self.stdout.write(f"  total_purchase_returned: {flow_purchase_returned}")
        self.stdout.write(f"  total_sold: {flow_sold}")
        self.stdout.write(f"  total_sale_returned: {flow_sale_returned}")
        self.stdout.write(f"  total_lost: {flow_lost}")
        self.stdout.write(f"  total_found: {flow_found}")
        self.stdout.write(self.style.SUCCESS("\nStock movement backfill complete."))
