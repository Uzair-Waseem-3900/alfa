from django.db import models

# Phase 1 (A/R aging, A/P aging, Fixed Asset Register) is entirely read-only —
# every figure is derived live, bounded to rows with a nonzero outstanding
# balance or active status (same "live snapshot report" exception
# architecture.md carves out for Inventory Valuation), so it needed no
# models. Income Statement and Cash Flow Statement (phase 2) are the same —
# pure selectors over profits.MonthlyProfit / cash_flow.CashMovement.
# Balance Sheet is the one exception: every one of its figures is an
# ALL-TIME singleton (CashFlow/AssetFlow/TaxFlow/CashManagementFlow/
# ProfitFlow), so there is no way to answer "what did it look like last
# month" without freezing a snapshot at the time — hence this one model.


class BalanceSheetSnapshot(models.Model):
    """
    One row per FINISHED month, created once by
    accounting.services.catch_up_balance_sheet_snapshots (catch-up on read,
    registered in GET /api/system/catch-up/ right after profits' own
    catch-up) and never recomputed afterward — exact same pattern as
    profits.MonthlyProfit. The current, still-open month has no row here;
    accounting.selectors.get_balance_sheet_live() computes it live instead.

    total_assets/total_liabilities/total_equity are stored (not recomputed
    on read) so the balance-check comparison never drifts from what was
    actually true at snapshot time, even if a later bug changes how the
    live totals would be computed today.
    """

    period = models.CharField(max_length=7, unique=True, db_index=True, help_text="YYYY-MM")

    # ---- Assets ----
    cash_in_hand          = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    accounts_receivable   = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    inventory_value       = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    fixed_assets_nbv       = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    total_assets           = models.DecimalField(max_digits=20, decimal_places=4, default=0)

    # ---- Liabilities ----
    accounts_payable       = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    gst_payable             = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    wht_payable             = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    total_liabilities       = models.DecimalField(max_digits=20, decimal_places=4, default=0)

    # ---- Equity ----
    owner_capital           = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    investor_capital         = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    opening_balance_equity    = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                    help_text="Net offset for go-live bootstrap data (data_entry app): "
                                               "+customer opening balances, +opening stock, -supplier opening "
                                               "balances. Each of those creates an asset or liability with no "
                                               "natural double-entry counterpart, so without this line the "
                                               "balance sheet would never balance for a business that used the "
                                               "Data Entry app to bootstrap pre-existing debts/stock at go-live.")
    pre_owned_asset_equity    = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                    help_text="Total cost of assets registered with acquisition_type='existing' "
                                               "(already owned before being recorded, so no cash ever left the "
                                               "business). Like opening stock, these add an asset with no natural "
                                               "counterpart — without this line the sheet cannot balance for any "
                                               "business that registered a pre-owned asset. Includes disposed ones: "
                                               "removing them would strand the depreciation already expensed "
                                               "through retained earnings.")
    asset_revaluation_surplus  = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                    help_text="Net of all AssetValuationEntry REVALUATION amounts (signed, so "
                                               "downward revaluations reduce it). Only DEPRECIATION entries feed "
                                               "net profit, so a revaluation moves current_worth with nothing on "
                                               "the other side — this is the standard revaluation-surplus offset.")
    retained_earnings        = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                    help_text="Cumulative net profit minus everything already paid out or reinvested.")
    total_equity              = models.DecimalField(max_digits=20, decimal_places=4, default=0)

    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Balance Sheet Snapshot"
        verbose_name_plural  = "Balance Sheet Snapshots"
        ordering             = ["-period"]

    def __str__(self):
        return f"{self.period} — assets {self.total_assets}"
