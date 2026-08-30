from decimal import Decimal

from django.core.management.base import BaseCommand

from recurring_expenses.models import (
    RecurringExpense, RecurringExpenseAssignment, RecurringExpenseAssignmentPayment,
    RecurringExpenseFlow, RecurringExpenseMonthlyStats,
)


class Command(BaseCommand):
    help = "Backfills RecurringExpenseFlow and every RecurringExpenseMonthlyStats row from existing assignments/payments."

    def handle(self, *args, **kwargs):
        self.stdout.write("Starting RecurringExpenses backfill...\n")

        # Reset singleton — EVERY field this command touches must be reset
        # here, same idempotency discipline as every other backfill command
        # in this project.
        flow, _ = RecurringExpenseFlow.objects.get_or_create(pk=1)
        flow.total_assigned_amount = Decimal("0")
        flow.total_paid_amount     = Decimal("0")
        flow.total_pending_amount  = Decimal("0")
        flow.total_assignments_count = 0
        flow.total_active_templates  = 0
        flow.total_active_monthly_obligation = Decimal("0")
        flow.save()

        # 1. Active template totals
        for t in RecurringExpense.objects.filter(is_deleted=False, is_active=True):
            flow.total_active_templates += 1
            flow.total_active_monthly_obligation += t.amount
        self.stdout.write(f"  total_active_templates: {flow.total_active_templates}")
        self.stdout.write(f"  total_active_monthly_obligation: {flow.total_active_monthly_obligation}")

        # 2. Assignment totals — every assignment ever created (assignments are
        #    permanent, never soft-deleted, so no is_deleted filter needed).
        for a in RecurringExpenseAssignment.objects.all():
            flow.total_assigned_amount += a.amount
            flow.total_assignments_count += 1
        self.stdout.write(f"  total_assigned_amount: {flow.total_assigned_amount}")
        self.stdout.write(f"  total_assignments_count: {flow.total_assignments_count}")

        # 3. Payment totals (non-deleted only)
        for p in RecurringExpenseAssignmentPayment.objects.filter(is_deleted=False):
            flow.total_paid_amount += p.amount
        self.stdout.write(f"  total_paid_amount: {flow.total_paid_amount}")

        flow.total_pending_amount = max(Decimal("0"), flow.total_assigned_amount - flow.total_paid_amount)
        flow.save()

        # 4. Per-assignment amount_paid/payment_status — recomputed from
        #    scratch off non-deleted payments, same idempotency discipline.
        for a in RecurringExpenseAssignment.objects.all():
            paid = Decimal("0")
            for p in RecurringExpenseAssignmentPayment.objects.filter(assignment=a, is_deleted=False):
                paid += p.amount
            if paid <= 0:
                status = RecurringExpenseAssignment.PaymentStatus.UNPAID
            elif paid >= a.amount:
                status = RecurringExpenseAssignment.PaymentStatus.PAID
            else:
                status = RecurringExpenseAssignment.PaymentStatus.PARTIAL
            if a.amount_paid != paid or a.payment_status != status:
                a.amount_paid = paid
                a.payment_status = status
                a.save(update_fields=["amount_paid", "payment_status"])

        # 5. Monthly stats — one row per distinct period seen across all assignments.
        RecurringExpenseMonthlyStats.objects.all().delete()
        periods = set(RecurringExpenseAssignment.objects.values_list("period", flat=True))
        for period in sorted(periods):
            assigned = Decimal("0")
            for a in RecurringExpenseAssignment.objects.filter(period=period):
                assigned += a.amount
            # Paid amount always attributed to the ASSIGNMENT's own period —
            # matches the live sync in _adjust_recurring_expense_monthly_stats.
            paid = Decimal("0")
            for a in RecurringExpenseAssignment.objects.filter(period=period):
                for p in RecurringExpenseAssignmentPayment.objects.filter(assignment=a, is_deleted=False):
                    paid += p.amount
            pending = max(Decimal("0"), assigned - paid)
            RecurringExpenseMonthlyStats.objects.create(
                period=period,
                total_assigned=assigned,
                total_paid=paid,
                total_pending=pending,
                is_fully_paid=(assigned > 0 and pending == 0),
            )
        self.stdout.write(f"  monthly stats rows rebuilt: {len(periods)}")

        # 6. CashFlow.total_recurring_expenses_paid — kept in step by
        #    backfill_cashflow, but recomputed here too so this command alone
        #    is a complete, correct picture if run standalone.
        try:
            from cash_flow.models import CashFlow
            cf = CashFlow.get_instance()
            total_paid_all = Decimal("0")
            for p in RecurringExpenseAssignmentPayment.objects.filter(is_deleted=False):
                total_paid_all += p.amount
            cf.total_recurring_expenses_paid = total_paid_all
            cf.save(update_fields=["total_recurring_expenses_paid"])
            self.stdout.write(f"  CashFlow.total_recurring_expenses_paid: {total_paid_all}")
        except Exception:
            pass

        self.stdout.write(self.style.SUCCESS("\nRecurringExpenses backfill complete."))
        self.stdout.write(f"""
Final RecurringExpenseFlow state:
  total_assigned_amount           : {flow.total_assigned_amount}
  total_paid_amount               : {flow.total_paid_amount}
  total_pending_amount            : {flow.total_pending_amount}
  total_assignments_count         : {flow.total_assignments_count}
  total_active_templates          : {flow.total_active_templates}
  total_active_monthly_obligation : {flow.total_active_monthly_obligation}
""")
