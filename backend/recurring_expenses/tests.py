from datetime import date
from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory, force_authenticate

from cash_flow.models import CashFlow
from cash_flow.services import sync_invoice_payment_received
from payment_methods.models import PaymentMethod
from users.models import User

from .models import RecurringExpenseFlow, RecurringExpenseMonthlyStats
from .services import (
    create_recurring_expense, create_recurring_expense_assignment,
    create_recurring_expense_category, create_recurring_expense_payment,
    delete_recurring_expense, delete_recurring_expense_assignment,
    delete_recurring_expense_payment, update_recurring_expense,
)
from .views import (
    RecurringExpenseAssignmentListCreateView, RecurringExpenseListCreateView,
    RecurringExpensePendingDuesView,
)


def make_admin(email="admin@example.com"):
    return User.objects.create_user(
        email=email, password="Adm1n-secret!", first_name="Admin",
        last_name="User", is_staff=True,
    )


def make_normal_user(email="normal@example.com"):
    return User.objects.create_user(
        email=email, password="N0rmal-secret!", first_name="Normal", last_name="User",
    )


class RecurringExpensesTestBase(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.admin = make_admin()
        self.category = create_recurring_expense_category(name="Salaries", user=self.admin)
        self.template = create_recurring_expense(
            name="Office Rent", category_id=self.category.id,
            amount=Decimal("5000"), start_date=date(2026, 8, 15), user=self.admin,
        )
        # Seed cash — cash_in_hand floors at 0, so payments from an empty
        # till would vanish and hide round-trip errors.
        sync_invoice_payment_received(amount=Decimal("100000"), user=self.admin)
        self.cash_method = PaymentMethod.objects.get_or_create(name="Cash", defaults={"balance": Decimal("1000000")})[0]

    def flow(self):
        return RecurringExpenseFlow.get_instance()

    def monthly(self, period):
        return RecurringExpenseMonthlyStats.objects.get(period=period)

    def cash(self):
        return CashFlow.get_instance().cash_in_hand

    def cash_split(self, amount):
        return [(self.cash_method, Decimal(amount))]


class TemplateFlowTests(RecurringExpensesTestBase):
    def test_create_bumps_active_obligation(self):
        flow = self.flow()
        self.assertEqual(flow.total_active_templates, 1)
        self.assertEqual(flow.total_active_monthly_obligation, Decimal("5000"))

    def test_deactivate_reactivate_and_amount_change(self):
        update_recurring_expense(pk=self.template.pk, is_active=False, user=self.admin)
        flow = self.flow()
        self.assertEqual((flow.total_active_templates, flow.total_active_monthly_obligation),
                         (0, Decimal("0")))

        update_recurring_expense(pk=self.template.pk, is_active=True, user=self.admin)
        update_recurring_expense(pk=self.template.pk, amount=Decimal("6000"), user=self.admin)
        flow = self.flow()
        self.assertEqual((flow.total_active_templates, flow.total_active_monthly_obligation),
                         (1, Decimal("6000")))

    def test_delete_active_template_removes_obligation(self):
        delete_recurring_expense(pk=self.template.pk, user=self.admin)
        flow = self.flow()
        self.assertEqual((flow.total_active_templates, flow.total_active_monthly_obligation),
                         (0, Decimal("0")))


class AssignmentPaymentRoundTripTests(RecurringExpensesTestBase):
    def test_full_lifecycle_round_trips_every_synced_number(self):
        cash_start = self.cash()

        assignment = create_recurring_expense_assignment(
            recurring_expense_id=self.template.id, period="2026-08", user=self.admin,
        )
        flow = self.flow()
        self.assertEqual(flow.total_assigned_amount, Decimal("5000"))
        self.assertEqual(flow.total_pending_amount, Decimal("5000"))
        self.assertEqual(flow.total_assignments_count, 1)
        month = self.monthly("2026-08")
        self.assertEqual((month.total_assigned, month.total_pending, month.is_fully_paid),
                         (Decimal("5000"), Decimal("5000"), False))

        p1 = create_recurring_expense_payment(
            assignment_id=assignment.id, amount=Decimal("2000"),
            payment_date=timezone.now().date(), method_allocations=self.cash_split("2000"), user=self.admin,
        )
        assignment.refresh_from_db()
        self.assertEqual(assignment.payment_status, "partial")
        self.assertEqual(self.cash(), cash_start - Decimal("2000"))

        p2 = create_recurring_expense_payment(
            assignment_id=assignment.id, amount=Decimal("3000"),
            payment_date=timezone.now().date(), method_allocations=self.cash_split("3000"), user=self.admin,
        )
        assignment.refresh_from_db()
        self.assertEqual(assignment.payment_status, "paid")
        month = self.monthly("2026-08")
        self.assertTrue(month.is_fully_paid)
        self.assertEqual(self.cash(), cash_start - Decimal("5000"))

        # Overpayment guard unchanged.
        with self.assertRaises(ValidationError):
            create_recurring_expense_payment(
                assignment_id=assignment.id, amount=Decimal("1"),
                payment_date=timezone.now().date(), method_allocations=self.cash_split("1"), user=self.admin,
            )

        # Unassigning with payments recorded is still rejected.
        with self.assertRaises(ValidationError):
            delete_recurring_expense_assignment(pk=assignment.pk, user=self.admin)

        # Delete both payments — everything must restore exactly.
        delete_recurring_expense_payment(pk=p2.pk, user=self.admin)
        assignment.refresh_from_db()
        self.assertEqual(assignment.payment_status, "partial")
        self.assertFalse(self.monthly("2026-08").is_fully_paid)

        delete_recurring_expense_payment(pk=p1.pk, user=self.admin)
        assignment.refresh_from_db()
        self.assertEqual(assignment.payment_status, "unpaid")
        self.assertEqual(self.cash(), cash_start)

        # Now unassigning works, and flow/monthly return to zero.
        delete_recurring_expense_assignment(pk=assignment.pk, user=self.admin)
        flow = self.flow()
        self.assertEqual(flow.total_assigned_amount, Decimal("0"))
        self.assertEqual(flow.total_assignments_count, 0)
        month = self.monthly("2026-08")
        self.assertEqual((month.total_assigned, month.total_pending), (Decimal("0"), Decimal("0")))


class PendingDuesTests(RecurringExpensesTestBase):
    def pending_names(self, period):
        request = self.factory.get("/recurring-expenses/pending-dues/", {"period": period})
        force_authenticate(request, user=self.admin)
        response = RecurringExpensePendingDuesView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        return [r["name"] for r in response.data["results"]]

    def test_start_month_eligibility_boundary(self):
        # start_date 2026-08-15 → eligible for its own start month, not before.
        self.assertEqual(self.pending_names("2026-08"), ["Office Rent"])
        self.assertEqual(self.pending_names("2026-07"), [])

    def test_assigned_template_leaves_pending_list(self):
        create_recurring_expense_assignment(
            recurring_expense_id=self.template.id, period="2026-08", user=self.admin,
        )
        self.assertEqual(self.pending_names("2026-08"), [])


class SearchAndPermissionTests(RecurringExpensesTestBase):
    def test_template_search(self):
        create_recurring_expense(
            name="Internet Bill", category_id=self.category.id,
            amount=Decimal("100"), start_date=date(2026, 1, 1), user=self.admin,
        )
        request = self.factory.get("/recurring-expenses/", {"search": "RENT"})
        force_authenticate(request, user=self.admin)
        response = RecurringExpenseListCreateView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([r["name"] for r in response.data["results"]], ["Office Rent"])

    def test_assignment_snapshot_search(self):
        create_recurring_expense_assignment(
            recurring_expense_id=self.template.id, period="2026-08", user=self.admin,
        )
        request = self.factory.get("/recurring-expenses/assignments/", {"search": "office"})
        force_authenticate(request, user=self.admin)
        response = RecurringExpenseAssignmentListCreateView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)

    def test_normal_user_gets_403(self):
        request = self.factory.get("/recurring-expenses/")
        force_authenticate(request, user=make_normal_user())
        response = RecurringExpenseListCreateView.as_view()(request)
        self.assertEqual(response.status_code, 403)


class RecurringExpensePaymentAllocationQueryCountTests(RecurringExpensesTestBase):
    """architecture.md's STRICT O(1)-per-page rule — Phase 5 Batch D's
    allocations field must not N+1 as row count grows."""

    def count_queries(self, view, url):
        request = self.factory.get(url)
        force_authenticate(request, user=self.admin)
        with CaptureQueriesContext(connection) as ctx:
            response = view(request)
            response.render()
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries)

    def test_payment_list_query_count_flat(self):
        from .views import RecurringExpenseAssignmentPaymentListCreateView

        assignment = create_recurring_expense_assignment(
            recurring_expense_id=self.template.id, period="2026-08", user=self.admin,
        )
        create_recurring_expense_payment(
            assignment_id=assignment.id, amount=Decimal("500"),
            payment_date=timezone.now().date(), method_allocations=self.cash_split("500"), user=self.admin,
        )
        view = RecurringExpenseAssignmentPaymentListCreateView.as_view()
        baseline = self.count_queries(view, "/recurring-expenses/payments/")

        for _ in range(4):
            create_recurring_expense_payment(
                assignment_id=assignment.id, amount=Decimal("500"),
                payment_date=timezone.now().date(), method_allocations=self.cash_split("500"), user=self.admin,
            )
        grown = self.count_queries(view, "/recurring-expenses/payments/")
        self.assertEqual(baseline, grown)
