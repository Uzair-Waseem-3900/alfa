from datetime import date, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from .models import (
    InvestorProfitPayout, MonthlyProfit, MonthlyProfitInvestorShare,
    MonthlyProfitOwnerShare, OwnerProfitPayout, ProfitFlow,
)


# ---------------------------------------------------------------------------
# Small date helpers — no external date libraries needed
# ---------------------------------------------------------------------------

def _add_months(year: int, month: int, delta: int) -> tuple:
    total = (year * 12 + (month - 1)) + delta
    return total // 12, (total % 12) + 1


def _month_bounds(period: str) -> tuple:
    y, m = (int(p) for p in period.split("-"))
    first_day = date(y, m, 1)
    ny, nm = _add_months(y, m, 1)
    last_day = date(ny, nm, 1) - timedelta(days=1)
    return first_day, last_day


def _earliest_period():
    """The month of the earliest confirmed, non-draft, non-data-entry invoice — nothing to report before this."""
    from billing.models import Invoice

    first = (
        Invoice.objects.filter(is_deleted=False, is_data_entry=False)
        .exclude(status=Invoice.Status.DRAFT)
        .order_by("confirmed_at")
        .values_list("confirmed_at", flat=True)
        .first()
    )
    if not first:
        return None
    first_local = timezone.localtime(first)
    return f"{first_local.year:04d}-{first_local.month:02d}"


# ---------------------------------------------------------------------------
# Per-month deduction computations — each scoped to [first_day, last_day]
# ---------------------------------------------------------------------------

def compute_month_figures_in_one_query(first_day, last_day, period: str) -> dict:
    """
    The same ten month figures the _compute_* helpers below return, but in ONE
    round-trip instead of ten.

    Why: each helper is a single-row `.aggregate()` against a different table.
    Individually they're cheap and correctly indexed — the cost is purely that
    there are ten network round-trips. Against Supabase at ~100ms each that's
    ~1 second, and it is paid on EVERY read of the live Income Statement and
    the live Balance Sheet (which reuses this path). architecture.md's 200ms
    rule is about query COUNT for exactly this reason.

    Deliberately used ONLY by the live current-month path, NOT by
    catch_up_monthly_profits. That function writes MonthlyProfit rows which
    are frozen forever and never recomputed, so an error there would be
    permanent and undetectable; and it runs once a month, where ten round
    trips cost a second that nobody notices. Fixing the hot path while leaving
    the irreversible writer on the long-proven code is the whole point — the
    ten helpers remain the single definition of each predicate, and
    ProfitsEquivalenceTests asserts this function returns byte-identical
    values to them.

    Each figure is a correlated scalar subquery hung off the ProfitFlow
    singleton (guaranteed to exist via get_instance), grouped by a constant so
    every subquery yields exactly one row. Coalesce handles the empty-table
    case, which a bare Subquery would return as NULL.
    """
    from django.db.models import DecimalField, IntegerField, OuterRef, Subquery, Value
    from django.db.models.functions import Coalesce

    from assets.models import AssetDisposal, AssetValuationEntry
    from cash_flow.models import Expense
    from cash_management.models import CashAdjustment
    from purchases.models import LostInventoryRecord, LostInventoryRecovery
    from purchases.selectors import _day_start, _next_day_start
    from recurring_expenses.models import RecurringExpenseAssignmentPayment
    from taxes.models import TaxPayment, WHTPayment

    money = DecimalField(max_digits=20, decimal_places=4)

    def scalar(qs, field):
        """One-row scalar sum of `field` over `qs`, safe on an empty table."""
        # .order_by() FIRST, to clear the model's Meta.ordering.
        #
        # Without it Django appends those ordering columns to the generated
        # SQL, and a .values().annotate() GROUP BY then references a column
        # that is neither grouped nor aggregated. SQLite silently allows that;
        # PostgreSQL rejects it outright:
        #     ProgrammingError: column "u0.expense_date" must appear in the
        #     GROUP BY clause or be used in an aggregate function
        # Caught only by running this against real Postgres — every local
        # SQLite test passed. Ordering is meaningless for a scalar sum anyway.
        grouped = (
            qs.order_by()
            .values(_g=Value(1, output_field=IntegerField()))
            .annotate(_t=Sum(field))
            .values("_t")[:1]
        )
        return Coalesce(Subquery(grouped, output_field=money), Value(Decimal("0")),
                        output_field=money)

    # Predicates below are copied verbatim from the individual helpers. Any
    # divergence is caught by the equivalence test, not left to review.
    def _read():
        return ProfitFlow.objects.filter(pk=1).annotate(
            _expenses=scalar(
                Expense.objects.filter(
                    is_deleted=False, expense_date__gte=first_day, expense_date__lte=last_day),
                "amount"),
            _recurring=scalar(
                RecurringExpenseAssignmentPayment.objects.filter(
                    is_deleted=False, payment_date__gte=first_day, payment_date__lte=last_day),
                "amount"),
            _gst=scalar(
                TaxPayment.objects.filter(
                    is_deleted=False, payment_date__gte=first_day, payment_date__lte=last_day),
                "amount"),
            _wht=scalar(
                WHTPayment.objects.filter(
                    is_deleted=False, payment_date__gte=first_day, payment_date__lte=last_day),
                "amount"),
            _lost_cash=scalar(
                CashAdjustment.objects.filter(
                    is_deleted=False, adjustment_type=CashAdjustment.AdjustmentType.LOST,
                    adjustment_date__gte=first_day, adjustment_date__lte=last_day),
                "amount"),
            _found_cash=scalar(
                CashAdjustment.objects.filter(
                    is_deleted=False, adjustment_type=CashAdjustment.AdjustmentType.FOUND,
                    adjustment_date__gte=first_day, adjustment_date__lte=last_day),
                "amount"),
            _lost_inv=scalar(
                LostInventoryRecord.objects.filter(
                    is_deleted=False,
                    created_at__gte=_day_start(first_day),
                    created_at__lt=_next_day_start(last_day)),
                "total_lost_amount"),
            _found_inv=scalar(
                LostInventoryRecovery.objects.filter(
                    recovered_at__gte=first_day, recovered_at__lte=last_day),
                "recovered_amount"),
            _depreciation=scalar(
                AssetValuationEntry.objects.filter(
                    entry_type=AssetValuationEntry.EntryType.DEPRECIATION, period=period),
                "amount"),
            _disposal_sold=scalar(
                AssetDisposal.objects.filter(
                    disposal_type=AssetDisposal.DisposalType.SOLD,
                    disposal_date__gte=first_day, disposal_date__lte=last_day),
                "gain_loss"),
            _disposal_scrapped=scalar(
                AssetDisposal.objects.filter(
                    disposal_type=AssetDisposal.DisposalType.SCRAPPED,
                    disposal_date__gte=first_day, disposal_date__lte=last_day),
                "worth_at_disposal"),
        ).values(
                "_expenses", "_recurring", "_gst", "_wht", "_lost_cash", "_found_cash",
                "_lost_inv", "_found_inv", "_depreciation",
                "_disposal_sold", "_disposal_scrapped",
            ).first()

    # Read first; only pay get_instance()'s extra get_or_create round-trip if
    # the singleton genuinely doesn't exist yet (once in the system's
    # lifetime). Same pattern as accounting.selectors.get_balance_sheet_live —
    # and it matters here for the same reason: without the row, `.filter(pk=1)`
    # returns nothing and EVERY figure would silently read as zero.
    row = _read()
    if row is None:
        ProfitFlow.get_instance()
        row = _read()
    row = row or {}

    zero = Decimal("0")

    def g(key):
        return row.get(key) or zero

    return {
        "expenses_paid": g("_expenses"),
        "recurring_expenses_paid": g("_recurring"),
        "gst_paid": g("_gst"),
        "wht_paid": g("_wht"),
        "lost_cash": g("_lost_cash"),
        "found_cash": g("_found_cash"),
        "lost_inventory": g("_lost_inv"),
        "found_inventory": g("_found_inv"),
        # Stored negative, same abs() the individual helper applies.
        "depreciation": abs(g("_depreciation")),
        "disposal_gain_loss": g("_disposal_sold") - g("_disposal_scrapped"),
    }


def _compute_expenses_paid(first_day, last_day) -> Decimal:
    from cash_flow.models import Expense

    total = Expense.objects.filter(
        is_deleted=False, expense_date__gte=first_day, expense_date__lte=last_day,
    ).aggregate(total=Sum("amount"))["total"]
    return total or Decimal("0")


def _compute_recurring_expenses_paid(first_day, last_day) -> Decimal:
    from recurring_expenses.models import RecurringExpenseAssignmentPayment

    total = RecurringExpenseAssignmentPayment.objects.filter(
        is_deleted=False, payment_date__gte=first_day, payment_date__lte=last_day,
    ).aggregate(total=Sum("amount"))["total"]
    return total or Decimal("0")


def _compute_gst_paid(first_day, last_day) -> Decimal:
    from taxes.models import TaxPayment

    total = TaxPayment.objects.filter(
        is_deleted=False, payment_date__gte=first_day, payment_date__lte=last_day,
    ).aggregate(total=Sum("amount"))["total"]
    return total or Decimal("0")


def _compute_wht_paid(first_day, last_day) -> Decimal:
    from taxes.models import WHTPayment

    total = WHTPayment.objects.filter(
        is_deleted=False, payment_date__gte=first_day, payment_date__lte=last_day,
    ).aggregate(total=Sum("amount"))["total"]
    return total or Decimal("0")


def _compute_lost_cash(first_day, last_day) -> Decimal:
    from cash_management.models import CashAdjustment

    total = CashAdjustment.objects.filter(
        is_deleted=False, adjustment_type=CashAdjustment.AdjustmentType.LOST,
        adjustment_date__gte=first_day, adjustment_date__lte=last_day,
    ).aggregate(total=Sum("amount"))["total"]
    return total or Decimal("0")


def _compute_found_cash(first_day, last_day) -> Decimal:
    from cash_management.models import CashAdjustment

    total = CashAdjustment.objects.filter(
        is_deleted=False, adjustment_type=CashAdjustment.AdjustmentType.FOUND,
        adjustment_date__gte=first_day, adjustment_date__lte=last_day,
    ).aggregate(total=Sum("amount"))["total"]
    return total or Decimal("0")


def _compute_lost_inventory(first_day, last_day) -> Decimal:
    """Batches (LostInventoryRecord) created this month — the loss side, dated by when it was recorded."""
    from purchases.models import LostInventoryRecord
    from purchases.selectors import _day_start, _next_day_start

    # Half-open datetime range instead of the index-defeating __date cast —
    # this runs on every current-month profit view, not just finalization.
    total = LostInventoryRecord.objects.filter(
        is_deleted=False,
        created_at__gte=_day_start(first_day),
        created_at__lt=_next_day_start(last_day),
    ).aggregate(total=Sum("total_lost_amount"))["total"]
    return total or Decimal("0")


def _compute_found_inventory(first_day, last_day) -> Decimal:
    """Recoveries (LostInventoryRecovery) dated this month, regardless of which month the original loss was recorded in."""
    from purchases.models import LostInventoryRecovery

    total = LostInventoryRecovery.objects.filter(
        recovered_at__gte=first_day, recovered_at__lte=last_day,
    ).aggregate(total=Sum("recovered_amount"))["total"]
    return total or Decimal("0")


def _compute_depreciation(period: str) -> Decimal:
    """Assumes assets.services catch-up has already run for this period — see catch_up_monthly_profits."""
    from assets.models import AssetValuationEntry

    total = AssetValuationEntry.objects.filter(
        entry_type=AssetValuationEntry.EntryType.DEPRECIATION, period=period,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    return abs(total)  # stored negative for depreciation entries


def _compute_disposal_gain_loss(first_day, last_day) -> Decimal:
    """
    Net gain/(loss) from disposing of fixed assets this month — BOTH kinds.

    This used to filter disposal_type=SOLD only. Scrapping an asset has
    gain_loss=None (there's no sale price to compare against), so a scrapped
    asset's remaining book value simply disappeared: AssetFlow.
    total_current_worth dropped by worth_at_disposal, but nothing was ever
    recorded as an expense. The loss was real — the business genuinely wrote
    off that value — it just never reached the income statement, and it left
    the Balance Sheet unable to balance by exactly that amount.

    SOLD assets keep using the stored gain_loss (sale_amount -
    worth_at_disposal, already computed at disposal time — deliberately NOT
    recomputed here, so a historical disposal keeps the figure it was
    recorded with). SCRAPPED assets are a pure loss of worth_at_disposal.

    One query, not two: a conditional aggregate over the same date-bounded
    queryset, so this costs nothing extra on the current-month path that
    recomputes it on every read.
    """
    from assets.models import AssetDisposal

    totals = AssetDisposal.objects.filter(
        disposal_date__gte=first_day, disposal_date__lte=last_day,
    ).aggregate(
        sold=Sum("gain_loss", filter=Q(disposal_type=AssetDisposal.DisposalType.SOLD)),
        scrapped=Sum(
            "worth_at_disposal",
            filter=Q(disposal_type=AssetDisposal.DisposalType.SCRAPPED),
        ),
    )
    return (totals["sold"] or Decimal("0")) - (totals["scrapped"] or Decimal("0"))


def _compute_share_status(share: MonthlyProfitInvestorShare) -> str:
    settled = share.amount_paid_out + share.amount_reinvested
    if settled <= 0:
        return MonthlyProfitInvestorShare.PaymentStatus.UNPAID
    # share_amount is stored at 4dp for exactness, but real PKR payments are
    # only ever made to the nearest paisa (2dp) — a sub-paisa residual (e.g.
    # Rs. 0.0014) can never actually be paid, so compare at 2dp to avoid a
    # genuinely fully-paid investor being stuck at PARTIAL forever.
    if settled.quantize(Decimal("0.01")) >= share.share_amount.quantize(Decimal("0.01")):
        return MonthlyProfitInvestorShare.PaymentStatus.PAID
    return MonthlyProfitInvestorShare.PaymentStatus.PARTIAL


# ---------------------------------------------------------------------------
# Internal atomic ProfitFlow adjuster — NEVER call from outside this module
# ---------------------------------------------------------------------------

def _adjust_profitflow(
    *,
    total_gross_profit_delta             : Decimal = Decimal("0"),
    total_net_gross_profit_delta         : Decimal = Decimal("0"),
    total_net_profit_delta               : Decimal = Decimal("0"),
    total_investor_profit_share_delta    : Decimal = Decimal("0"),
    total_owner_profit_share_delta       : Decimal = Decimal("0"),
    total_paid_out_to_investors_delta    : Decimal = Decimal("0"),
    total_reinvested_by_investors_delta  : Decimal = Decimal("0"),
    total_paid_out_to_owner_delta        : Decimal = Decimal("0"),
    total_reinvested_by_owner_delta      : Decimal = Decimal("0"),
    months_finalized_count_delta         : int = 0,
    user,
) -> ProfitFlow:
    with transaction.atomic():
        pf = ProfitFlow.objects.select_for_update().get_or_create(pk=1)[0]

        # Not floored — lifetime profit can legitimately go negative.
        pf.total_gross_profit           += total_gross_profit_delta
        pf.total_net_gross_profit       += total_net_gross_profit_delta
        pf.total_net_profit             += total_net_profit_delta
        pf.total_investor_profit_share  += total_investor_profit_share_delta
        pf.total_owner_profit_share     += total_owner_profit_share_delta
        pf.total_paid_out_to_investors   = max(Decimal("0"), pf.total_paid_out_to_investors + total_paid_out_to_investors_delta)
        pf.total_reinvested_by_investors = max(Decimal("0"), pf.total_reinvested_by_investors + total_reinvested_by_investors_delta)
        pf.total_paid_out_to_owner       = max(Decimal("0"), pf.total_paid_out_to_owner + total_paid_out_to_owner_delta)
        pf.total_reinvested_by_owner     = max(Decimal("0"), pf.total_reinvested_by_owner + total_reinvested_by_owner_delta)
        pf.months_finalized_count        = max(0, pf.months_finalized_count + months_finalized_count_delta)

        pf.last_updated_by = user
        pf.save()
        return pf


# ---------------------------------------------------------------------------
# Finalization — catch-up on read, no cron (mirrors assets/recurring_expenses)
# ---------------------------------------------------------------------------

@transaction.atomic
def _finalize_month(period: str, user=None) -> MonthlyProfit:
    """Idempotent — a period that already has a row is returned as-is, never recomputed."""
    existing = MonthlyProfit.objects.filter(period=period).first()
    if existing:
        return existing

    first_day, last_day = _month_bounds(period)

    from cash_flow.selectors import get_gross_profit_trend
    row = get_gross_profit_trend(date_from=first_day.isoformat(), date_to=last_day.isoformat())[0]

    expenses_paid            = _compute_expenses_paid(first_day, last_day)
    recurring_expenses_paid  = _compute_recurring_expenses_paid(first_day, last_day)
    gst_paid                  = _compute_gst_paid(first_day, last_day)
    wht_paid                  = _compute_wht_paid(first_day, last_day)
    lost_cash                 = _compute_lost_cash(first_day, last_day)
    found_cash                = _compute_found_cash(first_day, last_day)
    lost_inventory             = _compute_lost_inventory(first_day, last_day)
    found_inventory            = _compute_found_inventory(first_day, last_day)
    depreciation              = _compute_depreciation(period)
    disposal_gain_loss        = _compute_disposal_gain_loss(first_day, last_day)

    net_profit = (
        row["net_gross_profit"]
        - expenses_paid - recurring_expenses_paid - gst_paid - wht_paid
        - lost_cash + found_cash - lost_inventory + found_inventory
        - depreciation + disposal_gain_loss
    )

    try:
        # Savepoint: catch-up runs on every profits read, so two requests at a
        # month boundary can race to finalize the same period. The unique
        # constraint on period stops the loser — treat that as "already
        # finalized by the winner" instead of crashing the read with a 500.
        with transaction.atomic():
            mp = MonthlyProfit.objects.create(
                period=period,
                gross_revenue=row["revenue"], gross_cogs=row["cogs"], gross_profit=row["gross_profit"],
                net_revenue=row["net_revenue"], net_cogs=row["net_cogs"], net_gross_profit=row["net_gross_profit"],
                expenses_paid=expenses_paid, recurring_expenses_paid=recurring_expenses_paid,
                gst_paid=gst_paid, wht_paid=wht_paid,
                lost_cash=lost_cash, found_cash=found_cash,
                lost_inventory=lost_inventory, found_inventory=found_inventory,
                depreciation=depreciation, disposal_gain_loss=disposal_gain_loss,
                net_profit=net_profit,
            )
    except IntegrityError:
        return MonthlyProfit.objects.get(period=period)

    # Snapshot the ownership split AT THIS MOMENT — frozen forever on the
    # share rows, never recalculated even if current ownership % later moves.
    from profits.selectors import get_ownership_split
    split = get_ownership_split()

    investor_amounts_sum   = Decimal("0")
    total_investor_percent = Decimal("0")
    for inv in split["investors"]:
        total_investor_percent += inv["share_percent"]
        if inv["current_worth"] <= 0:
            continue  # a fully-exited investor gets no share row for this month
        share_amount = (net_profit * inv["share_percent"] / Decimal("100")).quantize(Decimal("0.0001"))
        investor_amounts_sum += share_amount
        MonthlyProfitInvestorShare.objects.create(
            monthly_profit=mp,
            investor_id=inv["id"],
            investor_name_snapshot=inv["name"],
            share_percent_snapshot=inv["share_percent"],
            share_amount=share_amount,
        )

    # Owner gets the exact remainder — guarantees investor + owner amounts
    # always sum to net_profit exactly, no rounding drift.
    owner_share_amount = net_profit - investor_amounts_sum

    mp.total_investor_share_percent = total_investor_percent
    mp.total_investor_share_amount  = investor_amounts_sum
    mp.owner_share_percent          = split["owner_share_percent"]
    mp.owner_share_amount           = owner_share_amount
    mp.save(update_fields=[
        "total_investor_share_percent", "total_investor_share_amount",
        "owner_share_percent", "owner_share_amount",
    ])

    MonthlyProfitOwnerShare.objects.create(monthly_profit=mp, share_amount=owner_share_amount)

    _adjust_profitflow(
        total_gross_profit_delta=row["gross_profit"],
        total_net_gross_profit_delta=row["net_gross_profit"],
        total_net_profit_delta=net_profit,
        total_investor_profit_share_delta=investor_amounts_sum,
        total_owner_profit_share_delta=owner_share_amount,
        months_finalized_count_delta=1,
        user=user,
    )

    return mp


def catch_up_monthly_profits(user=None) -> None:
    """
    Creates any missing FINISHED month rows, from the month after the latest
    existing one (or the earliest confirmed invoice's month, if none exist
    yet) up to — but never including — the current, still-open month. Called
    from every profits.selectors read path, same as assets/recurring_expenses
    catch-up. A no-op most of the time (single query, zero iterations).
    """
    today = timezone.localdate()
    current_period = f"{today.year:04d}-{today.month:02d}"

    # Self-healing backfill: any MonthlyProfit row that predates
    # MonthlyProfitOwnerShare (introduced after this app already had data)
    # gets one created from its own already-stored owner_share_amount — no
    # recomputation, no drift, same "catch-up on read, no cron" idiom as
    # everything else here.
    for mp in MonthlyProfit.objects.filter(owner_share__isnull=True):
        MonthlyProfitOwnerShare.objects.create(monthly_profit=mp, share_amount=mp.owner_share_amount)

    last_row = MonthlyProfit.objects.order_by("-period").first()
    if last_row:
        y, m = (int(p) for p in last_row.period.split("-"))
        next_y, next_m = _add_months(y, m, 1)
    else:
        earliest = _earliest_period()
        if not earliest:
            return  # no confirmed invoices at all yet — nothing to report
        next_y, next_m = (int(p) for p in earliest.split("-"))

    next_period = f"{next_y:04d}-{next_m:02d}"
    if next_period >= current_period:
        return  # already caught up

    # Depreciation is posted by assets' own catch-up, which only runs when
    # something reads the assets app — make sure it's current before we
    # read AssetValuationEntry rows below for every period we're about to finalize.
    from assets.selectors import get_asset_stats
    get_asset_stats()

    while next_period < current_period:
        _finalize_month(next_period, user=user)
        next_y, next_m = _add_months(next_y, next_m, 1)
        next_period = f"{next_y:04d}-{next_m:02d}"


# ---------------------------------------------------------------------------
# InvestorProfitPayout services
# ---------------------------------------------------------------------------

@transaction.atomic
def create_investor_profit_payout(
    *, share_id: int, amount: Decimal, action_type: str, payout_date,
    method_allocations: list = None, note: str = "", user,
) -> InvestorProfitPayout:
    from django.shortcuts import get_object_or_404
    from rest_framework.exceptions import ValidationError

    if amount <= 0:
        raise ValidationError({"amount": "Amount must be greater than zero."})
    if action_type not in (InvestorProfitPayout.ActionType.PAYOUT, InvestorProfitPayout.ActionType.REINVEST):
        raise ValidationError({"action_type": "Must be 'payout' or 'reinvest'."})
    if action_type == InvestorProfitPayout.ActionType.PAYOUT and not method_allocations:
        raise ValidationError({"method_allocations": "At least one method must be selected for a payout."})

    share = get_object_or_404(
        MonthlyProfitInvestorShare.objects.select_for_update().select_related("investor", "monthly_profit"),
        pk=share_id,
    )

    remaining = share.amount_remaining
    if amount > remaining:
        raise ValidationError({
            "amount": f"Amount exceeds this investor's remaining share balance. Remaining: {remaining}."
        })

    payout = InvestorProfitPayout.objects.create(
        share=share, amount=amount, payout_date=payout_date, action_type=action_type,
        note=note, created_by=user, updated_by=user,
    )

    # Always: real cash leaves for this share, regardless of what happens next.
    from cash_flow.services import record_cash_movement, sync_investor_profit_payout_made
    sync_investor_profit_payout_made(amount=amount, user=user)
    record_cash_movement(payout)

    from payment_methods.services import record_allocations

    if action_type == InvestorProfitPayout.ActionType.PAYOUT:
        record_allocations(
            payout, direction="outflow", splits=method_allocations,
            total_amount=amount, date=payout_date, user=user,
        )
        share.amount_paid_out += amount
        _adjust_profitflow(total_paid_out_to_investors_delta=+amount, user=user)
    else:
        # Reinvest — no real money crosses accounts (it's a bookkeeping
        # swap of equity), so the user is never asked for a method here;
        # both legs default silently to the protected Cash account.
        from payment_methods.models import PaymentMethod
        cash, _ = PaymentMethod.objects.get_or_create(name="Cash", defaults={"is_protected": True})
        record_allocations(
            payout, direction="outflow", splits=[(cash, amount)],
            total_amount=amount, date=payout_date, user=user,
        )
        # Reinvest: the same amount immediately comes back in as a genuine
        # new investment — real capital growth, not a payout-in-disguise.
        # method_allocations passed explicitly (Cash, same as the outflow
        # leg above) since create_investor_transaction requires one now —
        # this is the resolution of the cross-phase dependency Phase 4
        # flagged: without this, reinvest would suddenly demand a user
        # method pick, which is exactly the behavior Phase 4 turned off.
        from cash_management.models import InvestorTransaction
        from cash_management.services import create_investor_transaction

        txn = create_investor_transaction(
            investor_id=share.investor_id,
            transaction_type=InvestorTransaction.TransactionType.INVESTMENT,
            amount=amount,
            transaction_date=payout_date,
            method_allocations=[(cash, amount)],
            note=f"Reinvested profit share — {share.monthly_profit.period} (payout #{payout.id})",
            user=user,
        )
        payout.linked_investor_transaction = txn
        payout.save(update_fields=["linked_investor_transaction"])

        share.amount_reinvested += amount
        _adjust_profitflow(total_reinvested_by_investors_delta=+amount, user=user)

    share.payment_status = _compute_share_status(share)
    share.save(update_fields=["amount_paid_out", "amount_reinvested", "payment_status"])

    return payout


@transaction.atomic
def delete_investor_profit_payout(*, pk: int, user) -> None:
    from django.shortcuts import get_object_or_404

    payout = get_object_or_404(InvestorProfitPayout, pk=pk, is_deleted=False)
    share  = MonthlyProfitInvestorShare.objects.select_for_update().get(pk=payout.share_id)
    amount = payout.amount

    payout.is_deleted = True
    payout.deleted_at = timezone.now()
    payout.deleted_by = user
    payout.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])

    # Reverse the outflow every payout action performed, regardless of type.
    from cash_flow.services import reverse_cash_movement, sync_investor_profit_payout_reversed
    sync_investor_profit_payout_reversed(amount=amount, user=user)
    reverse_cash_movement(payout)

    from payment_methods.services import reverse_allocations
    reverse_allocations(payout)

    if payout.action_type == InvestorProfitPayout.ActionType.PAYOUT:
        share.amount_paid_out = max(Decimal("0"), share.amount_paid_out - amount)
        _adjust_profitflow(total_paid_out_to_investors_delta=-amount, user=user)
    else:
        if payout.linked_investor_transaction_id:
            from cash_management.services import delete_investor_transaction
            delete_investor_transaction(pk=payout.linked_investor_transaction_id, user=user)
        share.amount_reinvested = max(Decimal("0"), share.amount_reinvested - amount)
        _adjust_profitflow(total_reinvested_by_investors_delta=-amount, user=user)

    share.payment_status = _compute_share_status(share)
    share.save(update_fields=["amount_paid_out", "amount_reinvested", "payment_status"])


# ---------------------------------------------------------------------------
# OwnerProfitPayout services — exact mirror of InvestorProfitPayout services
# ---------------------------------------------------------------------------

@transaction.atomic
def create_owner_profit_payout(
    *, owner_share_id: int, amount: Decimal, action_type: str, payout_date,
    method_allocations: list = None, note: str = "", user,
) -> OwnerProfitPayout:
    from django.shortcuts import get_object_or_404
    from rest_framework.exceptions import ValidationError

    if amount <= 0:
        raise ValidationError({"amount": "Amount must be greater than zero."})
    if action_type not in (OwnerProfitPayout.ActionType.PAYOUT, OwnerProfitPayout.ActionType.REINVEST):
        raise ValidationError({"action_type": "Must be 'payout' or 'reinvest'."})
    if action_type == OwnerProfitPayout.ActionType.PAYOUT and not method_allocations:
        raise ValidationError({"method_allocations": "At least one method must be selected for a payout."})

    owner_share = get_object_or_404(
        MonthlyProfitOwnerShare.objects.select_for_update().select_related("monthly_profit"),
        pk=owner_share_id,
    )

    remaining = owner_share.amount_remaining
    if amount > remaining:
        raise ValidationError({
            "amount": f"Amount exceeds the owner's remaining share balance. Remaining: {remaining}."
        })

    payout = OwnerProfitPayout.objects.create(
        owner_share=owner_share, amount=amount, payout_date=payout_date, action_type=action_type,
        note=note, created_by=user, updated_by=user,
    )

    # Always: real cash leaves for this share, regardless of what happens next.
    from cash_flow.services import record_cash_movement, sync_owner_profit_payout_made
    sync_owner_profit_payout_made(amount=amount, user=user)
    record_cash_movement(payout)

    from payment_methods.services import record_allocations

    if action_type == OwnerProfitPayout.ActionType.PAYOUT:
        record_allocations(
            payout, direction="outflow", splits=method_allocations,
            total_amount=amount, date=payout_date, user=user,
        )
        owner_share.amount_paid_out += amount
        _adjust_profitflow(total_paid_out_to_owner_delta=+amount, user=user)
    else:
        # Reinvest — no real money crosses accounts (it's a bookkeeping
        # swap of equity), so the user is never asked for a method here;
        # both legs default silently to the protected Cash account.
        from payment_methods.models import PaymentMethod
        cash, _ = PaymentMethod.objects.get_or_create(name="Cash", defaults={"is_protected": True})
        record_allocations(
            payout, direction="outflow", splits=[(cash, amount)],
            total_amount=amount, date=payout_date, user=user,
        )
        # Reinvest: the same amount immediately comes back in as a genuine
        # owner contribution — real capital, not a payout-in-disguise.
        # method_allocations passed explicitly (Cash, same as the outflow
        # leg above) since create_owner_transaction requires one now — the
        # resolution of the cross-phase dependency Phase 4 flagged.
        from cash_management.models import OwnerTransaction
        from cash_management.services import create_owner_transaction

        txn = create_owner_transaction(
            transaction_type=OwnerTransaction.TransactionType.CONTRIBUTION,
            amount=amount,
            transaction_date=payout_date,
            method_allocations=[(cash, amount)],
            note=f"Reinvested profit share — {owner_share.monthly_profit.period} (payout #{payout.id})",
            user=user,
        )
        payout.linked_owner_transaction = txn
        payout.save(update_fields=["linked_owner_transaction"])

        owner_share.amount_reinvested += amount
        _adjust_profitflow(total_reinvested_by_owner_delta=+amount, user=user)

    owner_share.payment_status = _compute_share_status(owner_share)
    owner_share.save(update_fields=["amount_paid_out", "amount_reinvested", "payment_status"])

    return payout


@transaction.atomic
def delete_owner_profit_payout(*, pk: int, user) -> None:
    from django.shortcuts import get_object_or_404

    payout      = get_object_or_404(OwnerProfitPayout, pk=pk, is_deleted=False)
    owner_share = MonthlyProfitOwnerShare.objects.select_for_update().get(pk=payout.owner_share_id)
    amount      = payout.amount

    payout.is_deleted = True
    payout.deleted_at = timezone.now()
    payout.deleted_by = user
    payout.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])

    # Reverse the outflow every payout action performed, regardless of type.
    from cash_flow.services import reverse_cash_movement, sync_owner_profit_payout_reversed
    sync_owner_profit_payout_reversed(amount=amount, user=user)
    reverse_cash_movement(payout)

    from payment_methods.services import reverse_allocations
    reverse_allocations(payout)

    if payout.action_type == OwnerProfitPayout.ActionType.PAYOUT:
        owner_share.amount_paid_out = max(Decimal("0"), owner_share.amount_paid_out - amount)
        _adjust_profitflow(total_paid_out_to_owner_delta=-amount, user=user)
    else:
        if payout.linked_owner_transaction_id:
            from cash_management.services import delete_owner_transaction
            delete_owner_transaction(pk=payout.linked_owner_transaction_id, user=user)
        owner_share.amount_reinvested = max(Decimal("0"), owner_share.amount_reinvested - amount)
        _adjust_profitflow(total_reinvested_by_owner_delta=-amount, user=user)

    owner_share.payment_status = _compute_share_status(owner_share)
    owner_share.save(update_fields=["amount_paid_out", "amount_reinvested", "payment_status"])
