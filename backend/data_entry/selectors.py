from .models import (
    CustomerOpeningBalance, OpeningCashEntry, SupplierOpeningBalance,
)


# ---------------------------------------------------------------------------
# Audit list selectors (superuser GET endpoints)
# ---------------------------------------------------------------------------

def get_all_supplier_opening_balances():
    return SupplierOpeningBalance.objects.select_related(
        "supplier", "purchase_order", "created_by",
    ).order_by("-created_at")


def get_all_customer_opening_balances():
    return CustomerOpeningBalance.objects.select_related(
        "customer", "invoice", "created_by",
    ).order_by("-created_at")


def get_all_opening_cash_entries():
    return OpeningCashEntry.objects.select_related("added_by").order_by("-added_at")


def get_all_opening_stock_orders():
    from purchases.models import PurchaseOrder
    return (
        PurchaseOrder.objects
        .filter(is_data_entry=True, supplier__code="SYS-OPENING", is_deleted=False)
        .select_related("supplier")
        .prefetch_related("items__product")
        .order_by("-created_at")
    )


def get_all_opening_investor_investments():
    from cash_management.models import InvestorTransaction
    return (
        InvestorTransaction.objects
        .filter(is_data_entry=True, is_deleted=False)
        .select_related("investor", "created_by")
        .order_by("-created_at")
    )
