from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from rest_framework.exceptions import ValidationError

from billing.services import create_customer
from purchases.services import create_supplier
from users.models import User

from .models import CustomerOpeningBalance, SupplierOpeningBalance
from .services import create_customer_opening_balance, create_supplier_opening_balance


def make_admin(email="admin@example.com"):
    return User.objects.create_user(
        email=email, password="Adm1n-secret!", first_name="Admin",
        last_name="User", is_staff=True, is_superuser=True,
    )


class OpeningBalanceDuplicateGuardTests(TestCase):
    """
    Both opening-balance creates check-then-act on .exists() before writing,
    but the OneToOneField already makes a true duplicate impossible at the
    DB level. These tests force the .exists() check to (falsely) pass, to
    prove the IntegrityError fallback converts the DB's rejection into the
    same friendly ValidationError instead of an unhandled 500 — the actual
    race this guards against.
    """

    def setUp(self):
        self.admin = make_admin()

    def test_supplier_opening_balance_race_returns_validation_error(self):
        supplier = create_supplier(name="Ali Traders", code="ALI", user=self.admin)
        create_supplier_opening_balance(supplier_id=supplier.id, amount=Decimal("500"), user=self.admin)
        self.assertEqual(SupplierOpeningBalance.objects.filter(supplier=supplier).count(), 1)

        with patch(
            "django.db.models.query.QuerySet.exists", return_value=False,
        ):
            with self.assertRaises(ValidationError) as ctx:
                create_supplier_opening_balance(supplier_id=supplier.id, amount=Decimal("200"), user=self.admin)
        self.assertIn("supplier", ctx.exception.detail)

        # No corruption: still exactly one row, original amount untouched.
        self.assertEqual(SupplierOpeningBalance.objects.filter(supplier=supplier).count(), 1)
        self.assertEqual(SupplierOpeningBalance.objects.get(supplier=supplier).amount, Decimal("500.0000"))

    def test_customer_opening_balance_race_returns_validation_error(self):
        customer = create_customer(name="Big Mart", code="BM", address="Main St", user=self.admin)
        create_customer_opening_balance(customer_id=customer.id, amount=Decimal("300"), user=self.admin)
        self.assertEqual(CustomerOpeningBalance.objects.filter(customer=customer).count(), 1)

        with patch(
            "django.db.models.query.QuerySet.exists", return_value=False,
        ):
            with self.assertRaises(ValidationError) as ctx:
                create_customer_opening_balance(customer_id=customer.id, amount=Decimal("100"), user=self.admin)
        self.assertIn("customer", ctx.exception.detail)

        self.assertEqual(CustomerOpeningBalance.objects.filter(customer=customer).count(), 1)
        self.assertEqual(CustomerOpeningBalance.objects.get(customer=customer).amount, Decimal("300.0000"))

    def test_normal_duplicate_still_blocked_by_exists_check(self):
        supplier = create_supplier(name="Karachi Metals", code="KM", user=self.admin)
        create_supplier_opening_balance(supplier_id=supplier.id, amount=Decimal("100"), user=self.admin)

        with self.assertRaises(ValidationError):
            create_supplier_opening_balance(supplier_id=supplier.id, amount=Decimal("50"), user=self.admin)
