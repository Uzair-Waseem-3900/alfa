from decimal import Decimal

from django.core.management.base import BaseCommand

from assets.models import Asset, AssetCategory, AssetDisposal, AssetFlow, AssetValuationEntry
from assets.services import _catch_up_asset_depreciation


class Command(BaseCommand):
    help = "Runs catch-up depreciation for every asset, recomputes each asset's current_worth from its full history, then rebuilds the AssetFlow singleton from scratch."

    def handle(self, *args, **kwargs):
        self.stdout.write("Starting Assets backfill...\n")

        # 1. Catch-up first — make sure every active asset has every entry
        #    it should already have, up to the current month.
        active_assets = Asset.objects.filter(is_deleted=False, is_disposed=False).select_related("category")
        for asset in active_assets:
            _catch_up_asset_depreciation(asset)
        self.stdout.write(f"  Ran catch-up for {active_assets.count()} active assets")

        # 2. Recompute every non-deleted asset's current_worth from scratch —
        #    cost + sum of every posted AssetValuationEntry amount — guards
        #    against any drift between the stored field and its own history.
        for asset in Asset.objects.filter(is_deleted=False):
            entries = AssetValuationEntry.objects.filter(asset=asset)
            change = sum((e.amount for e in entries), Decimal("0"))
            asset.current_worth = asset.cost + change
            asset.save(update_fields=["current_worth"])

        # Reset singleton — EVERY field this command touches must be reset here.
        af, _ = AssetFlow.objects.get_or_create(pk=1)
        af.total_asset_cost               = Decimal("0")
        af.total_current_worth            = Decimal("0")
        af.total_accumulated_depreciation = Decimal("0")
        af.total_disposed_count           = 0
        af.total_gain_on_disposal         = Decimal("0")
        af.total_loss_on_disposal         = Decimal("0")
        af.save()

        # 3. Totals over active (non-disposed, non-deleted) assets only.
        for asset in Asset.objects.filter(is_deleted=False, is_disposed=False).select_related("category"):
            af.total_asset_cost    += asset.cost
            af.total_current_worth += asset.current_worth
            if asset.category.valuation_method == AssetCategory.ValuationMethod.DEPRECIATION:
                af.total_accumulated_depreciation += (asset.cost - asset.current_worth)
        self.stdout.write(f"  total_asset_cost: {af.total_asset_cost}")
        self.stdout.write(f"  total_current_worth: {af.total_current_worth}")
        self.stdout.write(f"  total_accumulated_depreciation: {af.total_accumulated_depreciation}")

        # 4. Disposal totals.
        for d in AssetDisposal.objects.all():
            af.total_disposed_count += 1
            if d.disposal_type == AssetDisposal.DisposalType.SOLD and d.gain_loss is not None:
                if d.gain_loss >= 0:
                    af.total_gain_on_disposal += d.gain_loss
                else:
                    af.total_loss_on_disposal += -d.gain_loss
        self.stdout.write(f"  total_disposed_count: {af.total_disposed_count}")
        self.stdout.write(f"  total_gain_on_disposal: {af.total_gain_on_disposal}")
        self.stdout.write(f"  total_loss_on_disposal: {af.total_loss_on_disposal}")

        af.save()
        self.stdout.write(self.style.SUCCESS("\nAssets backfill complete."))
        self.stdout.write(f"""
Final AssetFlow state:
  total_asset_cost               : {af.total_asset_cost}
  total_current_worth            : {af.total_current_worth}
  total_accumulated_depreciation : {af.total_accumulated_depreciation}
  total_disposed_count           : {af.total_disposed_count}
  total_gain_on_disposal         : {af.total_gain_on_disposal}
  total_loss_on_disposal         : {af.total_loss_on_disposal}
""")
