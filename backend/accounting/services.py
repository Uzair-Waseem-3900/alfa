from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import BalanceSheetSnapshot


def catch_up_balance_sheet_snapshots(*, user=None) -> int:
    """
    Catch-up on read (no cron) — but NOT the same shape as
    profits.catch_up_monthly_profits, on purpose. MonthlyProfit's per-month
    figures come from DATE-BOUNDED queries (_compute_expenses_paid(first_day,
    last_day), etc.), so they stay correct no matter how late the catch-up
    actually runs. Balance Sheet has no such luxury: every figure here comes
    from an ALL-TIME singleton (CashFlow.cash_in_hand, etc.) that only knows
    "right now" — it has no memory of what it looked like at a past month's
    end. So this function can only ever freeze the SINGLE most recently
    finished month, using whatever the live singletons say at the moment
    it's called, and ONLY if that hasn't already been frozen.

    It deliberately does NOT attempt to backfill snapshots for older
    finalized months — there is no correct number to backfill them with
    (today's live state is not "as of" any past month), so those periods
    simply never get a BalanceSheetSnapshot; get_balance_sheet_for_period()
    raises DoesNotExist for them and the caller surfaces that honestly
    rather than showing a wrong number.

    Real consequence: this snapshot is only accurate if this function is
    called promptly after the month rolls over (same day or the next),
    before much of the new month's activity has happened — every day of
    delay bleeds new-month transactions into what's supposed to be
    last-month's figures, with no way to detect or correct that after the
    fact. Materially more fragile than MonthlyProfit's own catch-up timing
    assumption, precisely because MonthlyProfit's queries don't have this
    problem and Balance Sheet's structurally can't avoid it.
    """
    from profits.models import MonthlyProfit

    from .selectors import get_balance_sheet_live

    today = timezone.localdate()
    current_period = f"{today.year:04d}-{today.month:02d}"

    last_finished_period = (
        MonthlyProfit.objects
        .exclude(period=current_period)
        .order_by("-period")
        .values_list("period", flat=True)
        .first()
    )
    if last_finished_period is None:
        return 0
    if BalanceSheetSnapshot.objects.filter(period=last_finished_period).exists():
        return 0

    live = get_balance_sheet_live()
    try:
        with transaction.atomic():
            BalanceSheetSnapshot.objects.create(
                period=last_finished_period,
                cash_in_hand=live["assets"]["cash_in_hand"],
                accounts_receivable=live["assets"]["accounts_receivable"],
                inventory_value=live["assets"]["inventory_value"],
                fixed_assets_nbv=live["assets"]["fixed_assets_nbv"],
                total_assets=live["assets"]["total"],
                accounts_payable=live["liabilities"]["accounts_payable"],
                gst_payable=live["liabilities"]["gst_payable"],
                wht_payable=live["liabilities"]["wht_payable"],
                total_liabilities=live["liabilities"]["total"],
                owner_capital=live["equity"]["owner_capital"],
                investor_capital=live["equity"]["investor_capital"],
                opening_balance_equity=live["equity"]["opening_balance_equity"],
                pre_owned_asset_equity=live["equity"]["pre_owned_asset_equity"],
                asset_revaluation_surplus=live["equity"]["asset_revaluation_surplus"],
                retained_earnings=live["equity"]["retained_earnings"],
                total_equity=live["equity"]["total"],
            )
    except IntegrityError:
        # Another concurrent catch-up already froze this period — fine.
        return 0

    return 1
