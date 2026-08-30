from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from billing.models import Customer
from billing.services import (
    accept_return, confirm_invoice, create_customer, create_invoice,
    create_payment, create_return, set_invoice_item_shelf_allocations,
    set_return_item_shelf_allocations, update_invoice_due_date,
)
from purchases.models import Category, Shelf
from purchases.services import (
    confirm_purchase_order, create_purchase_order, create_supplier,
    set_purchase_item_shelf_allocations,
)
from rates.services import create_rate
from users.models import User

from payment_methods.models import PaymentMethod

from .models import CreditScoreFlow, CreditScoreHistory, CustomerCreditScore, ScoreTier
from .services import recalculate_credit_score, run_overdue_catchup
from .views import CustomerCreditScoreHistoryView


def make_admin(email="csadmin@example.com"):
    return User.objects.create_user(
        email=email, password="Adm1n-secret!", first_name="Admin",
        last_name="User", is_staff=True,
    )


class CreditScoreTestBase(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.admin = make_admin()
        self.category = Category.objects.create(name="Cat A")
        self.shelf = Shelf.objects.create(name="Shelf A")
        self.supplier = create_supplier(name="Ali Traders", code="ALI", user=self.admin)
        self.customer = create_customer(
            name="Big Mart", code="BM", address="Main St", user=self.admin,
        )
        self.cash = PaymentMethod.objects.get_or_create(name="Cash", defaults={"balance": Decimal("1000000")})[0]

    def cash_split(self, amount):
        return [(self.cash, Decimal(amount))]

    def make_stocked_product(self, code="P001", name="Product 1", *, stock=20,
                             unit_cost="50", selling_price="100"):
        from purchases.models import Product
        product = Product.objects.create(
            name=name, code=code, category=self.category,
        )
        create_rate(product_id=product.id, selling_price=Decimal(selling_price), user=self.admin)
        order = create_purchase_order(
            supplier_id=self.supplier.id,
            items=[{"product_id": product.id, "quantity": stock, "unit_price": Decimal(unit_cost)}],
            user=self.admin,
        )
        for item in order.items.all():
            set_purchase_item_shelf_allocations(
                purchase_item_id=item.id,
                allocations=[{"shelf_id": self.shelf.id, "quantity": item.quantity}],
                user=self.admin,
            )
        confirm_purchase_order(order_id=order.id, user=self.admin)
        return product

    def confirm_invoice_for(self, product, quantity=1, due_date=None, customer=None):
        invoice = create_invoice(
            customer_id=(customer or self.customer).id,
            items=[{"product_id": product.id, "quantity": quantity}],
            payment_due_date=due_date, user=self.admin,
        )
        for item in invoice.items.all():
            set_invoice_item_shelf_allocations(
                invoice_item_id=item.id,
                allocations=[{"shelf_id": self.shelf.id, "quantity": item.quantity}],
                user=self.admin,
            )
        return confirm_invoice(invoice_id=invoice.id, user=self.admin)


class CreditScoreInitializationTests(CreditScoreTestBase):
    def test_customer_gets_baseline_score_immediately(self):
        score = CustomerCreditScore.objects.get(customer=self.customer)
        self.assertEqual(score.score, 50)
        self.assertEqual(score.tier, ScoreTier.AVERAGE)

        history = CreditScoreHistory.objects.filter(customer=self.customer)
        self.assertEqual(history.count(), 1)
        self.assertEqual(history.first().trigger, "customer_created")

    def test_initializing_twice_does_not_duplicate(self):
        from .services import initialize_credit_score
        initialize_credit_score(self.customer, self.admin)
        initialize_credit_score(self.customer, self.admin)
        self.assertEqual(CustomerCreditScore.objects.filter(customer=self.customer).count(), 1)
        self.assertEqual(CreditScoreHistory.objects.filter(customer=self.customer).count(), 1)


class CreditScoreRecalculationTests(CreditScoreTestBase):
    def test_new_customer_first_overdue_invoice_lands_in_average_not_poor(self):
        product = self.make_stocked_product()
        past_date = timezone.localtime(timezone.now()).date() - timedelta(days=10)
        self.confirm_invoice_for(product, quantity=1, due_date=past_date)

        # Nothing else moves the score until the catch-up sweep notices it's overdue.
        run_overdue_catchup(user=self.admin)

        score = CustomerCreditScore.objects.get(customer=self.customer)
        self.assertEqual(score.tier, ScoreTier.AVERAGE)
        self.assertGreater(score.score, 30)
        self.assertLess(score.score, 70)

    def test_confirm_invoice_writes_history_entry(self):
        product = self.make_stocked_product()
        invoice = self.confirm_invoice_for(product, quantity=1)

        history = CreditScoreHistory.objects.filter(customer=self.customer).order_by("-created_at")
        latest = history.first()
        self.assertEqual(latest.trigger, "invoice_confirmed")
        self.assertEqual(latest.reference, invoice.bill_number)

    def test_full_payment_improves_score_vs_unpaid(self):
        product = self.make_stocked_product()
        invoice = self.confirm_invoice_for(product, quantity=1)
        score_before_payment = CustomerCreditScore.objects.get(customer=self.customer).score

        create_payment(
            invoice_id=invoice.id, amount=invoice.grand_total, method_allocations=self.cash_split(invoice.grand_total),
            payment_date=timezone.now().date(), user=self.admin,
        )
        score_after_payment = CustomerCreditScore.objects.get(customer=self.customer).score

        self.assertGreaterEqual(score_after_payment, score_before_payment)

    def test_return_accepted_triggers_recalculation(self):
        product = self.make_stocked_product(stock=10, unit_cost="50", selling_price="100")
        invoice = self.confirm_invoice_for(product, quantity=4)
        item = invoice.items.first()

        history_count_before = CreditScoreHistory.objects.filter(customer=self.customer).count()
        # Returning 1 of 4 units (25% of invoice value) doesn't move the
        # rounded score at this customer's low confidence (1 confirmed
        # invoice) — returning 3 of 4 (75%) does, so this test exercises a
        # real recalculation instead of a no-op (see recalculate_credit_score:
        # a no-op recompute correctly writes no history row since 2026-08-31).
        ret = create_return(invoice_id=invoice.id,
                            items=[{"invoice_item_id": item.id, "quantity": 3}],
                            user=self.admin)
        for return_item in ret.items.all():
            set_return_item_shelf_allocations(
                return_item_id=return_item.id,
                allocations=[{"shelf_id": self.shelf.id, "quantity": return_item.quantity}],
                user=self.admin,
            )
        accept_return(return_id=ret.id, user=self.admin)

        history_count_after = CreditScoreHistory.objects.filter(customer=self.customer).count()
        self.assertEqual(history_count_after, history_count_before + 1)
        self.assertEqual(
            CreditScoreHistory.objects.filter(customer=self.customer).latest("created_at").trigger,
            "return_accepted",
        )

    def test_due_date_extension_triggers_recalculation(self):
        product = self.make_stocked_product()
        past_date = timezone.localtime(timezone.now()).date() - timedelta(days=1)
        invoice = self.confirm_invoice_for(product, quantity=1, due_date=past_date)
        run_overdue_catchup(user=self.admin)
        score_while_overdue = CustomerCreditScore.objects.get(customer=self.customer).score

        future_date = timezone.localtime(timezone.now()).date() + timedelta(days=30)
        update_invoice_due_date(invoice_id=invoice.id, new_due_date=future_date, user=self.admin)

        score_after_extension = CustomerCreditScore.objects.get(customer=self.customer).score
        self.assertGreater(score_after_extension, score_while_overdue)
        self.assertEqual(
            CreditScoreHistory.objects.filter(customer=self.customer).latest("created_at").trigger,
            "due_date_extended",
        )

    def test_zero_invoice_customer_recalculates_to_baseline_safely(self):
        # No confirmed invoices at all — must not crash on division by zero.
        recalculate_credit_score(customer_id=self.customer.id, user=self.admin, trigger="test")
        score = CustomerCreditScore.objects.get(customer=self.customer)
        self.assertEqual(score.score, 50)
        self.assertEqual(score.tier, ScoreTier.AVERAGE)

    def test_noop_recalculation_does_not_write_history_row(self):
        # Found 2026-08-31: a no-op recompute (e.g. daily overdue_catchup
        # re-checking a customer whose score/tier hasn't moved) was writing
        # a fresh "44 -> 44" history row every time — CreditScoreHistory
        # exists to answer "why did this score change", so nothing should
        # be written when nothing changed.
        recalculate_credit_score(customer_id=self.customer.id, user=self.admin, trigger="test")
        count_after_first = CreditScoreHistory.objects.filter(customer=self.customer).count()

        # Repeat calls with identical inputs — score/tier stay at baseline.
        recalculate_credit_score(customer_id=self.customer.id, user=self.admin, trigger="overdue_catchup")
        recalculate_credit_score(customer_id=self.customer.id, user=self.admin, trigger="overdue_catchup")

        count_after_repeats = CreditScoreHistory.objects.filter(customer=self.customer).count()
        self.assertEqual(count_after_first, count_after_repeats)


class OverdueCatchupTests(CreditScoreTestBase):
    def test_catchup_is_marker_gated_same_day(self):
        product = self.make_stocked_product()
        past_date = timezone.localtime(timezone.now()).date() - timedelta(days=1)
        self.confirm_invoice_for(product, quantity=1, due_date=past_date)

        first_run_count = run_overdue_catchup(user=self.admin)
        second_run_count = run_overdue_catchup(user=self.admin)

        self.assertEqual(first_run_count, 1)
        self.assertEqual(second_run_count, 0)  # already caught up today

    def test_catchup_updates_flow_marker(self):
        run_overdue_catchup(user=self.admin)
        flow = CreditScoreFlow.get_instance()
        self.assertEqual(flow.overdue_caught_up_through, timezone.localtime(timezone.now()).date())


class CreditScoreHistoryViewTests(CreditScoreTestBase):
    def test_history_view_is_customer_scoped(self):
        other_customer = create_customer(
            name="Other Co", code="OC", address="Elsewhere", user=self.admin,
        )
        product = self.make_stocked_product()
        self.confirm_invoice_for(product, quantity=1)
        self.confirm_invoice_for(product, quantity=1, customer=other_customer)

        request = self.factory.get(f"/credit-score/customers/{self.customer.id}/history/")
        force_authenticate(request, user=self.admin)
        response = CustomerCreditScoreHistoryView.as_view()(request, customer_id=self.customer.id)

        # Only this customer's own events (customer_created + invoice_confirmed) —
        # if the query leaked across customers this would be 4, not 2.
        self.assertEqual(len(response.data["results"]), 2)


class BackfillCreditScoresIdempotencyTests(CreditScoreTestBase):
    def test_backfill_is_idempotent(self):
        product = self.make_stocked_product()
        self.confirm_invoice_for(product, quantity=1)

        call_command("backfill_credit_scores", verbosity=0)
        first_score = CustomerCreditScore.objects.get(customer=self.customer).score

        call_command("backfill_credit_scores", verbosity=0)
        second_score = CustomerCreditScore.objects.get(customer=self.customer).score

        self.assertEqual(first_score, second_score)
        self.assertEqual(CustomerCreditScore.objects.filter(customer=self.customer).count(), 1)


class CleanupNoopCreditScoreHistoryTests(CreditScoreTestBase):
    """Cleans up the no-op rows that existed before recalculate_credit_score
    was fixed (2026-08-31) to stop writing them going forward."""

    def make_noop_row(self, score=44, tier=ScoreTier.AVERAGE):
        return CreditScoreHistory.objects.create(
            customer=self.customer,
            score_before=score, score_after=score,
            tier_before=tier, tier_after=tier,
            trigger="overdue_catchup",
        )

    def test_dry_run_deletes_nothing(self):
        self.make_noop_row()
        before = CreditScoreHistory.objects.count()
        call_command("cleanup_noop_credit_score_history", verbosity=0)
        self.assertEqual(CreditScoreHistory.objects.count(), before)

    def test_apply_deletes_only_noop_rows(self):
        noop = self.make_noop_row()
        real = CreditScoreHistory.objects.create(
            customer=self.customer,
            score_before=40, score_after=44,
            tier_before=ScoreTier.AVERAGE, tier_after=ScoreTier.AVERAGE,
            trigger="overdue_catchup",
        )
        # The customer_created row (score_before=None) must survive too —
        # None != 50 under an F() comparison, never matches the no-op filter.
        created_row_count_before = CreditScoreHistory.objects.filter(trigger="customer_created").count()

        call_command("cleanup_noop_credit_score_history", "--apply", verbosity=0)

        self.assertFalse(CreditScoreHistory.objects.filter(pk=noop.pk).exists())
        self.assertTrue(CreditScoreHistory.objects.filter(pk=real.pk).exists())
        self.assertEqual(
            CreditScoreHistory.objects.filter(trigger="customer_created").count(),
            created_row_count_before,
        )

    def test_idempotent(self):
        self.make_noop_row()
        call_command("cleanup_noop_credit_score_history", "--apply", verbosity=0)
        remaining = CreditScoreHistory.objects.count()
        call_command("cleanup_noop_credit_score_history", "--apply", verbosity=0)
        self.assertEqual(CreditScoreHistory.objects.count(), remaining)
