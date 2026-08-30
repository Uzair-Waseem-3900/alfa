from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from billing.models import Invoice
from billing.services import (
    confirm_invoice, create_customer, create_invoice, set_invoice_item_shelf_allocations,
)
from cash_flow.models import CashFlow
from purchases.models import Category, Product, Shelf
from purchases.services import (
    confirm_purchase_order, create_purchase_order, create_supplier,
    set_purchase_item_shelf_allocations,
)
from rates.services import create_rate
from users.models import User

from payment_methods.models import PaymentMethod

from .models import (
    MonthlyProfit, MonthlyProfitInvestorShare, MonthlyProfitOwnerShare, ProfitFlow,
)
from .services import (
    _add_months, _finalize_month, catch_up_monthly_profits,
    create_investor_profit_payout, create_owner_profit_payout,
    delete_owner_profit_payout,
)
from .views import InvestorProfitPayoutRetrieveDestroyView, MonthlyProfitDetailView


def make_admin(email="admin@example.com"):
    return User.objects.create_user(
        email=email, password="Adm1n-secret!", first_name="Admin",
        last_name="User", is_staff=True,
    )


class ProfitsTestBase(TestCase):
    """One confirmed invoice (revenue 400, COGS 200) backdated into last
    month, plus a 100 expense in that month → net profit 100."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.admin = make_admin()

        category = Category.objects.create(name="Cat A")
        shelf = Shelf.objects.create(name="Shelf A")
        supplier = create_supplier(name="Ali Traders", code="ALI", user=self.admin)
        customer = create_customer(name="Big Mart", code="BM", address="Main St", user=self.admin)

        product = Product.objects.create(name="Product 1", code="P001", category=category)
        create_rate(product_id=product.id, selling_price=Decimal("100"), user=self.admin)
        order = create_purchase_order(
            supplier_id=supplier.id,
            items=[{"product_id": product.id, "quantity": 10, "unit_price": Decimal("50")}],
            user=self.admin,
        )
        for item in order.items.all():
            set_purchase_item_shelf_allocations(
                purchase_item_id=item.id,
                allocations=[{"shelf_id": shelf.id, "quantity": item.quantity}],
                user=self.admin,
            )
        confirm_purchase_order(order_id=order.id, user=self.admin)

        invoice = create_invoice(
            customer_id=customer.id,
            items=[{"product_id": product.id, "quantity": 4}],
            user=self.admin,
        )
        for item in invoice.items.all():
            set_invoice_item_shelf_allocations(
                invoice_item_id=item.id,
                allocations=[{"shelf_id": shelf.id, "quantity": item.quantity}],
                user=self.admin,
            )
        confirm_invoice(invoice_id=invoice.id, user=self.admin)

        # Backdate the confirmation into last month so catch-up finalizes it.
        today = timezone.localdate()
        y, m = _add_months(today.year, today.month, -1)
        self.period = f"{y:04d}-{m:02d}"
        Invoice.objects.filter(pk=invoice.pk).update(
            confirmed_at=timezone.now().replace(year=y, month=m, day=15),
        )

        from cash_flow.services import create_expense, create_expense_category
        from data_entry.services import create_opening_cash
        create_opening_cash(amount=Decimal("10000"), user=self.admin)
        self.cash = PaymentMethod.objects.get_or_create(name="Cash", defaults={"balance": Decimal("1000000")})[0]
        cat = create_expense_category(name="Utilities", user=self.admin)
        create_expense(
            name="Electricity", category_id=cat.id, amount=Decimal("100"),
            expense_date=timezone.now().date().replace(year=y, month=m, day=20),
            method_allocations=self.cash_split("100"), user=self.admin,
        )
        # create_expense's allocation write updates the DB row directly, not
        # this in-memory self.cash instance — refresh so every test starts
        # from the real balance, not the stale one captured before the
        # expense above was recorded against it.
        self.cash.refresh_from_db()

    def cash_split(self, amount):
        return [(self.cash, Decimal(amount))]


class MonthlyProfitFinalizationTests(ProfitsTestBase):
    def test_catch_up_finalizes_month_with_exact_numbers(self):
        catch_up_monthly_profits()

        mp = MonthlyProfit.objects.get(period=self.period)
        self.assertEqual(mp.gross_profit, Decimal("200.0000"))
        self.assertEqual(mp.net_gross_profit, Decimal("200.0000"))
        self.assertEqual(mp.expenses_paid, Decimal("100.0000"))
        self.assertEqual(mp.net_profit, Decimal("100.0000"))

        # No investors → the owner gets the exact full remainder.
        self.assertEqual(mp.total_investor_share_amount, Decimal("0"))
        owner_share = MonthlyProfitOwnerShare.objects.get(monthly_profit=mp)
        self.assertEqual(owner_share.share_amount, Decimal("100.0000"))

        pf = ProfitFlow.get_instance()
        self.assertEqual(pf.total_net_profit, Decimal("100.0000"))
        self.assertEqual(pf.months_finalized_count, 1)

        # Idempotent: another catch-up / direct finalize never recomputes.
        catch_up_monthly_profits()
        self.assertEqual(MonthlyProfit.objects.filter(period=self.period).count(), 1)
        self.assertEqual(_finalize_month(self.period).pk, mp.pk)
        self.assertEqual(ProfitFlow.get_instance().months_finalized_count, 1)

    def test_owner_payout_round_trip(self):
        catch_up_monthly_profits()
        owner_share = MonthlyProfitOwnerShare.objects.get(monthly_profit__period=self.period)
        cash_start = CashFlow.get_instance().cash_in_hand

        payout = create_owner_profit_payout(
            owner_share_id=owner_share.id, amount=Decimal("40"), action_type="payout",
            method_allocations=self.cash_split("40"),
            payout_date=timezone.now().date(), user=self.admin,
        )
        owner_share.refresh_from_db()
        self.assertEqual(owner_share.amount_paid_out, Decimal("40.0000"))
        self.assertEqual(owner_share.payment_status, "partial")
        self.assertEqual(CashFlow.get_instance().cash_in_hand, cash_start - Decimal("40"))

        delete_owner_profit_payout(pk=payout.pk, user=self.admin)
        owner_share.refresh_from_db()
        self.assertEqual(owner_share.amount_paid_out, Decimal("0.0000"))
        self.assertEqual(owner_share.payment_status, "unpaid")
        self.assertEqual(CashFlow.get_instance().cash_in_hand, cash_start)


class MonthDetailQueryStabilityTests(ProfitsTestBase):
    def detail(self):
        request = self.factory.get(f"/profits/monthly/{self.period}/")
        force_authenticate(request, user=self.admin)
        return MonthlyProfitDetailView.as_view()(request, period=self.period)

    def test_detail_queries_constant_as_payouts_grow(self):
        catch_up_monthly_profits()
        owner_share = MonthlyProfitOwnerShare.objects.get(monthly_profit__period=self.period)
        create_owner_profit_payout(
            owner_share_id=owner_share.id, amount=Decimal("10"), action_type="payout",
            method_allocations=self.cash_split("10"),
            payout_date=timezone.now().date(), user=self.admin,
        )

        with CaptureQueriesContext(connection) as ctx_small:
            response = self.detail()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["owner_share"]["payouts"]), 1)

        for _ in range(2):
            create_owner_profit_payout(
                owner_share_id=owner_share.id, amount=Decimal("10"), action_type="payout",
                method_allocations=self.cash_split("10"),
                payout_date=timezone.now().date(), user=self.admin,
            )

        with CaptureQueriesContext(connection) as ctx_large:
            response = self.detail()
        self.assertEqual(len(response.data["owner_share"]["payouts"]), 3)
        # The filtered Prefetch serves the payout lists — query count must not
        # scale with payout (or share) count.
        self.assertEqual(len(ctx_small.captured_queries), len(ctx_large.captured_queries))


class ProfitPayoutMethodAllocationTests(ProfitsTestBase):
    """Phase 4: give (payout) requires a method split through the Phase 2
    engine; reinvest silently defaults both its own outflow leg and the
    (Phase 5-pending) inflow leg to Cash, no user prompt."""

    def setUp(self):
        super().setUp()
        catch_up_monthly_profits()
        self.owner_share = MonthlyProfitOwnerShare.objects.get(monthly_profit__period=self.period)

    def test_payout_without_method_allocations_rejected(self):
        from rest_framework.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            create_owner_profit_payout(
                owner_share_id=self.owner_share.id, amount=Decimal("10"), action_type="payout",
                payout_date=timezone.now().date(), user=self.admin,
            )

    def test_payout_records_allocation_and_moves_method_balance(self):
        from payment_methods.models import PaymentAllocation

        cash_start = self.cash.balance
        payout = create_owner_profit_payout(
            owner_share_id=self.owner_share.id, amount=Decimal("15"), action_type="payout",
            method_allocations=self.cash_split("15"), payout_date=timezone.now().date(), user=self.admin,
        )
        self.cash.refresh_from_db()
        self.assertEqual(self.cash.balance, cash_start - Decimal("15"))
        self.assertEqual(
            PaymentAllocation.objects.filter(
                source_model="profits.ownerprofitpayout", source_id=payout.id, is_deleted=False,
            ).count(),
            1,
        )

    def test_reinvest_needs_no_method_allocations_and_defaults_to_cash(self):
        from payment_methods.models import PaymentAllocation, PaymentMethod

        payout = create_owner_profit_payout(
            owner_share_id=self.owner_share.id, amount=Decimal("20"), action_type="reinvest",
            payout_date=timezone.now().date(), user=self.admin,
        )
        alloc = PaymentAllocation.objects.get(
            source_model="profits.ownerprofitpayout", source_id=payout.id, is_deleted=False,
        )
        self.assertEqual(alloc.payment_method_id, self.cash.id)
        self.assertEqual(alloc.direction, "outflow")
        self.assertEqual(alloc.amount, Decimal("20"))
        # Cash was already seeded by setUp — reinvest resolves the SAME
        # protected row, not a second one.
        self.assertEqual(PaymentMethod.objects.filter(name="Cash").count(), 1)

    def test_delete_payout_reverses_allocation(self):
        from payment_methods.models import PaymentAllocation

        cash_start = self.cash.balance
        payout = create_owner_profit_payout(
            owner_share_id=self.owner_share.id, amount=Decimal("15"), action_type="payout",
            method_allocations=self.cash_split("15"), payout_date=timezone.now().date(), user=self.admin,
        )
        delete_owner_profit_payout(pk=payout.pk, user=self.admin)
        self.cash.refresh_from_db()
        self.assertEqual(self.cash.balance, cash_start)
        self.assertFalse(
            PaymentAllocation.objects.filter(
                source_model="profits.ownerprofitpayout", source_id=payout.id, is_deleted=False,
            ).exists(),
        )


class InvestorProfitPayoutDetailViewTests(ProfitsTestBase):
    """GET /profits/payouts/<pk>/ — InvestorProfitPayoutDetailSerializer is
    deliberately separate from InvestorProfitPayoutReadSerializer (used
    nested in MonthlyProfitDetailView) so this endpoint can show
    investor_name/period without adding a query the nested list doesn't
    already pay for (see the serializer's own docstring)."""

    def setUp(self):
        super().setUp()
        catch_up_monthly_profits()
        from cash_management.services import create_investor
        investor = create_investor(name="Zafar Capital", growth_rate=Decimal("0"), user=self.admin)
        mp = MonthlyProfit.objects.get(period=self.period)
        self.share = MonthlyProfitInvestorShare.objects.create(
            monthly_profit=mp, investor=investor, investor_name_snapshot=investor.name,
            share_percent_snapshot=Decimal("50"), share_amount=Decimal("50"),
        )

    def test_detail_view_returns_investor_name_and_period(self):
        payout = create_investor_profit_payout(
            share_id=self.share.id, amount=Decimal("20"), action_type="payout",
            method_allocations=self.cash_split("20"), payout_date=timezone.now().date(), user=self.admin,
        )
        request = self.factory.get(f"/profits/payouts/{payout.id}/")
        force_authenticate(request, user=self.admin)
        with CaptureQueriesContext(connection) as ctx:
            response = InvestorProfitPayoutRetrieveDestroyView.as_view()(request, pk=payout.id)
            response.render()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["investor_name"], "Zafar Capital")
        self.assertEqual(response.data["period"], self.period)
        self.assertEqual(response.data["share"], self.share.id)
        self.assertEqual(len(response.data["allocations"]), 1)
        self.assertLessEqual(len(ctx.captured_queries), 5)

    def test_monthly_detail_query_count_unaffected_by_new_serializer(self):
        # Confirms the new detail-only serializer didn't touch the nested
        # investor payouts path (MonthlyProfitDetailView reuses
        # InvestorProfitPayoutReadSerializer, not the new one).
        create_investor_profit_payout(
            share_id=self.share.id, amount=Decimal("10"), action_type="payout",
            method_allocations=self.cash_split("10"), payout_date=timezone.now().date(), user=self.admin,
        )

        def detail():
            request = self.factory.get(f"/profits/monthly/{self.period}/")
            force_authenticate(request, user=self.admin)
            return MonthlyProfitDetailView.as_view()(request, period=self.period)

        with CaptureQueriesContext(connection) as ctx_small:
            response = detail()
        self.assertEqual(response.status_code, 200)

        for _ in range(2):
            create_investor_profit_payout(
                share_id=self.share.id, amount=Decimal("5"), action_type="payout",
                method_allocations=self.cash_split("5"), payout_date=timezone.now().date(), user=self.admin,
            )
        with CaptureQueriesContext(connection) as ctx_large:
            response = detail()
        self.assertEqual(len(ctx_small.captured_queries), len(ctx_large.captured_queries))
