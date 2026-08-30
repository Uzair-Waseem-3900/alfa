from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView


class PingView(APIView):
    """
    GET /api/ping/

    No-op keep-alive endpoint. The frontend calls this periodically while
    it's open so the Render free-plan backend doesn't spin down from
    inactivity. No auth required — this must work regardless of login state.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(status=200)


class IsAdminOrSuperuser(BasePermission):
    """Same rule as every app's own permissions.py — kept local here since
    this view is project-level (backend/backend/), not owned by one app."""
    message = "Only admins or superusers can perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_staff
        )


class TriggerAllCatchUpsView(APIView):
    """
    GET /api/system/catch-up/

    Triggers every "catch-up on read" calculation in the project in one
    call, so their freshness never depends on which specific dashboard
    pages/hooks happen to be wired up. Returns only a small confirmation
    object — no dashboard data lives here on purpose.

    There are exactly six such mechanisms in the whole codebase (verified
    by two independent sweeps across every app — nothing else uses this
    pattern; every other Flow singleton is kept current at write time,
    event-driven, and needs no trigger):

        1. assets      — depreciation catch-up, one entry per active asset
        2. cash_management — investor growth catch-up, one entry per investor
        3. profits     — monthly profit finalization catch-up (global)
        4. accounting  — balance sheet snapshot catch-up, one entry for the
                          single most-recently-finished month only (see
                          accounting.services.catch_up_balance_sheet_snapshots
                          for why it can't backfill further back than that)
        5. credit_score — overdue-invoice credit score catch-up, one entry
                          per customer with a newly-overdue invoice
        6. users       — expired JWT token flush (throttled to once/24h)

    Order matters: assets and investors run first because profits reads
    both of their outputs (asset depreciation for the deduction breakdown,
    investor current_worth for the ownership split) when finalizing a month.
    accounting's balance sheet catch-up runs right after profits because it
    reads the SAME live singletons profits' own finalization just settled
    (asset/investor catch-ups already ran, so those figures are current too).
    credit_score depends only on billing data (always live-updated, no
    ordering dependency on the other catch-ups) so it can run anywhere
    after profits; the token flush is independent of everything and runs last.

    Each phase is isolated in its own try/except — one app's failure never
    blocks the other two (same defensive-import discipline already used for
    cross-app reads elsewhere in this project, e.g. cash_flow's breakdown
    functions).
    """
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        assets_processed, assets_error = self._run_asset_catchup()
        investors_processed, investors_error = self._run_investor_catchup()
        months_finalized, profits_error = self._run_profits_catchup(user=request.user)
        balance_sheet_snapshots_created, balance_sheet_error = self._run_balance_sheet_catchup()
        credit_scores_recalculated, credit_score_error = self._run_credit_score_catchup(user=request.user)
        tokens_flushed, tokens_error = self._run_token_flush()

        return Response({
            "assets_processed": assets_processed,
            "assets_error": assets_error,
            "investors_processed": investors_processed,
            "investors_error": investors_error,
            "months_finalized": months_finalized,
            "profits_error": profits_error,
            "balance_sheet_snapshots_created": balance_sheet_snapshots_created,
            "balance_sheet_error": balance_sheet_error,
            "credit_scores_recalculated": credit_scores_recalculated,
            "credit_score_error": credit_score_error,
            "tokens_flushed": tokens_flushed,
            "tokens_error": tokens_error,
        })

    def _run_asset_catchup(self):
        """Reuses assets.selectors.get_asset_stats(), which already loops
        every active, non-disposed asset and catches up its depreciation —
        same call every Assets page read already makes."""
        try:
            from assets.models import Asset
            from assets.selectors import get_asset_stats

            get_asset_stats()
            count = Asset.objects.filter(is_deleted=False, is_disposed=False).count()
            return count, None
        except Exception as exc:
            return 0, str(exc)

    def _run_investor_catchup(self):
        """Reuses cash_management.selectors.get_cash_management_stats(),
        which already loops every non-deleted investor and catches up their
        growth — same call every Cash Management page read already makes."""
        try:
            from cash_management.models import Investor
            from cash_management.selectors import get_cash_management_stats

            get_cash_management_stats()
            count = Investor.objects.filter(is_deleted=False).count()
            return count, None
        except Exception as exc:
            return 0, str(exc)

    def _run_profits_catchup(self, *, user):
        """Depends on assets/investors already being current."""
        try:
            from profits.models import ProfitFlow
            from profits.services import catch_up_monthly_profits

            before = ProfitFlow.get_instance().months_finalized_count
            catch_up_monthly_profits(user=user)
            after = ProfitFlow.get_instance().months_finalized_count
            return after - before, None
        except Exception as exc:
            return 0, str(exc)

    def _run_balance_sheet_catchup(self):
        """Depends on assets/investors/profits already being current — see
        accounting.services.catch_up_balance_sheet_snapshots for why this
        only ever freezes the single most-recently-finished month, never a
        backlog of older ones."""
        try:
            from accounting.services import catch_up_balance_sheet_snapshots

            return catch_up_balance_sheet_snapshots(), None
        except Exception as exc:
            return 0, str(exc)

    def _run_credit_score_catchup(self, *, user):
        """Reuses credit_score.services.run_overdue_catchup(), which is
        itself marker-gated (O(1) unless the day has rolled over) and, even
        when it does run, bounded to invoices that are actually overdue —
        never a scan of every customer."""
        try:
            from credit_score.services import run_overdue_catchup

            return run_overdue_catchup(user=user), None
        except Exception as exc:
            return 0, str(exc)

    def _run_token_flush(self):
        """Prunes expired SimpleJWT outstanding/blacklisted token rows —
        the only tables in the project that would otherwise grow forever
        (every login and refresh inserts rows and nothing else deletes
        them). Throttled inside the service to once per 24h."""
        try:
            from users.services import flush_expired_tokens

            return flush_expired_tokens(), None
        except Exception as exc:
            return 0, str(exc)
