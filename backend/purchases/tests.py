from decimal import Decimal

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from users.models import User

from rest_framework.exceptions import ValidationError

from payment_methods.models import PaymentMethod

from .models import (
    LOW_STOCK_THRESHOLD, Category, Inventory, InventoryStatsFlow, Product,
    ProductStockMovement, PurchaseOrder, PurchaseReturn, Shelf, ShelfStock,
    StockMovementFlow, Supplier,
)
from .selectors import compute_auto_shelf_allocation
from .services import (
    accept_purchase_return, cancel_purchase_return, confirm_purchase_order,
    create_lost_inventory_record, create_purchase_order, create_purchase_return,
    create_supplier, create_supplier_payment, delete_product,
    delete_supplier_payment, mark_lost_inventory_found,
    set_purchase_item_shelf_allocations,
    set_purchase_return_item_shelf_allocations, sync_inventory,
    update_purchase_return_items,
)
from .views import (
    AutoAllocateShelvesView, DraftPurchaseOrderListView, InventoryListView,
    InventoryStatsView, LowStockInventoryListView, OutOfStockInventoryListView,
    PurchaseOrderListCreateView, PurchaseOrderPaymentSummaryView,
    SupplierPaymentListCreateView,
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


class PurchasesTestBase(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.admin = make_admin()
        self.category = Category.objects.create(name="Cat A")
        self.shelf = Shelf.objects.create(name="Shelf A")
        # Through the service so the supplier ledger exists for confirm flows.
        self.supplier = create_supplier(name="Ali Traders", code="ALI", user=self.admin)
        self.cash = PaymentMethod.objects.get_or_create(name="Cash", defaults={"balance": Decimal("1000000")})[0]

    def cash_split(self, amount):
        """[(PaymentMethod, amount)] — the single-method split most tests
        need; the account starts with a large balance so outflow tests
        never trip the insufficient-balance check incidentally."""
        return [(self.cash, Decimal(amount))]

    def make_product(self, code="P001", name="Product 1"):
        return Product.objects.create(
            name=name, code=code, category=self.category,
        )

    def make_order(self, product, quantity=10, unit_price="100"):
        return create_purchase_order(
            supplier_id=self.supplier.id,
            items=[{"product_id": product.id, "quantity": quantity, "unit_price": Decimal(unit_price)}],
            user=self.admin,
        )

    def make_confirmed_order(self, product, quantity=10, unit_price="100"):
        order = self.make_order(product, quantity=quantity, unit_price=unit_price)
        for item in order.items.all():
            set_purchase_item_shelf_allocations(
                purchase_item_id=item.id,
                allocations=[{"shelf_id": self.shelf.id, "quantity": item.quantity}],
                user=self.admin,
            )
        return confirm_purchase_order(order_id=order.id, user=self.admin)

    def allocate_return_items(self, purchase_return):
        for return_item in purchase_return.items.all():
            set_purchase_return_item_shelf_allocations(
                return_item_id=return_item.id,
                allocations=[{"shelf_id": self.shelf.id, "quantity": return_item.quantity}],
                user=self.admin,
            )

    def get(self, view, url, user=None, **params):
        request = self.factory.get(url, params)
        if user is not None:
            force_authenticate(request, user=user)
        return view(request)


class ReferenceCounterTests(PurchasesTestBase):
    def test_sequential_numbering_and_format(self):
        product = self.make_product()
        year = timezone.now().year
        o1 = self.make_order(product)
        o2 = self.make_order(product)
        self.assertEqual(o1.order_number, f"PO-{year}-0001")
        self.assertEqual(o2.order_number, f"PO-{year}-0002")

    def test_seeds_numerically_from_legacy_references_past_9999(self):
        # Old generator sorted references as TEXT, so '9999' > '10000' and
        # numbering broke permanently at 10000. The counter must seed from
        # the numeric max instead.
        year = timezone.now().year
        PurchaseOrder.objects.create(order_number=f"PO-{year}-9999", supplier=self.supplier)
        PurchaseOrder.objects.create(order_number=f"PO-{year}-10000", supplier=self.supplier)

        product = self.make_product()
        order = self.make_order(product)
        self.assertEqual(order.order_number, f"PO-{year}-10001")


class InventoryStatsFlowTests(PurchasesTestBase):
    def stats(self):
        return InventoryStatsFlow.get_instance()

    def test_confirm_purchase_creates_and_buckets_inventory(self):
        product = self.make_product()
        self.make_confirmed_order(product, quantity=10)
        flow = self.stats()
        self.assertEqual(flow.total_products, 1)
        self.assertEqual(flow.low_stock_count, 0)
        self.assertEqual(flow.out_of_stock_count, 0)

    def test_threshold_crossings_move_between_buckets(self):
        product = self.make_product()
        self.make_confirmed_order(product, quantity=10)

        # 10 → 4 : enters low stock
        create_lost_inventory_record(
            items=[{
                "product_id": product.id, "quantity": 6,
                "shelf_allocations": [{"shelf_id": self.shelf.id, "quantity": 6}],
            }], user=self.admin,
        )
        flow = self.stats()
        self.assertEqual((flow.low_stock_count, flow.out_of_stock_count), (1, 0))

        # 4 → 0 : leaves low, enters out of stock
        record = create_lost_inventory_record(
            items=[{
                "product_id": product.id, "quantity": 4,
                "shelf_allocations": [{"shelf_id": self.shelf.id, "quantity": 4}],
            }], user=self.admin,
        )
        flow = self.stats()
        self.assertEqual((flow.low_stock_count, flow.out_of_stock_count), (0, 1))

        # 0 → 2 : found again, back to low stock
        lost_item = record.items.first()
        mark_lost_inventory_found(
            lost_item_id=lost_item.id, quantity=2,
            shelf_allocations=[{"shelf_id": self.shelf.id, "quantity": 2}],
            user=self.admin,
        )
        flow = self.stats()
        self.assertEqual((flow.low_stock_count, flow.out_of_stock_count), (1, 0))

    def test_product_soft_delete_leaves_stats(self):
        product = self.make_product()
        self.make_confirmed_order(product, quantity=3)  # low stock
        delete_product(pk=product.id, user=self.admin)
        flow = self.stats()
        self.assertEqual(flow.total_products, 0)
        self.assertEqual(flow.low_stock_count, 0)
        self.assertEqual(flow.out_of_stock_count, 0)

    def test_shared_writer_used_directly_matches_billing_paths(self):
        # billing calls sync_inventory with user=None (return path) and a
        # user (confirm path) — both must maintain the counters.
        product = self.make_product()
        sync_inventory(product=product, quantity_delta=4, user=None)
        flow = self.stats()
        self.assertEqual((flow.total_products, flow.low_stock_count), (1, 1))
        sync_inventory(product=product, quantity_delta=-4, user=self.admin)
        flow = self.stats()
        self.assertEqual((flow.low_stock_count, flow.out_of_stock_count), (0, 1))

    def test_backfill_is_idempotent_and_matches_live_data(self):
        p1 = self.make_product("P001")
        p2 = self.make_product("P002", "Product 2")
        self.make_confirmed_order(p1, quantity=3)   # low
        self.make_confirmed_order(p2, quantity=20)  # ok

        # Corrupt the singleton, then rebuild twice.
        InventoryStatsFlow.get_instance()
        InventoryStatsFlow.objects.filter(pk=1).update(
            total_products=99, low_stock_count=99, out_of_stock_count=99,
        )
        call_command("backfill_inventory_stats")
        first = self.stats()
        self.assertEqual(
            (first.total_products, first.low_stock_count, first.out_of_stock_count),
            (2, 1, 0),
        )
        call_command("backfill_inventory_stats")
        second = self.stats()
        self.assertEqual(
            (second.total_products, second.low_stock_count, second.out_of_stock_count),
            (2, 1, 0),
        )


class InventoryEndpointTests(PurchasesTestBase):
    def setUp(self):
        super().setUp()
        self.normal = make_normal_user()
        p_ok  = self.make_product("P-OK", "Plenty")
        p_low = self.make_product("P-LOW", "Scarce")
        p_out = self.make_product("P-OUT", "Gone")
        sync_inventory(product=p_ok, quantity_delta=20, user=self.admin)
        sync_inventory(product=p_low, quantity_delta=LOW_STOCK_THRESHOLD, user=self.admin)
        Inventory.objects.get_or_create(product=p_out)  # row exists at 0
        # p_out was created outside the writer → rebuild counts, which is
        # exactly what backfill exists for.
        call_command("backfill_inventory_stats")

    def test_stats_endpoint_returns_singleton_counts(self):
        response = self.get(InventoryStatsView.as_view(), "/purchases/inventory/stats/", user=self.normal)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_products"], 3)
        self.assertEqual(response.data["low_stock_count"], 1)
        self.assertEqual(response.data["out_of_stock_count"], 1)

    def test_stats_endpoint_requires_authentication(self):
        response = self.get(InventoryStatsView.as_view(), "/purchases/inventory/stats/")
        self.assertEqual(response.status_code, 401)

    def test_breakdown_endpoints_return_correct_products(self):
        low = self.get(LowStockInventoryListView.as_view(), "/purchases/inventory/low-stock/", user=self.normal)
        self.assertEqual(low.status_code, 200)
        self.assertEqual([r["product"]["code"] for r in low.data["results"]], ["P-LOW"])

        out = self.get(OutOfStockInventoryListView.as_view(), "/purchases/inventory/out-of-stock/", user=self.normal)
        self.assertEqual(out.status_code, 200)
        self.assertEqual([r["product"]["code"] for r in out.data["results"]], ["P-OUT"])

    def test_inventory_list_no_longer_embeds_stats(self):
        response = self.get(InventoryListView.as_view(), "/purchases/inventory/", user=self.normal)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("stats", response.data)
        self.assertEqual(response.data["count"], 3)


class QueryCountStabilityTests(PurchasesTestBase):
    """Guards against N+1: query count must not grow with row count."""

    def count_queries(self, view, url):
        request = self.factory.get(url)
        force_authenticate(request, user=self.admin)
        with CaptureQueriesContext(connection) as ctx:
            response = view(request)
            response.render()
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries)

    def test_order_list_query_count_is_flat(self):
        view = PurchaseOrderListCreateView.as_view()
        p1 = self.make_product("P001")
        self.make_confirmed_order(p1, quantity=10)
        baseline = self.count_queries(view, "/purchases/orders/")

        for i in range(4):
            p = self.make_product(f"P10{i}", f"Product 10{i}")
            self.make_confirmed_order(p, quantity=10)
        grown = self.count_queries(view, "/purchases/orders/")
        self.assertEqual(baseline, grown)

    def test_draft_list_with_preview_query_count_is_flat(self):
        view = DraftPurchaseOrderListView.as_view()
        p1 = self.make_product("P001")
        self.make_order(p1)
        baseline = self.count_queries(view, "/purchases/orders/drafts/")

        for i in range(4):
            p = self.make_product(f"P20{i}", f"Product 20{i}")
            self.make_order(p)
        grown = self.count_queries(view, "/purchases/orders/drafts/")
        self.assertEqual(baseline, grown)

    def test_inventory_list_query_count_is_flat(self):
        view = InventoryListView.as_view()
        p1 = self.make_product("P001")
        sync_inventory(product=p1, quantity_delta=5, user=self.admin)
        baseline = self.count_queries(view, "/purchases/inventory/")

        for i in range(4):
            p = self.make_product(f"P30{i}", f"Product 30{i}")
            sync_inventory(product=p, quantity_delta=5, user=self.admin)
        grown = self.count_queries(view, "/purchases/inventory/")
        self.assertEqual(baseline, grown)


class SupplierPaymentAllocationQueryCountTests(PurchasesTestBase):
    """Phase 3's SupplierPaymentReadSerializer.allocations must not N+1 —
    one query for the whole page's allocations, not one per payment
    (architecture.md's STRICT 200ms/O(1)-per-page rule)."""

    def count_queries(self, view, url, **view_kwargs):
        request = self.factory.get(url)
        force_authenticate(request, user=self.admin)
        with CaptureQueriesContext(connection) as ctx:
            response = view(request, **view_kwargs)
            response.render()
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries)

    def test_supplier_payment_list_query_count_flat_as_payment_count_grows(self):
        product = self.make_product("SP001")
        order = self.make_confirmed_order(product, quantity=10, unit_price="50")
        create_supplier_payment(
            order_id=order.id, amount=Decimal("50"), method_allocations=self.cash_split("50"),
            payment_date=timezone.now().date(), user=self.admin,
        )
        view = SupplierPaymentListCreateView.as_view()
        url = f"/purchases/orders/{order.id}/payments/"
        baseline = self.count_queries(view, url, order_id=order.id)

        for _ in range(4):
            create_supplier_payment(
                order_id=order.id, amount=Decimal("10"), method_allocations=self.cash_split("10"),
                payment_date=timezone.now().date(), user=self.admin,
            )
        grown = self.count_queries(view, url, order_id=order.id)
        self.assertEqual(baseline, grown)

    def test_payment_summary_query_count_flat_as_payment_count_grows(self):
        product = self.make_product("SP002")
        order = self.make_confirmed_order(product, quantity=10, unit_price="50")
        create_supplier_payment(
            order_id=order.id, amount=Decimal("50"), method_allocations=self.cash_split("50"),
            payment_date=timezone.now().date(), user=self.admin,
        )
        view = PurchaseOrderPaymentSummaryView.as_view()
        url = f"/purchases/orders/{order.id}/payment-summary/"
        baseline = self.count_queries(view, url, pk=order.id)

        for _ in range(4):
            create_supplier_payment(
                order_id=order.id, amount=Decimal("10"), method_allocations=self.cash_split("10"),
                payment_date=timezone.now().date(), user=self.admin,
            )
        grown = self.count_queries(view, url, pk=order.id)
        self.assertEqual(baseline, grown)

    def _make_paid_order(self, n):
        product = self.make_product(f"SP1{n}")
        order = self.make_confirmed_order(product, quantity=10, unit_price="50")
        create_supplier_payment(
            order_id=order.id, amount=Decimal("50"), method_allocations=self.cash_split("50"),
            payment_date=timezone.now().date(), user=self.admin,
        )
        return order

    def test_all_payments_list_query_count_flat_as_payment_count_grows(self):
        # AllSupplierPaymentsView (/purchases/payments/, the global payments
        # search page) was missing the batched-allocations fix every sibling
        # payment view already had — each row was querying its own
        # PaymentAllocation set live, an N+1 as the page grows.
        from .views import AllSupplierPaymentsView

        order = self._make_paid_order(1)
        view = AllSupplierPaymentsView.as_view()
        url = "/purchases/payments/"
        baseline = self.count_queries(view, url)

        for i in range(2, 6):
            self._make_paid_order(i)
        grown = self.count_queries(view, url)
        self.assertEqual(baseline, grown)

    def test_order_number_and_supplier_name_present_without_extra_queries(self):
        # SupplierPaymentReadSerializer.order_number/supplier_name replace
        # the frontend's old per-row purchasesApi.orders.getById() fan-out
        # (GlobalPaymentsPage.jsx) — confirm they're populated and that
        # adding them didn't add a query (order__supplier was already/now
        # select_related on this queryset).
        from .views import SupplierPaymentListCreateView

        order = self._make_paid_order(9)
        view = SupplierPaymentListCreateView.as_view()
        url = f"/purchases/orders/{order.id}/payments/"
        request = self.factory.get(url)
        force_authenticate(request, user=self.admin)
        with CaptureQueriesContext(connection) as ctx:
            response = view(request, order_id=order.id)
            response.render()
        self.assertEqual(response.status_code, 200)
        row = response.data["results"][0]
        self.assertEqual(row["order_number"], order.order_number)
        self.assertEqual(row["supplier_name"], order.supplier.name)
        self.assertLessEqual(len(ctx.captured_queries), 5)


class StockMovementCounterTests(PurchasesTestBase):
    def test_counters_match_backfill_after_full_cycle(self):
        # Exercises every purchases-side counter through the real services
        # after the F()-expression rewrite, then uses the backfill command
        # (which recomputes from source records) as the consistency oracle.
        product = self.make_product()
        order = self.make_confirmed_order(product, quantity=10)          # purchased 10
        item = order.items.first()

        ret = create_purchase_return(
            order_id=order.id,
            items=[{"purchase_item_id": item.id, "quantity": 2}],
            user=self.admin,
        )
        self.allocate_return_items(ret)
        accept_purchase_return(return_id=ret.id, user=self.admin)        # returned 2

        record = create_lost_inventory_record(
            items=[{
                "product_id": product.id, "quantity": 3,
                "shelf_allocations": [{"shelf_id": self.shelf.id, "quantity": 3}],
            }], user=self.admin,
        )                                                                # lost 3
        mark_lost_inventory_found(
            lost_item_id=record.items.first().id, quantity=1,
            shelf_allocations=[{"shelf_id": self.shelf.id, "quantity": 1}],
            user=self.admin,
        )                                                                # found 1

        def snapshot():
            row = ProductStockMovement.objects.get(product_id=product.id)
            flow = StockMovementFlow.get_instance()
            return (
                (row.total_purchased, row.total_purchase_returned, row.total_lost, row.total_found),
                (flow.total_purchased, flow.total_purchase_returned, flow.total_lost, flow.total_found),
            )

        live = snapshot()
        self.assertEqual(live[0], (10, 2, 3, 1))
        self.assertEqual(live[1], (10, 2, 3, 1))

        call_command("backfill_stock_movement")
        self.assertEqual(snapshot(), live)


class OrderPayableSyncTests(PurchasesTestBase):
    def test_payment_and_credit_note_math_unchanged(self):
        product = self.make_product()
        order = self.make_confirmed_order(product, quantity=10, unit_price="50")  # net 500

        payment = create_supplier_payment(
            order_id=order.id, amount=Decimal("200"), method_allocations=self.cash_split("200"),
            payment_date=timezone.now().date(), user=self.admin,
        )
        order.refresh_from_db()
        self.assertEqual(order.total_paid, Decimal("200"))
        self.assertEqual(order.payable_outstanding, Decimal("300"))
        self.assertEqual(order.payment_status, PurchaseOrder.PaymentStatus.PARTIAL)

        item = order.items.first()
        ret = create_purchase_return(
            order_id=order.id,
            items=[{"purchase_item_id": item.id, "quantity": 2}],
            user=self.admin,
        )
        self.allocate_return_items(ret)
        accept_purchase_return(return_id=ret.id, user=self.admin)  # credit note -100
        order.refresh_from_db()
        self.assertEqual(order.payable_outstanding, Decimal("200"))
        self.assertEqual(order.payment_status, PurchaseOrder.PaymentStatus.PARTIAL)

        delete_supplier_payment(payment_id=payment.id, user=self.admin)
        order.refresh_from_db()
        self.assertEqual(order.total_paid, Decimal("0"))
        self.assertEqual(order.payable_outstanding, Decimal("400"))
        # Return credit still counts → partial, not unpaid.
        self.assertEqual(order.payment_status, PurchaseOrder.PaymentStatus.PARTIAL)


class DeleteSupplierPaymentLedgerTests(PurchasesTestBase):
    """delete_supplier_payment must remove the linked SupplierLedgerEntry —
    found 2026-08-31 (SPY-2026-0013): a soft-deleted payment kept its debit
    entry alive forever, still showing as outstanding on the ledger."""

    def test_deleting_payment_removes_ledger_entry_and_recalculates_balance(self):
        from ledger.models import SupplierLedgerEntry, SupplierLedgerSnapshot

        product = self.make_product()
        order = self.make_confirmed_order(product, quantity=10, unit_price="50")  # net 500
        payment = create_supplier_payment(
            order_id=order.id, amount=Decimal("200"), method_allocations=self.cash_split("200"),
            payment_date=timezone.now().date(), user=self.admin,
        )
        ledger = self.supplier.ledger
        year_month = timezone.now().date().strftime("%Y-%m")
        self.assertTrue(SupplierLedgerEntry.objects.filter(supplier_payment=payment).exists())
        self.assertEqual(
            SupplierLedgerSnapshot.objects.get(ledger=ledger, year_month=year_month).closing_balance,
            Decimal("300"),
        )

        delete_supplier_payment(payment_id=payment.id, user=self.admin)

        self.assertFalse(SupplierLedgerEntry.objects.filter(supplier_payment=payment).exists())
        self.assertEqual(
            SupplierLedgerSnapshot.objects.get(ledger=ledger, year_month=year_month).closing_balance,
            Decimal("500"),
        )


class PurchaseReturnRemainingQuantityTests(PurchasesTestBase):
    """
    Regression coverage for the accept_purchase_return bug fixed 2026-08-09:
    the FIFO batch's remaining_quantity used to INCREASE on an accepted
    purchase return while Inventory.quantity correctly decreased, silently
    diverging the two and inflating the Inventory Valuation Report's
    avg_unit_cost (which divides a batch-summed total by Inventory.quantity).
    """

    def test_remaining_quantity_moves_with_inventory_on_accepted_return(self):
        product = self.make_product()
        order = self.make_confirmed_order(product, quantity=10, unit_price="100")
        item = order.items.first()
        self.assertEqual(item.remaining_quantity, 10)
        self.assertEqual(Inventory.objects.get(product=product).quantity, 10)

        ret = create_purchase_return(
            order_id=order.id,
            items=[{"purchase_item_id": item.id, "quantity": 4}],
            user=self.admin,
        )
        self.allocate_return_items(ret)
        accept_purchase_return(return_id=ret.id, user=self.admin)

        item.refresh_from_db()
        inventory = Inventory.objects.get(product=product)
        # The bug made this 14 (10 + 4) instead of 6 (10 - 4).
        self.assertEqual(item.remaining_quantity, 6)
        self.assertEqual(inventory.quantity, 6)
        # The invariant the valuation report's avg_unit_cost depends on:
        # sum(remaining_quantity across batches) == Inventory.quantity.
        self.assertEqual(item.remaining_quantity, inventory.quantity)

    def test_cannot_return_more_than_currently_in_stock(self):
        """
        Reproduces the exact scenario reported: return a batch, sell what's
        left, then try to return more of that same batch than physically
        remains. Must be rejected, not silently corrupt remaining_quantity.
        """
        product = self.make_product()
        order = self.make_confirmed_order(product, quantity=10, unit_price="100")
        item = order.items.first()

        # Sell 8 of the 10 (drops remaining_quantity to 2) via a confirmed
        # invoice — mirrors how stock actually leaves in production.
        from billing.services import confirm_invoice, create_customer, create_invoice, set_invoice_item_shelf_allocations
        from rates.services import create_rate
        create_rate(product_id=product.id, selling_price=Decimal("150"), user=self.admin)
        customer = create_customer(name="Cust A", code="CUSTA", address="x", user=self.admin)
        invoice = create_invoice(
            customer_id=customer.id,
            items=[{"product_id": product.id, "quantity": 8}],
            user=self.admin,
        )
        for inv_item in invoice.items.all():
            set_invoice_item_shelf_allocations(
                invoice_item_id=inv_item.id,
                allocations=[{"shelf_id": self.shelf.id, "quantity": inv_item.quantity}],
                user=self.admin,
            )
        confirm_invoice(invoice_id=invoice.id, user=self.admin)

        item.refresh_from_db()
        self.assertEqual(item.remaining_quantity, 2)
        # returnable_quantity must reflect physical stock (2), not just
        # quantity - returned_quantity (10) — this is the validation gap
        # fixed alongside the remaining_quantity direction bug.
        self.assertEqual(item.returnable_quantity, 2)

        with self.assertRaises(ValidationError):
            create_purchase_return(
                order_id=order.id,
                items=[{"purchase_item_id": item.id, "quantity": 5}],
                user=self.admin,
            )


class PurchaseReturnEditCancelTests(PurchasesTestBase):
    """
    A pending return has zero side effects until accepted, so editing or
    cancelling one should be free of any inventory/payable consequence,
    and should never block creating further returns against the same
    order — whether the prior return was cancelled or already accepted.
    """

    def test_edit_replaces_items_and_resets_allocations(self):
        product = self.make_product()
        order = self.make_confirmed_order(product, quantity=10, unit_price="100")
        item = order.items.first()

        ret = create_purchase_return(
            order_id=order.id,
            items=[{"purchase_item_id": item.id, "quantity": 3}],
            user=self.admin,
        )
        self.allocate_return_items(ret)
        return_item = ret.items.first()
        self.assertEqual(return_item.allocated_quantity, 3)

        updated = update_purchase_return_items(
            return_id=ret.id,
            items=[{"purchase_item_id": item.id, "quantity": 5}],
            note="revised",
            user=self.admin,
        )

        self.assertEqual(updated.items.count(), 1)
        new_item = updated.items.first()
        self.assertEqual(new_item.quantity, 5)
        self.assertEqual(new_item.allocated_quantity, 0)  # old allocations cascaded away
        self.assertEqual(updated.note, "revised")

    def test_edit_revalidates_against_current_returnable_quantity(self):
        product = self.make_product()
        order = self.make_confirmed_order(product, quantity=10, unit_price="100")
        item = order.items.first()

        ret = create_purchase_return(
            order_id=order.id,
            items=[{"purchase_item_id": item.id, "quantity": 3}],
            user=self.admin,
        )

        with self.assertRaises(ValidationError):
            update_purchase_return_items(
                return_id=ret.id,
                items=[{"purchase_item_id": item.id, "quantity": 999}],
                user=self.admin,
            )

    def test_edit_blocked_once_accepted(self):
        product = self.make_product()
        order = self.make_confirmed_order(product, quantity=10, unit_price="100")
        item = order.items.first()
        ret = create_purchase_return(
            order_id=order.id,
            items=[{"purchase_item_id": item.id, "quantity": 3}],
            user=self.admin,
        )
        self.allocate_return_items(ret)
        accept_purchase_return(return_id=ret.id, user=self.admin)

        with self.assertRaises(ValidationError):
            update_purchase_return_items(
                return_id=ret.id,
                items=[{"purchase_item_id": item.id, "quantity": 1}],
                user=self.admin,
            )

    def test_cancel_soft_deletes_and_disappears_from_list(self):
        product = self.make_product()
        order = self.make_confirmed_order(product, quantity=10, unit_price="100")
        item = order.items.first()
        ret = create_purchase_return(
            order_id=order.id,
            items=[{"purchase_item_id": item.id, "quantity": 3}],
            user=self.admin,
        )

        cancel_purchase_return(return_id=ret.id, user=self.admin)

        self.assertFalse(PurchaseReturn.objects.filter(id=ret.id).exists())
        self.assertTrue(PurchaseReturn.all_objects.get(id=ret.id).is_deleted)
        # Item, order, and inventory are all untouched — a pending return
        # never had any side effect to reverse.
        item.refresh_from_db()
        self.assertEqual(item.remaining_quantity, 10)
        self.assertEqual(Inventory.objects.get(product=product).quantity, 10)

    def test_cancel_blocked_once_accepted(self):
        product = self.make_product()
        order = self.make_confirmed_order(product, quantity=10, unit_price="100")
        item = order.items.first()
        ret = create_purchase_return(
            order_id=order.id,
            items=[{"purchase_item_id": item.id, "quantity": 3}],
            user=self.admin,
        )
        self.allocate_return_items(ret)
        accept_purchase_return(return_id=ret.id, user=self.admin)

        with self.assertRaises(ValidationError):
            cancel_purchase_return(return_id=ret.id, user=self.admin)

    def test_can_create_another_return_after_cancelling(self):
        product = self.make_product()
        order = self.make_confirmed_order(product, quantity=10, unit_price="100")
        item = order.items.first()

        ret_a = create_purchase_return(
            order_id=order.id,
            items=[{"purchase_item_id": item.id, "quantity": 4}],
            user=self.admin,
        )
        cancel_purchase_return(return_id=ret_a.id, user=self.admin)

        # returnable_quantity is untouched by the cancelled return, so the
        # full 4 (in fact the full 10) is still available.
        ret_b = create_purchase_return(
            order_id=order.id,
            items=[{"purchase_item_id": item.id, "quantity": 4}],
            user=self.admin,
        )
        self.assertEqual(ret_b.items.first().quantity, 4)

    def test_can_create_another_return_after_accepting(self):
        product = self.make_product()
        order = self.make_confirmed_order(product, quantity=10, unit_price="100")
        item = order.items.first()

        ret_a = create_purchase_return(
            order_id=order.id,
            items=[{"purchase_item_id": item.id, "quantity": 4}],
            user=self.admin,
        )
        self.allocate_return_items(ret_a)
        accept_purchase_return(return_id=ret_a.id, user=self.admin)

        item.refresh_from_db()
        self.assertEqual(item.returnable_quantity, 6)

        ret_b = create_purchase_return(
            order_id=order.id,
            items=[{"purchase_item_id": item.id, "quantity": 6}],
            user=self.admin,
        )
        self.assertEqual(ret_b.items.first().quantity, 6)

    def test_non_admin_gets_403_on_update_and_cancel(self):
        from .views import PurchaseReturnRetrieveUpdateDestroyView

        normal = make_normal_user()
        product = self.make_product()
        order = self.make_confirmed_order(product, quantity=10, unit_price="100")
        item = order.items.first()
        ret = create_purchase_return(
            order_id=order.id,
            items=[{"purchase_item_id": item.id, "quantity": 3}],
            user=self.admin,
        )

        view = PurchaseReturnRetrieveUpdateDestroyView.as_view()

        patch_request = self.factory.patch(
            f"/purchases/returns/{ret.id}/",
            {"items": [{"purchase_item_id": item.id, "quantity": 1}]},
            format="json",
        )
        force_authenticate(patch_request, user=normal)
        patch_response = view(patch_request, pk=ret.id)
        self.assertEqual(patch_response.status_code, 403)

        delete_request = self.factory.delete(f"/purchases/returns/{ret.id}/")
        force_authenticate(delete_request, user=normal)
        delete_response = view(delete_request, pk=ret.id)
        self.assertEqual(delete_response.status_code, 403)

    def test_update_and_cancel_query_counts(self):
        product = self.make_product()
        order = self.make_confirmed_order(product, quantity=10, unit_price="100")
        item = order.items.first()
        ret = create_purchase_return(
            order_id=order.id,
            items=[{"purchase_item_id": item.id, "quantity": 3}],
            user=self.admin,
        )

        from .views import PurchaseReturnRetrieveUpdateDestroyView
        view = PurchaseReturnRetrieveUpdateDestroyView.as_view()

        with CaptureQueriesContext(connection) as ctx:
            patch_request = self.factory.patch(
                f"/purchases/returns/{ret.id}/",
                {"items": [{"purchase_item_id": item.id, "quantity": 2}]},
                format="json",
            )
            force_authenticate(patch_request, user=self.admin)
            response = view(patch_request, pk=ret.id)
            self.assertEqual(response.status_code, 200)
        # +1 from activity_log's is_tracking_enabled() check, added when the
        # audit-log on/off toggle shipped — one fixed extra SELECT per
        # tracked write (PurchaseReturn), not a scaling N+1.
        self.assertLessEqual(len(ctx.captured_queries), 21)

        with CaptureQueriesContext(connection) as ctx:
            delete_request = self.factory.delete(f"/purchases/returns/{ret.id}/")
            force_authenticate(delete_request, user=self.admin)
            response = view(delete_request, pk=ret.id)
            self.assertEqual(response.status_code, 200)
        self.assertLess(len(ctx.captured_queries), 12)


class LostStockValidationTests(PurchasesTestBase):
    def test_validation_boundary_unchanged(self):
        product = self.make_product()
        self.make_confirmed_order(product, quantity=10)

        # Exactly the available quantity passes…
        create_lost_inventory_record(
            items=[{
                "product_id": product.id, "quantity": 10,
                "shelf_allocations": [{"shelf_id": self.shelf.id, "quantity": 10}],
            }], user=self.admin,
        )
        # …one more unit is rejected with the same validation error.
        with self.assertRaises(ValidationError):
            create_lost_inventory_record(
                items=[{
                    "product_id": product.id, "quantity": 1,
                    "shelf_allocations": [{"shelf_id": self.shelf.id, "quantity": 1}],
                }], user=self.admin,
            )


class OrderDateFilterTests(PurchasesTestBase):
    def setUp(self):
        super().setUp()
        product = self.make_product()
        self.o_old = self.make_order(product)
        p2 = self.make_product("P002", "Product 2")
        self.o_new = self.make_order(p2)
        # Backdate the first order (created_at is auto_now_add, so set via update).
        PurchaseOrder.objects.filter(pk=self.o_old.pk).update(
            created_at=timezone.now() - timezone.timedelta(days=10),
        )

    def order_numbers(self, **params):
        response = self.get(
            PurchaseOrderListCreateView.as_view(), "/purchases/orders/",
            user=self.admin, **params,
        )
        self.assertEqual(response.status_code, 200)
        return {r["order_number"] for r in response.data["results"]}

    def test_date_from_filter(self):
        today = timezone.localtime(timezone.now()).date().isoformat()
        self.assertEqual(self.order_numbers(date_from=today), {self.o_new.order_number})

    def test_date_to_filter(self):
        cutoff = (timezone.localtime(timezone.now()).date() - timezone.timedelta(days=5)).isoformat()
        self.assertEqual(self.order_numbers(date_to=cutoff), {self.o_old.order_number})

    def test_exact_date_filter(self):
        today = timezone.localtime(timezone.now()).date().isoformat()
        self.assertEqual(self.order_numbers(date=today), {self.o_new.order_number})


class AutoShelfAllocationSelectorTests(PurchasesTestBase):
    """
    Covers compute_auto_shelf_allocation — the single shared implementation
    behind every consumption allocation context (invoice items, purchase
    returns to supplier, lost inventory).
    """
    def setUp(self):
        super().setUp()
        self.product = self.make_product()
        self.shelf_b = Shelf.objects.create(name="B - Large Stock")
        self.shelf_c = Shelf.objects.create(name="C - Empty")
        ShelfStock.objects.create(shelf=self.shelf, product=self.product, quantity=10)
        ShelfStock.objects.create(shelf=self.shelf_b, product=self.product, quantity=50)
        ShelfStock.objects.create(shelf=self.shelf_c, product=self.product, quantity=0)

    def test_fills_largest_quantity_shelf_first(self):
        result = compute_auto_shelf_allocation(product_id=self.product.id, quantity=15)
        self.assertEqual(result["allocations"][0]["shelf_id"], self.shelf_b.id)
        self.assertEqual(result["allocations"][0]["quantity"], 15)
        self.assertEqual(result["shortfall"], 0)

    def test_spills_over_to_second_shelf_when_first_isnt_enough(self):
        result = compute_auto_shelf_allocation(product_id=self.product.id, quantity=55)
        totals = {a["shelf_id"]: a["quantity"] for a in result["allocations"]}
        self.assertEqual(totals[self.shelf_b.id], 50)
        self.assertEqual(totals[self.shelf.id], 5)
        self.assertEqual(result["shortfall"], 0)

    def test_reports_shortfall_when_total_stock_insufficient(self):
        result = compute_auto_shelf_allocation(product_id=self.product.id, quantity=1000)
        allocated = sum(a["quantity"] for a in result["allocations"])
        self.assertEqual(allocated, 60)  # everything available across both stocked shelves
        self.assertEqual(result["shortfall"], 940)

    def test_excludes_shelves_the_user_already_manually_picked(self):
        # User already has a manual row on shelf_b — auto-allocate must not
        # touch it, only fill the remaining gap from other shelves.
        result = compute_auto_shelf_allocation(
            product_id=self.product.id, quantity=8, exclude_shelf_ids=[self.shelf_b.id],
        )
        self.assertEqual(len(result["allocations"]), 1)
        self.assertEqual(result["allocations"][0]["shelf_id"], self.shelf.id)
        self.assertEqual(result["allocations"][0]["quantity"], 8)

    def test_empty_shelf_never_offered(self):
        result = compute_auto_shelf_allocation(product_id=self.product.id, quantity=1000)
        shelf_ids = {a["shelf_id"] for a in result["allocations"]}
        self.assertNotIn(self.shelf_c.id, shelf_ids)

    def test_soft_deleted_shelf_never_offered(self):
        self.shelf_b.is_deleted = True
        self.shelf_b.save(update_fields=["is_deleted"])
        result = compute_auto_shelf_allocation(product_id=self.product.id, quantity=5)
        shelf_ids = {a["shelf_id"] for a in result["allocations"]}
        self.assertNotIn(self.shelf_b.id, shelf_ids)


class AutoAllocateShelvesViewTests(PurchasesTestBase):
    def setUp(self):
        super().setUp()
        self.product = self.make_product()
        ShelfStock.objects.create(shelf=self.shelf, product=self.product, quantity=20)

    def test_authenticated_user_gets_allocation(self):
        request = self.factory.post(
            "/api/purchases/shelves/auto-allocate/",
            {"product_id": self.product.id, "quantity": 5}, format="json",
        )
        force_authenticate(request, user=self.admin)
        response = AutoAllocateShelvesView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["allocations"][0]["shelf_id"], self.shelf.id)
        self.assertEqual(response.data["allocations"][0]["quantity"], 5)
        self.assertEqual(response.data["shortfall"], 0)

    def test_anonymous_forbidden(self):
        request = self.factory.post(
            "/api/purchases/shelves/auto-allocate/",
            {"product_id": self.product.id, "quantity": 5}, format="json",
        )
        response = AutoAllocateShelvesView.as_view()(request)
        self.assertEqual(response.status_code, 401)

    def test_zero_quantity_rejected(self):
        request = self.factory.post(
            "/api/purchases/shelves/auto-allocate/",
            {"product_id": self.product.id, "quantity": 0}, format="json",
        )
        force_authenticate(request, user=self.admin)
        response = AutoAllocateShelvesView.as_view()(request)
        self.assertEqual(response.status_code, 400)
