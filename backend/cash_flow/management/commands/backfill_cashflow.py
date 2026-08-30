from decimal import Decimal

from django.core.management.base import BaseCommand

from cash_flow.models import CashFlow


class Command(BaseCommand):
    help = "Backfills the CashFlow singleton from existing invoices, purchases, and expenses."

    def handle(self, *args, **kwargs):
        from billing.models import Invoice, Payment, Return
        from purchases.models import LostInventoryItem, PurchaseOrder, PurchaseReturn, SupplierPayment
        from cash_flow.models import Expense

        self.stdout.write("Starting CashFlow backfill...\n")

        # Reset singleton — EVERY field this command touches must be reset here.
        # A backfill command must be idempotent (safe to re-run, always lands
        # on the correct absolute value); any field summed further down but
        # left out of this reset silently compounds on every re-run instead.
        cf, _ = CashFlow.objects.get_or_create(pk=1)
        cf.cash_in_hand               = Decimal("0")
        cf.total_cash_inflow          = Decimal("0")
        cf.total_cash_outflow         = Decimal("0")
        cf.customer_outstanding       = Decimal("0")
        cf.total_invoices_cash        = Decimal("0")
        cf.total_paid_payables        = Decimal("0")
        cf.supplier_payable_outstanding = Decimal("0")
        cf.total_purchases_cash       = Decimal("0")
        cf.total_expenses_amount      = Decimal("0")
        cf.total_recurring_expenses_paid = Decimal("0")
        cf.total_lost_inventory_worth = Decimal("0")
        cf.total_lost_inventory_recovered = Decimal("0")
        cf.total_purchase_returns_value = Decimal("0")
        cf.total_purchase_returns_cogs  = Decimal("0")
        cf.total_customer_returns_value = Decimal("0")
        cf.total_customer_returns_cogs  = Decimal("0")
        cf.total_invoice_revenue      = Decimal("0")
        cf.total_invoice_cogs         = Decimal("0")
        cf.total_gross_profit         = Decimal("0")
        cf.total_invoices_count       = 0
        cf.total_purchases_count      = 0
        cf.total_expenses_count       = 0
        cf.save()

        # 1. Customer outstanding = sum of credit_outstanding on confirmed invoices
        invoices = Invoice.objects.filter(
            is_deleted=False,
        ).exclude(status="draft")

        for inv in invoices:
            cf.customer_outstanding += inv.credit_outstanding or Decimal("0")
        self.stdout.write(f"  customer_outstanding: {cf.customer_outstanding}")

        # 1b. Opening cash (data-entry bootstrap) — seeds starting cash on hand.
        #     Not an invoice, so it must NOT touch total_invoices_cash.
        try:
            from data_entry.models import OpeningCashEntry
            for oc in OpeningCashEntry.objects.all():
                cf.cash_in_hand += oc.amount or Decimal("0")
        except Exception:
            pass  # data_entry is a removable bootstrap app — fine if absent post-go-live

        # 2. Cash in hand + total_invoices_cash = sum of all positive invoice payments received
        payments = Payment.objects.filter(
            is_deleted=False,
            amount__gt=0,
            invoice__is_deleted=False,
        ).exclude(invoice__status="draft")

        for p in payments:
            cf.cash_in_hand       += p.amount
            cf.total_invoices_cash += p.amount
        self.stdout.write(f"  cash_in_hand (before expenses/advances): {cf.cash_in_hand}")
        self.stdout.write(f"  total_invoices_cash: {cf.total_invoices_cash}")

        # 2b. Advance payments on invoices still draft — already added to
        #     cash_in_hand at draft creation but excluded from the loop
        #     above (which only covers confirmed invoices). Not counted
        #     toward total_invoices_cash until the invoice is confirmed
        #     (mirrors sync_invoice_advance_payment_created/sync_invoice_confirmed).
        draft_advance_payments = Payment.objects.filter(
            is_deleted=False,
            amount__gt=0,
            note__startswith="Advance payment",
            invoice__is_deleted=False,
            invoice__status="draft",
        )
        for ap in draft_advance_payments:
            cf.cash_in_hand += ap.amount
        self.stdout.write(f"  cash_in_hand (draft invoice advances added): {cf.cash_in_hand}")

        # 3. Supplier payable outstanding = sum of payable_outstanding on confirmed orders
        #    (includes data-entry opening-balance orders — those DO count as real
        #    outstanding debt, per sync_data_entry_supplier_opening_balance).
        orders = PurchaseOrder.objects.filter(
            is_deleted=False,
            status="confirmed",
        )
        for order in orders:
            cf.supplier_payable_outstanding += order.payable_outstanding or Decimal("0")
        self.stdout.write(f"  supplier_payable_outstanding: {cf.supplier_payable_outstanding}")

        # 3b. total_purchases_cash = sum of net_payable on confirmed orders, EXCLUDING
        #     data-entry orders (opening balance/opening stock) — these are carried-
        #     forward payables, not operating-period purchases. sync_data_entry_
        #     supplier_opening_balance deliberately leaves total_purchases_cash
        #     untouched on the live path, and the purchases breakdown selector
        #     applies the same is_data_entry=False exclusion — this must match both.
        for order in orders.filter(is_data_entry=False):
            cf.total_purchases_cash += order.net_payable or Decimal("0")
        self.stdout.write(f"  total_purchases_cash: {cf.total_purchases_cash}")

        # 4. Total paid payables = sum of positive supplier payments on confirmed orders.
        #    These also reduce cash_in_hand (mirrors sync_supplier_payment_made) —
        #    the previous version of this command missed this subtraction entirely,
        #    overstating cash_in_hand by the full total_paid_payables amount.
        sp = SupplierPayment.objects.filter(
            is_deleted=False,
            amount__gt=0,
            order__is_deleted=False,
            order__status="confirmed",
        )
        for p in sp:
            cf.total_paid_payables += p.amount
            cf.cash_in_hand        -= p.amount
        cf.cash_in_hand = max(Decimal("0"), cf.cash_in_hand)
        self.stdout.write(f"  total_paid_payables: {cf.total_paid_payables}")

        # 5. Expenses
        expenses = Expense.objects.filter(is_deleted=False)
        for exp in expenses:
            cf.total_expenses_amount += exp.amount
            cf.cash_in_hand          -= exp.amount  # expenses reduce cash
        cf.cash_in_hand = max(Decimal("0"), cf.cash_in_hand)
        self.stdout.write(f"  total_expenses_amount: {cf.total_expenses_amount}")

        # 5b. Tax payments (GST paid to FBR) — same treatment as expenses:
        #     real cash leaving the till. Mirrors taxes.services.sync_tax_payment_made.
        try:
            from taxes.models import TaxPayment
            tax_payments = TaxPayment.objects.filter(is_deleted=False)
            total_tax_paid = Decimal("0")
            for tp in tax_payments:
                total_tax_paid  += tp.amount
                cf.cash_in_hand -= tp.amount
            cf.cash_in_hand = max(Decimal("0"), cf.cash_in_hand)
            self.stdout.write(f"  total_tax_paid (deducted from cash_in_hand): {total_tax_paid}")
        except Exception:
            pass  # taxes app absent — fine, nothing to deduct

        # 5b2. WHT payments (withholding tax deposited to FBR) — same treatment
        #      as tax payments: real cash leaving the till. Mirrors
        #      taxes.services.sync_wht_payment_made.
        try:
            from taxes.models import WHTPayment
            wht_payments = WHTPayment.objects.filter(is_deleted=False)
            total_wht_paid = Decimal("0")
            for wp in wht_payments:
                total_wht_paid  += wp.amount
                cf.cash_in_hand -= wp.amount
            cf.cash_in_hand = max(Decimal("0"), cf.cash_in_hand)
            self.stdout.write(f"  total_wht_paid (deducted from cash_in_hand): {total_wht_paid}")
        except Exception:
            pass  # taxes app absent — fine, nothing to deduct

        # 5b3. Investor profit payouts (payout or reinvest — BOTH move cash out
        #      the same way; a reinvest's offsetting inflow is already counted
        #      separately via the investor-transactions loop below). Mirrors
        #      profits.services.sync_investor_profit_payout_made.
        try:
            from profits.models import InvestorProfitPayout
            payouts = InvestorProfitPayout.objects.filter(is_deleted=False)
            total_profit_payouts = Decimal("0")
            for pp in payouts:
                total_profit_payouts += pp.amount
                cf.cash_in_hand      -= pp.amount
            cf.cash_in_hand = max(Decimal("0"), cf.cash_in_hand)
            self.stdout.write(f"  total_investor_profit_payouts (deducted from cash_in_hand): {total_profit_payouts}")
        except Exception:
            pass  # profits app absent — fine, nothing to deduct

        # 5b4. Owner profit payouts (payout or reinvest — BOTH move cash out
        #      the same way; a reinvest's offsetting inflow is already counted
        #      separately via the owner-transactions loop below). Mirrors
        #      profits.services.sync_owner_profit_payout_made.
        try:
            from profits.models import OwnerProfitPayout
            owner_payouts = OwnerProfitPayout.objects.filter(is_deleted=False)
            total_owner_profit_payouts = Decimal("0")
            for op in owner_payouts:
                total_owner_profit_payouts += op.amount
                cf.cash_in_hand            -= op.amount
            cf.cash_in_hand = max(Decimal("0"), cf.cash_in_hand)
            self.stdout.write(f"  total_owner_profit_payouts (deducted from cash_in_hand): {total_owner_profit_payouts}")
        except Exception:
            pass  # profits app absent — fine, nothing to deduct

        # 5c. Lost/found cash + investor investments/withdrawals — mirrors
        #     cash_flow.services.sync_cash_lost/sync_cash_found/
        #     sync_investor_investment/sync_investor_withdrawal exactly.
        try:
            from cash_management.models import CashAdjustment, InvestorTransaction, OwnerTransaction

            total_lost = Decimal("0")
            total_found = Decimal("0")
            for a in CashAdjustment.objects.filter(is_deleted=False):
                if a.adjustment_type == CashAdjustment.AdjustmentType.LOST:
                    total_lost      += a.amount
                    cf.cash_in_hand -= a.amount
                else:
                    total_found     += a.amount
                    cf.cash_in_hand += a.amount
            cf.cash_in_hand = max(Decimal("0"), cf.cash_in_hand)
            self.stdout.write(f"  total_cash_lost (deducted): {total_lost}, total_cash_found (added): {total_found}")

            total_invested = Decimal("0")
            total_withdrawn = Decimal("0")
            for t in InvestorTransaction.objects.filter(is_deleted=False):
                if t.transaction_type == InvestorTransaction.TransactionType.INVESTMENT:
                    total_invested   += t.amount
                    cf.cash_in_hand  += t.amount
                else:
                    total_withdrawn  += t.amount
                    cf.cash_in_hand  -= t.amount
            cf.cash_in_hand = max(Decimal("0"), cf.cash_in_hand)
            self.stdout.write(f"  total_investor_capital (added): {total_invested}, total_investor_withdrawn (deducted): {total_withdrawn}")

            total_owner_contributions = Decimal("0")
            total_owner_drawings = Decimal("0")
            for t in OwnerTransaction.objects.filter(is_deleted=False):
                if t.transaction_type == OwnerTransaction.TransactionType.CONTRIBUTION:
                    total_owner_contributions += t.amount
                    cf.cash_in_hand           += t.amount
                else:
                    total_owner_drawings      += t.amount
                    cf.cash_in_hand           -= t.amount
            cf.cash_in_hand = max(Decimal("0"), cf.cash_in_hand)
            self.stdout.write(f"  total_owner_contributions (added): {total_owner_contributions}, total_owner_drawings (deducted): {total_owner_drawings}")
        except Exception:
            pass  # cash_management app absent — fine, nothing to adjust

        # 5d. Fixed asset purchases (outflow) + sold disposals (inflow) —
        #     mirrors cash_flow.services.sync_asset_purchased/sync_asset_sold.
        try:
            from assets.models import Asset, AssetDisposal

            total_asset_purchases = Decimal("0")
            for a in Asset.objects.filter(is_deleted=False, acquisition_type=Asset.AcquisitionType.NEW):
                total_asset_purchases += a.cost
                cf.cash_in_hand       -= a.cost
            cf.cash_in_hand = max(Decimal("0"), cf.cash_in_hand)
            self.stdout.write(f"  total_asset_purchases (deducted): {total_asset_purchases}")

            total_asset_sales = Decimal("0")
            for d in AssetDisposal.objects.filter(disposal_type=AssetDisposal.DisposalType.SOLD):
                total_asset_sales += d.sale_amount or Decimal("0")
                cf.cash_in_hand   += d.sale_amount or Decimal("0")
            cf.cash_in_hand = max(Decimal("0"), cf.cash_in_hand)
            self.stdout.write(f"  total_asset_sales (added): {total_asset_sales}")
        except Exception:
            pass  # assets app absent — fine, nothing to adjust

        # 5e. Recurring expense payments (salaries, rent, ...) — mirrors
        #     cash_flow.services.sync_recurring_expense_payment_made. Only
        #     PAYMENTS touch cash_in_hand — assignments (dues) never do.
        try:
            from recurring_expenses.models import RecurringExpenseAssignmentPayment

            total_recurring_paid = Decimal("0")
            for p in RecurringExpenseAssignmentPayment.objects.filter(is_deleted=False):
                total_recurring_paid += p.amount
                cf.cash_in_hand      -= p.amount
            cf.cash_in_hand = max(Decimal("0"), cf.cash_in_hand)
            cf.total_recurring_expenses_paid = total_recurring_paid
            self.stdout.write(f"  total_recurring_expenses_paid (deducted): {total_recurring_paid}")
        except Exception:
            pass  # recurring_expenses app absent — fine, nothing to adjust

        # 6. Advance payments already deducted from cash_in_hand
        advance_payments = SupplierPayment.objects.filter(
            is_deleted=False,
            amount__gt=0,
            note__startswith="Advance payment",
            order__is_deleted=False,
            order__status="draft",  # only draft advances not yet confirmed
        )
        for ap in advance_payments:
            cf.cash_in_hand -= ap.amount
        cf.cash_in_hand = max(Decimal("0"), cf.cash_in_hand)
        self.stdout.write(f"  cash_in_hand (final): {cf.cash_in_hand}")

        # 7. Lost inventory worth = sum of total_cost on all lost inventory items
        lost_items = LostInventoryItem.objects.filter(record__is_deleted=False)
        for li in lost_items:
            cf.total_lost_inventory_worth += li.total_cost or Decimal("0")
            cf.total_lost_inventory_recovered += li.recovered_amount or Decimal("0")
        self.stdout.write(f"  total_lost_inventory_worth: {cf.total_lost_inventory_worth}")
        self.stdout.write(f"  total_lost_inventory_recovered: {cf.total_lost_inventory_recovered}")

        # 8. Purchase returns value/cogs = sum of total_return_amount/total_return_gross on accepted purchase returns
        purchase_returns = PurchaseReturn.objects.filter(is_deleted=False, status="accepted")
        for pr in purchase_returns:
            cf.total_purchase_returns_value += pr.total_return_amount or Decimal("0")
            cf.total_purchase_returns_cogs  += pr.total_return_gross or Decimal("0")
        self.stdout.write(f"  total_purchase_returns_value: {cf.total_purchase_returns_value}")
        self.stdout.write(f"  total_purchase_returns_cogs: {cf.total_purchase_returns_cogs}")

        # 9. Customer returns value/cogs = sum on accepted billing returns
        customer_returns = Return.objects.filter(is_deleted=False, status="accepted")
        for cr in customer_returns:
            cf.total_customer_returns_value += cr.total_return_amount or Decimal("0")
            cf.total_customer_returns_cogs  += cr.total_return_cogs or Decimal("0")
        self.stdout.write(f"  total_customer_returns_value: {cf.total_customer_returns_value}")
        self.stdout.write(f"  total_customer_returns_cogs: {cf.total_customer_returns_cogs}")

        # 10. Invoice revenue/cogs/gross_profit = sum over confirmed, non-data-entry invoices
        #     (mirrors exactly which invoices go through confirm_invoice in the live sync path)
        real_invoices = invoices.filter(is_data_entry=False)
        for inv in real_invoices:
            cf.total_invoice_revenue += inv.grand_total or Decimal("0")
            cf.total_invoice_cogs    += inv.total_cogs or Decimal("0")
            cf.total_gross_profit    += inv.gross_profit or Decimal("0")
        self.stdout.write(f"  total_invoice_revenue: {cf.total_invoice_revenue}")
        self.stdout.write(f"  total_invoice_cogs: {cf.total_invoice_cogs}")
        self.stdout.write(f"  total_gross_profit: {cf.total_gross_profit}")

        # 11. total_cash_inflow / total_cash_outflow — the two gross halves
        #     of cash_in_hand, used by the Cash In Hand breakdown's no-filter
        #     totals bar (O(1) read instead of a live sum on every load).
        #     Reuses the same aggregator get_cash_in_hand_as_of() is built
        #     on (cross-verified against live cash_in_hand at build time)
        #     instead of duplicating the 13-source logic here by hand.
        from cash_flow.selectors import get_cash_flow_totals_up_to
        totals = get_cash_flow_totals_up_to(None)
        cf.total_cash_inflow  = totals["inflow"]
        cf.total_cash_outflow = totals["outflow"]
        self.stdout.write(f"  total_cash_inflow: {cf.total_cash_inflow}")
        self.stdout.write(f"  total_cash_outflow: {cf.total_cash_outflow}")

        # 12. Dashboard counts — stored so get_cashflow_stats() never runs a
        #     live COUNT. Same filters the selector used before the counters.
        cf.total_invoices_count = invoices.filter(is_data_entry=False).count()
        cf.total_purchases_count = PurchaseOrder.objects.filter(
            is_deleted=False, is_data_entry=False, status="confirmed",
        ).count()
        cf.total_expenses_count = Expense.objects.filter(is_deleted=False).count()
        self.stdout.write(f"  total_invoices_count: {cf.total_invoices_count}")
        self.stdout.write(f"  total_purchases_count: {cf.total_purchases_count}")
        self.stdout.write(f"  total_expenses_count: {cf.total_expenses_count}")

        cf.save()
        self.stdout.write(self.style.SUCCESS("\nCashFlow backfill complete."))
        self.stdout.write(f"""
Final CashFlow state:
  cash_in_hand                  : {cf.cash_in_hand}
  total_cash_inflow             : {cf.total_cash_inflow}
  total_cash_outflow            : {cf.total_cash_outflow}
  customer_outstanding          : {cf.customer_outstanding}
  total_invoices_cash           : {cf.total_invoices_cash}
  total_paid_payables           : {cf.total_paid_payables}
  supplier_payable_outstanding  : {cf.supplier_payable_outstanding}
  total_purchases_cash          : {cf.total_purchases_cash}
  total_expenses_amount         : {cf.total_expenses_amount}
  total_recurring_expenses_paid : {cf.total_recurring_expenses_paid}
  total_lost_inventory_worth    : {cf.total_lost_inventory_worth}
  total_lost_inventory_recovered: {cf.total_lost_inventory_recovered}
  total_purchase_returns_value  : {cf.total_purchase_returns_value}
  total_purchase_returns_cogs   : {cf.total_purchase_returns_cogs}
  total_customer_returns_value  : {cf.total_customer_returns_value}
  total_customer_returns_cogs   : {cf.total_customer_returns_cogs}
  total_invoice_revenue         : {cf.total_invoice_revenue}
  total_invoice_cogs            : {cf.total_invoice_cogs}
  total_gross_profit            : {cf.total_gross_profit}
""")