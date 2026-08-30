from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Asset, AssetCategory, AssetDisposal, AssetFlow, AssetPayment, AssetValuationEntry


def _add_months(year: int, month: int, delta: int) -> tuple:
    """Month-only arithmetic, no external date libraries needed. Mirrors
    cash_flow.selectors._add_months exactly."""
    total = (year * 12 + (month - 1)) + delta
    return total // 12, (total % 12) + 1


def _record_asset_payment(asset, *, source, payment_type, direction, amount, date, user) -> AssetPayment:
    """Writes one AssetPayment event row. `source` is the SAME row
    payment_methods.services.record_allocations was called against right
    before this (the Asset itself for a purchase, the AssetDisposal for a
    sale) — source_model/source_id snapshot it so the payment's real method
    split can be looked back up later."""
    return AssetPayment.objects.create(
        asset=asset, payment_type=payment_type, direction=direction, amount=amount, date=date,
        source_model=f"{source._meta.app_label}.{source._meta.model_name}", source_id=source.pk,
        created_by=user,
    )


# ---------------------------------------------------------------------------
# Internal atomic AssetFlow adjuster — NEVER call from outside this module
# ---------------------------------------------------------------------------

def _adjust_asset_flow(
    *,
    total_asset_cost_delta               : Decimal = Decimal("0"),
    total_current_worth_delta            : Decimal = Decimal("0"),
    total_accumulated_depreciation_delta : Decimal = Decimal("0"),
    total_disposed_count_delta           : int = 0,
    total_gain_on_disposal_delta         : Decimal = Decimal("0"),
    total_loss_on_disposal_delta         : Decimal = Decimal("0"),
    user,
) -> AssetFlow:
    """
    Atomically adjusts the AssetFlow singleton by the given deltas.
    Positive delta = increase. Negative delta = decrease (e.g. disposal
    removing an asset's cost/worth from the totals). This is the ONLY
    function that writes to AssetFlow.
    """
    with transaction.atomic():
        af = AssetFlow.objects.select_for_update().get_or_create(pk=1)[0]

        af.total_asset_cost = max(
            Decimal("0"), af.total_asset_cost + total_asset_cost_delta
        )
        # NOT floored at 0 — same reasoning as cash_flow._adjust_cashflow's
        # cash_in_hand. This is a live balance (the net book value of every
        # asset still held), not a cumulative counter, and it feeds the
        # Balance Sheet's fixed_assets_nbv directly.
        #
        # With max(0, ...) any delta that would take it negative had the
        # excess silently DISCARDED, so the total no longer matched
        # sum(Asset.current_worth) and every later movement built on the
        # wrong base — permanently, with no error and no way to detect it.
        # If it ever does go negative, that means depreciation/disposal
        # deltas have outrun what was actually added, which is a real bug
        # worth seeing rather than hiding.
        #
        # The genuinely cumulative counters below (accumulated depreciation,
        # gain/loss on disposal, disposed count) keep their floors — those
        # only ever move one way, so a floor there guards a value that
        # should never be negative rather than destroying information.
        af.total_current_worth = af.total_current_worth + total_current_worth_delta
        af.total_accumulated_depreciation = max(
            Decimal("0"), af.total_accumulated_depreciation + total_accumulated_depreciation_delta
        )
        af.total_disposed_count = max(
            0, af.total_disposed_count + total_disposed_count_delta
        )
        af.total_gain_on_disposal = max(
            Decimal("0"), af.total_gain_on_disposal + total_gain_on_disposal_delta
        )
        af.total_loss_on_disposal = max(
            Decimal("0"), af.total_loss_on_disposal + total_loss_on_disposal_delta
        )

        af.last_updated_by = user
        af.save()
        return af


# ---------------------------------------------------------------------------
# Catch-up depreciation — the core "no cron" mechanism
# ---------------------------------------------------------------------------

def _catch_up_asset_depreciation(asset: Asset, user=None) -> None:
    """
    Posts any AssetValuationEntry rows that should already exist for this
    asset, up to and including the current month, using reducing-balance
    depreciation. Called from every read path (asset detail, asset list,
    stats) as well as right after creating an 'existing' asset (to back-fill
    its full history) — this is what replaces a scheduled job: the "tick"
    happens whenever anyone actually looks, not on a timer.

    No-op for revaluation/none-method categories, disposed assets, or a
    zero/unset rate.
    """
    if asset.is_disposed:
        return
    if asset.category.valuation_method != AssetCategory.ValuationMethod.DEPRECIATION:
        return

    rate = asset.category.depreciation_rate
    if rate <= 0:
        return

    today = timezone.localdate()
    current_month_start = date(today.year, today.month, 1)

    last_entry = AssetValuationEntry.objects.filter(
        asset=asset, entry_type=AssetValuationEntry.EntryType.DEPRECIATION,
    ).order_by("-period").first()

    if last_entry:
        ly, lm = (int(p) for p in last_entry.period.split("-"))
        ny, nm = _add_months(ly, lm, 1)
    else:
        # First-ever entry starts the month AFTER acquisition — the
        # acquisition month itself isn't a completed period of ownership.
        ny, nm = _add_months(asset.acquisition_date.year, asset.acquisition_date.month, 1)

    next_date = date(ny, nm, 1)
    precision = Decimal("0.0001")

    while next_date <= current_month_start:
        months_since_acquisition = (
            (next_date.year - asset.acquisition_date.year) * 12
            + (next_date.month - asset.acquisition_date.month)
        )
        asset_year_index = (months_since_acquisition - 1) // 12  # 0-indexed 12-month block
        book_value_start_of_year = asset.cost * (Decimal("1") - rate) ** asset_year_index
        annual_depreciation = book_value_start_of_year * rate
        monthly_depreciation = (annual_depreciation / Decimal("12")).quantize(
            precision, rounding=ROUND_HALF_UP
        )

        worth_before = asset.current_worth
        worth_after = worth_before - monthly_depreciation
        period_str = f"{next_date.year:04d}-{next_date.month:02d}"

        try:
            # Savepoint so a unique-constraint hit doesn't poison an outer
            # transaction (catch-up runs inside atomic services too).
            with transaction.atomic():
                AssetValuationEntry.objects.create(
                    asset=asset,
                    entry_type=AssetValuationEntry.EntryType.DEPRECIATION,
                    period=period_str,
                    rate_applied=rate,
                    worth_before=worth_before,
                    worth_after=worth_after,
                    amount=-monthly_depreciation,
                    note="Auto-posted monthly depreciation (catch-up)",
                    created_by=user,
                )
        except IntegrityError:
            # uniq_asset_depreciation_period: a concurrent catch-up already
            # posted this month (and everything after it) — pick up its
            # result and stop instead of double-depreciating.
            asset.refresh_from_db(fields=["current_worth"])
            return

        asset.current_worth = worth_after
        asset.save(update_fields=["current_worth"])

        _adjust_asset_flow(
            total_current_worth_delta=-monthly_depreciation,
            total_accumulated_depreciation_delta=+monthly_depreciation,
            user=user,
        )

        ny2, nm2 = _add_months(next_date.year, next_date.month, 1)
        next_date = date(ny2, nm2, 1)


def catch_up_all_asset_depreciation(user=None) -> None:
    """
    Runs depreciation catch-up for every active asset, gated by an O(1)
    month marker on AssetFlow: depreciation only ever becomes due at a month
    boundary (a new asset's first entry is due the month AFTER acquisition,
    and 'existing' assets are fully back-filled inside create_asset), so
    once everything is posted through the current month there is nothing to
    check until the 1st of the next month. update_asset_category resets the
    marker on a rate change, so a new rate still takes effect on the very
    next read — same timing as before the marker. Posting math unchanged.
    """
    today = timezone.localdate()
    current_period = f"{today.year:04d}-{today.month:02d}"

    af = AssetFlow.get_instance()
    if af.depreciation_caught_up_through == current_period:
        return

    for asset in Asset.objects.filter(is_deleted=False, is_disposed=False).select_related("category"):
        _catch_up_asset_depreciation(asset, user=user)

    # update() — not save() — so the marker stamp doesn't touch last_updated_at.
    AssetFlow.objects.filter(pk=1).update(depreciation_caught_up_through=current_period)


# ---------------------------------------------------------------------------
# AssetCategory services
# ---------------------------------------------------------------------------

def _validate_depreciation_rate(rate: Decimal) -> None:
    """
    depreciation_rate is a FRACTION (0.15 == 15%), stored as
    DecimalField(max_digits=5, decimal_places=4) — so the largest value the
    column can physically hold is 9.9999.

    Only `rate > 0` was checked before, which meant someone typing 15 for
    "15%" was written successfully and then poisoned the row: every
    subsequent read raised decimal.InvalidOperation trying to fit 15.00 into
    5 digits with 4 decimal places, taking down the whole assets app until
    the row was deleted by hand. A silent write that bricks later reads is
    far worse than a rejected write.

    Upper bound is 1 (100%) rather than the column's 9.9999: this is a
    reducing-balance rate, so anything above 100% would write off more than
    the asset is worth and drive current_worth negative.
    """
    from rest_framework.exceptions import ValidationError

    if rate <= 0:
        raise ValidationError(
            {"depreciation_rate": "Depreciation rate must be greater than zero."}
        )
    if rate > 1:
        raise ValidationError({
            "depreciation_rate":
                f"Depreciation rate is a fraction between 0 and 1 — enter 0.15 for 15%, "
                f"not 15. Got {rate}.",
        })


def create_asset_category(
    *, name: str, valuation_method: str, depreciation_rate: Decimal = Decimal("0"), user,
) -> AssetCategory:
    from rest_framework.exceptions import ValidationError

    if not name.strip():
        raise ValidationError({"name": "Category name cannot be blank."})
    if AssetCategory.objects.filter(name__iexact=name.strip()).exists():
        raise ValidationError({"name": "An asset category with this name already exists."})
    if valuation_method not in AssetCategory.ValuationMethod.values:
        raise ValidationError({"valuation_method": "Must be 'depreciation', 'revaluation', or 'none'."})
    if valuation_method == AssetCategory.ValuationMethod.DEPRECIATION:
        _validate_depreciation_rate(depreciation_rate)

    return AssetCategory.objects.create(
        name=name.strip(),
        valuation_method=valuation_method,
        depreciation_rate=depreciation_rate if valuation_method == AssetCategory.ValuationMethod.DEPRECIATION else Decimal("0"),
        created_by=user,
    )


def update_asset_category(
    *, pk: int, name: str = None, depreciation_rate: Decimal = None, user,
) -> AssetCategory:
    """
    Deliberately has NO valuation_method parameter — it is permanently
    locked at creation. depreciation_rate is editable, but only affects
    AssetValuationEntry rows posted after this change (see
    _catch_up_asset_depreciation, which snapshots rate_applied per entry).
    """
    from django.shortcuts import get_object_or_404
    from rest_framework.exceptions import ValidationError

    category = get_object_or_404(AssetCategory, pk=pk)

    if name is not None:
        if not name.strip():
            raise ValidationError({"name": "Category name cannot be blank."})
        category.name = name.strip()

    rate_changed = False
    if depreciation_rate is not None:
        if category.valuation_method != AssetCategory.ValuationMethod.DEPRECIATION:
            raise ValidationError({"depreciation_rate": "Only depreciation-method categories have a rate."})
        _validate_depreciation_rate(depreciation_rate)
        rate_changed = category.depreciation_rate != depreciation_rate
        category.depreciation_rate = depreciation_rate

    category.save(update_fields=["name", "depreciation_rate", "updated_at"])

    if rate_changed:
        # Reset the month marker so the next read re-runs the catch-up sweep
        # with the NEW rate — a rate edit takes effect on the next read (from
        # the current month forward), never delayed to month-end; already-
        # posted months are immune via their rate_applied snapshot.
        AssetFlow.objects.filter(pk=1).update(depreciation_caught_up_through="")

    return category


# ---------------------------------------------------------------------------
# Asset services
# ---------------------------------------------------------------------------

@transaction.atomic
def create_asset(
    *, name: str, category_id: int, acquisition_type: str, cost: Decimal,
    acquisition_date, method_allocations: list = None, note: str = "", user,
) -> Asset:
    """
    existing: no cash movement; catch-up immediately back-fills every
              historical AssetValuationEntry from acquisition_date to today.
              method_allocations not required — nothing to allocate.
    new     : cash_in_hand decreases by cost (real cash left the business);
              catch-up runs too but finds nothing to post yet.
              method_allocations required.
    """
    from django.shortcuts import get_object_or_404
    from rest_framework.exceptions import ValidationError

    if cost <= 0:
        raise ValidationError({"cost": "Cost must be greater than zero."})
    if acquisition_type not in Asset.AcquisitionType.values:
        raise ValidationError({"acquisition_type": "Must be 'existing' or 'new'."})
    if acquisition_type == Asset.AcquisitionType.NEW and not method_allocations:
        raise ValidationError({"method_allocations": "At least one method must be selected for a new (cash-purchased) asset."})

    category = get_object_or_404(AssetCategory, pk=category_id)

    asset = Asset.objects.create(
        name=name,
        category=category,
        acquisition_type=acquisition_type,
        cost=cost,
        acquisition_date=acquisition_date,
        current_worth=cost,
        note=note,
        created_by=user,
        updated_by=user,
    )

    _adjust_asset_flow(
        total_asset_cost_delta=+cost,
        total_current_worth_delta=+cost,
        user=user,
    )

    if acquisition_type == Asset.AcquisitionType.NEW:
        from cash_flow.services import record_cash_movement, sync_asset_purchased
        sync_asset_purchased(amount=cost, user=user)
        record_cash_movement(asset)

        from payment_methods.services import record_allocations
        record_allocations(
            asset, direction="outflow", splits=method_allocations,
            total_amount=cost, date=acquisition_date, user=user,
        )

        _record_asset_payment(
            asset, source=asset, payment_type=AssetPayment.PaymentType.PURCHASE,
            direction=AssetPayment.Direction.OUTFLOW, amount=cost, date=acquisition_date, user=user,
        )

    _catch_up_asset_depreciation(asset, user=user)

    return asset


@transaction.atomic
def revalue_asset(
    *, asset_id: int, new_worth: Decimal, revaluation_date, note: str = "", user,
) -> AssetValuationEntry:
    """Manual revaluation — only for revaluation-method categories (e.g. Land)."""
    from django.shortcuts import get_object_or_404
    from rest_framework.exceptions import ValidationError

    if new_worth < 0:
        raise ValidationError({"new_worth": "New worth cannot be negative."})

    asset = get_object_or_404(
        Asset.objects.select_for_update().select_related("category"),
        pk=asset_id, is_deleted=False, is_disposed=False,
    )

    if asset.category.valuation_method != AssetCategory.ValuationMethod.REVALUATION:
        raise ValidationError({
            "detail": f"'{asset.category.name}' is not a revaluation-method category — only revaluation-method assets can be revalued."
        })

    worth_before = asset.current_worth
    amount = new_worth - worth_before
    period = f"{revaluation_date.year:04d}-{revaluation_date.month:02d}"

    entry = AssetValuationEntry.objects.create(
        asset=asset,
        entry_type=AssetValuationEntry.EntryType.REVALUATION,
        period=period,
        rate_applied=None,
        worth_before=worth_before,
        worth_after=new_worth,
        amount=amount,
        note=note,
        created_by=user,
    )

    asset.current_worth = new_worth
    asset.updated_by = user
    asset.save(update_fields=["current_worth", "updated_by", "updated_at"])

    _adjust_asset_flow(total_current_worth_delta=amount, user=user)

    return entry


@transaction.atomic
def dispose_asset(
    *, asset_id: int, disposal_type: str, disposal_date, sale_amount: Decimal = None,
    method_allocations: list = None, reason: str = "", user,
) -> AssetDisposal:
    """
    scrapped: no cash movement, just an audit record. worth/cost removed
              from AssetFlow totals. method_allocations not required.
    sold    : cash_in_hand increases by sale_amount; gain_loss computed
              against worth_at_disposal (after running catch-up, so the
              comparison uses an up-to-date book value). method_allocations
              required.
    """
    from django.shortcuts import get_object_or_404
    from rest_framework.exceptions import ValidationError

    if disposal_type not in AssetDisposal.DisposalType.values:
        raise ValidationError({"disposal_type": "Must be 'scrapped' or 'sold'."})
    if disposal_type == AssetDisposal.DisposalType.SOLD and (not sale_amount or sale_amount <= 0):
        raise ValidationError({"sale_amount": "Sale amount is required and must be greater than zero when selling an asset."})
    if disposal_type == AssetDisposal.DisposalType.SOLD and not method_allocations:
        raise ValidationError({"method_allocations": "At least one method must be selected for a sold asset."})

    asset = get_object_or_404(
        Asset.objects.select_for_update().select_related("category"),
        pk=asset_id, is_deleted=False, is_disposed=False,
    )

    _catch_up_asset_depreciation(asset, user=user)

    worth_at_disposal = asset.current_worth
    is_depreciable = asset.category.valuation_method == AssetCategory.ValuationMethod.DEPRECIATION
    accumulated_depreciation_for_asset = (asset.cost - asset.current_worth) if is_depreciable else Decimal("0")

    disposal = AssetDisposal.objects.create(
        asset=asset,
        disposal_type=disposal_type,
        disposal_date=disposal_date,
        sale_amount=sale_amount if disposal_type == AssetDisposal.DisposalType.SOLD else None,
        worth_at_disposal=worth_at_disposal,
        reason=reason,
        created_by=user,
    )

    flow_kwargs = dict(
        total_asset_cost_delta=-asset.cost,
        total_current_worth_delta=-asset.current_worth,
        total_accumulated_depreciation_delta=-accumulated_depreciation_for_asset,
        total_disposed_count_delta=+1,
        user=user,
    )

    if disposal_type == AssetDisposal.DisposalType.SOLD:
        gain_loss = sale_amount - worth_at_disposal
        disposal.gain_loss = gain_loss
        disposal.save(update_fields=["gain_loss"])

        if gain_loss >= 0:
            flow_kwargs["total_gain_on_disposal_delta"] = gain_loss
        else:
            flow_kwargs["total_loss_on_disposal_delta"] = -gain_loss

        from cash_flow.services import record_cash_movement, sync_asset_sold
        sync_asset_sold(amount=sale_amount, user=user)
        record_cash_movement(disposal)

        from payment_methods.services import record_allocations
        record_allocations(
            disposal, direction="inflow", splits=method_allocations,
            total_amount=sale_amount, date=disposal_date, user=user,
        )

        _record_asset_payment(
            asset, source=disposal, payment_type=AssetPayment.PaymentType.SALE,
            direction=AssetPayment.Direction.INFLOW, amount=sale_amount, date=disposal_date, user=user,
        )

    _adjust_asset_flow(**flow_kwargs)

    asset.is_disposed = True
    asset.updated_by = user
    asset.save(update_fields=["is_disposed", "updated_by", "updated_at"])

    return disposal
