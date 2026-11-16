"""Shared fixtures for the invoice tests: a customer, stocked + priced products, a chat and a run."""
from decimal import Decimal

from billing.services import create_customer, set_invoice_item_shelf_allocations
from payment_methods.models import PaymentMethod
from purchases.models import Category, Product, Shelf
from purchases.services import (
    confirm_purchase_order, create_purchase_order, create_supplier, set_purchase_item_shelf_allocations,
)
from rates.services import create_rate

from ai_agent.models import Chat, ChatRun
from ai_agent.schemas.context import AgentContext, LookupLog

from .helpers import make_admin


class InvoiceWorld:
    """Mixin: call build_world() from setUp (TestCase or TransactionTestCase)."""

    def build_world(self):
        self.admin = make_admin()
        self.category = Category.objects.create(name="Cat A")
        self.shelf = Shelf.objects.create(name="Shelf A")
        self.supplier = create_supplier(name="Paper Mill", code="PM", user=self.admin)
        self.customer = create_customer(name="Sultan Kitab Ghar", code="SKG", address="Main St", user=self.admin)
        self.cash = PaymentMethod.objects.get_or_create(name="Cash", defaults={"balance": Decimal("1000000")})[0]
        self.chat = Chat.objects.create(user=self.admin)
        self.run = ChatRun.objects.create(chat=self.chat, user_message="make an invoice", status="running")

    def new_run(self):
        """Another request in the same chat. Created as FINISHED: a chat may have only ONE active run
        (a DB constraint), and these tests only need a distinct run id for the idempotency key."""
        return ChatRun.objects.create(chat=self.chat, user_message="another request", status="done")

    def stocked_product(self, code="P001", name="Pen Blue", *, stock=100, unit_cost="50", selling_price="100"):
        product = Product.objects.create(name=name, code=code, category=self.category)
        create_rate(product_id=product.id, selling_price=Decimal(selling_price), user=self.admin)
        order = create_purchase_order(
            supplier_id=self.supplier.id,
            items=[{"product_id": product.id, "quantity": stock, "unit_price": Decimal(unit_cost)}],
            user=self.admin,
        )
        for item in order.items.all():
            set_purchase_item_shelf_allocations(
                purchase_item_id=item.id,
                allocations=[{"shelf_id": self.shelf.id, "quantity": item.quantity}], user=self.admin,
            )
        confirm_purchase_order(order_id=order.id, user=self.admin)
        return product

    def allocate_invoice(self, invoice):
        for item in invoice.items.all():
            set_invoice_item_shelf_allocations(
                invoice_item_id=item.id,
                allocations=[{"shelf_id": self.shelf.id, "quantity": item.quantity}], user=self.admin,
            )

    def agent_context(self, run=None, *, user=None, looked_up=True, **extra):
        """AgentContext for tool-path tests. By default the model 'has already looked up' every customer and
        product in the world (what find_* would have recorded); looked_up=False gives the empty log."""
        from billing.models import Customer
        from purchases.models import Product
        run = run or self.run
        lookups = LookupLog(
            customers=set(Customer.objects.values_list("id", flat=True)) if looked_up else set(),
            products=set(Product.objects.values_list("id", flat=True)) if looked_up else set(),
        )
        return AgentContext(user=user or self.admin, run_id=str(run.id), chat_id=str(self.chat.id), lookups=lookups, **extra)

    def ctx_kwargs(self, run=None):
        run = run or self.run
        return {"user": self.admin, "run_id": str(run.id), "chat_id": str(self.chat.id)}
