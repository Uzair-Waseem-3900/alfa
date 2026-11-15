"""Customer / product resolution: the rules that decide when the assistant may create without asking."""
from decimal import Decimal

from django.test import TestCase

from billing.models import Customer
from billing.services import create_customer, create_invoice

from ai_agent.selectors import invoicing as sel

from .invoice_fixtures import InvoiceWorld


class CustomerResolutionTests(InvoiceWorld, TestCase):
    def setUp(self):
        self.build_world()                                  # "Sultan Kitab Ghar" / SKG
        create_customer(name="Ali", code="ALI-1", address="a", user=self.admin)
        create_customer(name="Ali Traders", code="ALI-2", address="a", user=self.admin)
        create_customer(name="Waseem Stationers", code="WS", address="a", user=self.admin)
        create_customer(name="Waseem Books", code="WB", address="a", user=self.admin)

    def test_unique_by_name(self):
        unique, candidates = sel.find_customers(search="sultan", code=None)
        self.assertEqual(unique.code, "SKG")
        self.assertEqual(len(candidates), 1)

    def test_a_code_is_exact_even_when_it_is_a_prefix_of_others(self):
        unique, _ = sel.find_customers(search=None, code="ali-1")          # case-insensitive
        self.assertEqual(unique.name, "Ali")

    def test_an_exact_name_wins_over_longer_names_containing_it(self):
        unique, candidates = sel.find_customers(search="ali", code=None)   # "Ali" and "Ali Traders" both contain it
        self.assertEqual(unique.name, "Ali")
        self.assertGreaterEqual(len(candidates), 2)

    def test_several_matches_means_no_unique_choice(self):
        unique, candidates = sel.find_customers(search="waseem", code=None)
        self.assertIsNone(unique)
        self.assertEqual({c.code for c in candidates}, {"WS", "WB"})

    def test_no_match(self):
        unique, candidates = sel.find_customers(search="nobody", code=None)
        self.assertEqual((unique, candidates), (None, []))

    def test_a_partial_code_is_not_treated_as_exact(self):
        unique, _ = sel.find_customers(search=None, code="ALI")            # prefix of ALI-1 and ALI-2
        self.assertIsNone(unique)

    def test_a_soft_deleted_customer_is_never_offered(self):
        Customer.objects.filter(code="WS").update(is_deleted=True)
        unique, candidates = sel.find_customers(search="waseem", code=None)
        self.assertEqual(unique.code, "WB")

    def test_customer_standing_for_a_customer_who_owes_nothing(self):
        self.assertEqual(sel.customer_standing(self.customer.id)["total_credit_outstanding"], Decimal("0"))


class ProductResolutionTests(InvoiceWorld, TestCase):
    def setUp(self):
        self.build_world()
        self.pen_blue = self.stocked_product("PEN-B", "Pen Blue", stock=30, selling_price="100")
        self.stocked_product("PEN-R", "Pen Red", stock=10, selling_price="110")
        self.notebook = self.stocked_product("NB", "Notebook", stock=5, selling_price="200")

    def test_unique_by_name_and_by_code(self):
        self.assertEqual(sel.find_products(search="notebook", code=None)[0].code, "NB")
        self.assertEqual(sel.find_products(search=None, code="pen-r")[0].name, "Pen Red")

    def test_several_matches(self):
        unique, candidates = sel.find_products(search="pen", code=None)
        self.assertIsNone(unique)
        self.assertEqual({p.code for p in candidates}, {"PEN-B", "PEN-R"})

    def test_none(self):
        self.assertEqual(sel.find_products(search="zzz", code=None), (None, []))

    def test_availability_counts_stock_other_drafts_have_reserved(self):
        info = sel.product_availability(self.notebook)
        self.assertEqual((info["price"], info["physical"], info["reserved"], info["available"]),
                         (Decimal("200"), 5, 0, 5))
        create_invoice(customer_id=self.customer.id, items=[{"product_id": self.notebook.id, "quantity": 3}], user=self.admin)
        info = sel.product_availability(self.notebook)
        self.assertEqual((info["physical"], info["reserved"], info["available"]), (5, 3, 2))

    def test_an_unpriced_product_reports_no_price(self):
        self.notebook.rate.delete()
        fresh = type(self.notebook).objects.get(pk=self.notebook.pk)
        self.assertIsNone(sel.product_availability(fresh)["price"])
