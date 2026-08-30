from django.core.management.base import BaseCommand
from django.db import transaction

from assets.models import Asset, AssetDisposal, AssetPayment


class Command(BaseCommand):
    help = (
        "Rebuilds the AssetPayment event table from Asset (acquisition_type=new) "
        "and AssetDisposal (disposal_type=sold). Idempotent — wipes and "
        "reconstructs, so it is also the repair tool if the event table ever "
        "drifts from the sources. Existing installs need this once, for any "
        "assets/disposals created before AssetPayment existed."
    )

    @transaction.atomic
    def handle(self, *args, **kwargs):
        self.stdout.write("Rebuilding AssetPayment events from source tables...\n")

        deleted, _ = AssetPayment.objects.all().delete()
        self.stdout.write(f"  wiped {deleted} existing event rows")

        batch = []

        for asset in Asset.objects.filter(is_deleted=False, acquisition_type=Asset.AcquisitionType.NEW):
            batch.append(AssetPayment(
                asset=asset, payment_type=AssetPayment.PaymentType.PURCHASE,
                direction=AssetPayment.Direction.OUTFLOW, amount=asset.cost, date=asset.acquisition_date,
                source_model="assets.asset", source_id=asset.pk, created_by=asset.created_by,
            ))

        for disposal in AssetDisposal.objects.filter(
            disposal_type=AssetDisposal.DisposalType.SOLD,
        ).select_related("asset"):
            batch.append(AssetPayment(
                asset=disposal.asset, payment_type=AssetPayment.PaymentType.SALE,
                direction=AssetPayment.Direction.INFLOW, amount=disposal.sale_amount, date=disposal.disposal_date,
                source_model="assets.assetdisposal", source_id=disposal.pk, created_by=disposal.created_by,
            ))

        AssetPayment.objects.bulk_create(batch, batch_size=500)
        self.stdout.write(self.style.SUCCESS(
            f"\nAssetPayment backfill complete — {len(batch)} events created."
        ))
