from django.contrib import admin

from .models import (
    CustomerLedger, CustomerLedgerEntry, CustomerLedgerSnapshot,
    SavedCustomerLedgerPDF, SavedLedgerPDF,
    SupplierLedger, SupplierLedgerEntry, SupplierLedgerSnapshot,
)


@admin.register(SupplierLedger)
class SupplierLedgerAdmin(admin.ModelAdmin):
    list_display  = ["supplier_name", "supplier_code", "created_at"]
    search_fields = ["supplier_name", "supplier_code"]
    readonly_fields = ["supplier", "supplier_name", "supplier_code", "created_at"]

    def has_add_permission(self, request):
        return False  # created automatically with supplier

    def has_delete_permission(self, request, obj=None):
        return False  # ledgers are permanent


@admin.register(SupplierLedgerEntry)
class SupplierLedgerEntryAdmin(admin.ModelAdmin):
    list_display  = ["ledger", "date", "entry_type", "reference", "debit", "credit"]
    list_filter   = ["entry_type"]
    search_fields = ["reference", "details", "ledger__supplier_name"]
    readonly_fields = [
        "ledger", "entry_type", "date", "details", "reference",
        "debit", "credit", "created_by", "created_at",
        "purchase_order", "supplier_payment", "purchase_return",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SupplierLedgerSnapshot)
class SupplierLedgerSnapshotAdmin(admin.ModelAdmin):
    list_display  = ["ledger", "year_month", "closing_balance", "updated_at"]
    list_filter   = ["year_month"]
    search_fields = ["ledger__supplier_name", "ledger__supplier_code"]
    readonly_fields = ["ledger", "year_month", "closing_balance", "updated_at"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SavedLedgerPDF)
class SavedLedgerPDFAdmin(admin.ModelAdmin):
    list_display  = ["ledger", "file_name", "date_from", "date_to", "saved_by", "is_deleted"]
    list_filter   = ["is_deleted"]
    search_fields = ["ledger__supplier_name", "file_name"]
    readonly_fields = [
        "ledger", "file_name", "file_path", "date_from", "date_to",
        "saved_by", "deleted_by", "created_at", "deleted_at",
    ]

    def has_add_permission(self, request):
        return False


@admin.register(CustomerLedger)
class CustomerLedgerAdmin(admin.ModelAdmin):
    list_display  = ["customer_name", "customer_code", "created_at"]
    search_fields = ["customer_name", "customer_code"]
    readonly_fields = ["customer", "customer_name", "customer_code", "created_at"]

    def has_add_permission(self, request):
        return False  # created automatically with customer

    def has_delete_permission(self, request, obj=None):
        return False  # ledgers are permanent


@admin.register(CustomerLedgerEntry)
class CustomerLedgerEntryAdmin(admin.ModelAdmin):
    list_display  = ["ledger", "date", "entry_type", "reference", "debit", "credit"]
    list_filter   = ["entry_type"]
    search_fields = ["reference", "details", "ledger__customer_name"]
    readonly_fields = [
        "ledger", "entry_type", "date", "details", "reference",
        "debit", "credit", "created_by", "created_at",
        "invoice", "payment", "customer_return",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CustomerLedgerSnapshot)
class CustomerLedgerSnapshotAdmin(admin.ModelAdmin):
    list_display  = ["ledger", "year_month", "closing_balance", "updated_at"]
    list_filter   = ["year_month"]
    search_fields = ["ledger__customer_name", "ledger__customer_code"]
    readonly_fields = ["ledger", "year_month", "closing_balance", "updated_at"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SavedCustomerLedgerPDF)
class SavedCustomerLedgerPDFAdmin(admin.ModelAdmin):
    list_display  = ["ledger", "file_name", "date_from", "date_to", "saved_by", "is_deleted"]
    list_filter   = ["is_deleted"]
    search_fields = ["ledger__customer_name", "file_name"]
    readonly_fields = [
        "ledger", "file_name", "file_path", "date_from", "date_to",
        "saved_by", "deleted_by", "created_at", "deleted_at",
    ]

    def has_add_permission(self, request):
        return False