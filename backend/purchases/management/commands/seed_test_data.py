import random
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone
from rest_framework.exceptions import ValidationError


class Command(BaseCommand):
    help = (
        "TEST DATA ONLY — seeds ~3 months of fake-but-realistic confirmed "
        "purchase orders and invoices, using ONLY existing products/"
        "suppliers/customers/rates (creates none of those). ~80% of orders "
        "and ~80% of invoices get a full payment recorded, the rest stay "
        "unpaid. Everything goes through the real service layer (not raw "
        "ORM writes) so CashFlow/TaxFlow/StockMovementFlow/ledger all stay "
        "consistent. Intended for testing Monthly Profit / ownership "
        "distribution against a non-production database."
    )

    def handle(self, *args, **options):
        from billing.models import Customer
        from billing.services import confirm_invoice, create_invoice, create_payment
        from payment_methods.models import PaymentMethod
        from purchases.models import Product, Supplier
        from purchases.services import confirm_purchase_order, create_purchase_order, create_supplier_payment
        from users.models import User

        # The real accounts system replaced free-text methods — every
        # payment now needs a PaymentMethod split. Seed data keeps it
        # simple and puts everything on Cash (get_or_create: safe whether
        # or not seed_and_backfill_payment_methods has already run). Seeded
        # with a large starting balance since this script pays suppliers
        # before it ever records an offsetting customer inflow — a fresh
        # Cash row at 0 would fail the very first supplier payment's
        # insufficient-balance check.
        cash_method, _ = PaymentMethod.objects.get_or_create(
            name="Cash", defaults={"is_protected": True, "balance": Decimal("10000000")},
        )

        user = User.objects.filter(is_superuser=True).first() or User.objects.first()
        if not user:
            self.stderr.write(self.style.ERROR("No user exists — aborting."))
            return

        suppliers = list(Supplier.objects.filter(is_deleted=False).exclude(code="SYS-OPENING"))
        products  = list(Product.objects.filter(is_deleted=False))
        customers = list(Customer.objects.filter(is_deleted=False))

        if not suppliers or not products or not customers:
            self.stderr.write(self.style.ERROR(
                "Need at least 1 existing supplier, 1 product, and 1 customer to seed data."
            ))
            return

        today = timezone.localdate()
        start = today - timedelta(days=90)
        self.stdout.write(f"Seeding fake orders/invoices from {start} to {today} "
                           f"({len(suppliers)} suppliers, {len(products)} products, {len(customers)} customers)...\n")

        orders_created = invoices_created = 0
        orders_paid = invoices_paid = 0
        invoices_skipped = 0

        for month_start, month_end in self._months(start, today):
            self.stdout.write(f"  {month_start} -> {month_end}")

            num_orders = random.randint(6, 10)
            for _ in range(num_orders):
                order_date = self._random_date(month_start, month_end)
                order = self._create_and_confirm_order(
                    suppliers=suppliers, products=products, user=user, order_date=order_date,
                    create_purchase_order=create_purchase_order, confirm_purchase_order=confirm_purchase_order,
                )
                orders_created += 1

                if random.random() < 0.8 and order.payable_outstanding > 0:
                    create_supplier_payment(
                        order_id=order.id,
                        amount=order.payable_outstanding,
                        method_allocations=[(cash_method, order.payable_outstanding)],
                        payment_date=self._random_date(order_date, today),
                        note="Seed test data payment",
                        user=user,
                    )
                    orders_paid += 1

            num_invoices = random.randint(10, 18)
            for _ in range(num_invoices):
                invoice_date = self._random_date(month_start, month_end)
                try:
                    invoice = self._create_and_confirm_invoice(
                        customers=customers, products=products, user=user, invoice_date=invoice_date,
                        create_invoice=create_invoice, confirm_invoice=confirm_invoice,
                    )
                except ValidationError:
                    # Random product/quantity combo exceeded currently available FIFO
                    # stock (e.g. a lean month) — skip this one and move on.
                    invoices_skipped += 1
                    continue

                invoices_created += 1

                if random.random() < 0.8 and invoice.credit_outstanding > 0:
                    create_payment(
                        invoice_id=invoice.id,
                        amount=invoice.credit_outstanding,
                        method_allocations=[(cash_method, invoice.credit_outstanding)],
                        payment_date=self._random_date(invoice_date, today),
                        note="Seed test data payment",
                        user=user,
                    )
                    invoices_paid += 1

        self.stdout.write(self.style.SUCCESS(
            f"\nDone.\n"
            f"  Purchase orders : {orders_created} confirmed, {orders_paid} paid\n"
            f"  Invoices        : {invoices_created} confirmed, {invoices_paid} paid "
            f"({invoices_skipped} skipped - insufficient stock)\n"
            f"Run the profits catch-up (GET /api/system/catch-up/, or just open the "
            f"Monthly Profits page) to finalize the now-closed months."
        ))

    # -----------------------------------------------------------------
    # Order/invoice construction — one call each, backdates confirmed_at
    # immediately after confirming so later FIFO reads (order__confirmed_at
    # ascending) see the INTENDED chronology, not real wall-clock time.
    # -----------------------------------------------------------------

    def _create_and_confirm_order(self, *, suppliers, products, user, order_date,
                                   create_purchase_order, confirm_purchase_order):
        supplier = random.choice(suppliers)
        chosen = random.sample(products, k=random.randint(1, min(4, len(products))))
        items = []
        for product in chosen:
            selling_price = product.rate.selling_price if hasattr(product, "rate") else Decimal("100")
            unit_price = (selling_price * Decimal(str(round(random.uniform(0.55, 0.75), 2)))).quantize(Decimal("0.01"))
            items.append({
                "product_id": product.id,
                "quantity"  : random.randint(20, 200),
                "unit_price": unit_price,
                "gst"       : Decimal("17"),
                "wht"       : Decimal("1"),
            })

        order = create_purchase_order(supplier_id=supplier.id, items=items, user=user)
        order = confirm_purchase_order(order_id=order.id, user=user)
        order.confirmed_at = self._random_datetime(order_date)
        order.save(update_fields=["confirmed_at"])
        return order

    def _create_and_confirm_invoice(self, *, customers, products, user, invoice_date,
                                     create_invoice, confirm_invoice):
        customer = random.choice(customers)
        chosen = random.sample(products, k=random.randint(1, min(3, len(products))))
        items = [
            {
                "product_id": product.id,
                "quantity"  : random.randint(1, 10),
                "gst"       : Decimal("17"),
                "wht"       : Decimal("1"),
            }
            for product in chosen
        ]

        invoice = create_invoice(customer_id=customer.id, items=items, user=user)
        invoice = confirm_invoice(invoice_id=invoice.id, user=user)
        invoice.confirmed_at = self._random_datetime(invoice_date)
        invoice.save(update_fields=["confirmed_at"])
        return invoice

    # -----------------------------------------------------------------
    # Date helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _months(start, end):
        """Yields (month_start, month_end) pairs covering [start, end], clamped at both ends."""
        cursor = start.replace(day=1)
        while cursor <= end:
            next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
            month_end = min(end, next_month - timedelta(days=1))
            month_start = max(start, cursor)
            yield month_start, month_end
            cursor = next_month

    @staticmethod
    def _random_date(start, end):
        if start > end:
            start, end = end, start
        delta_days = (end - start).days
        return start + timedelta(days=random.randint(0, delta_days)) if delta_days > 0 else start

    @staticmethod
    def _random_datetime(date):
        naive = datetime.combine(date, time(hour=random.randint(8, 18), minute=random.randint(0, 59)))
        return timezone.make_aware(naive) if timezone.is_naive(naive) else naive
