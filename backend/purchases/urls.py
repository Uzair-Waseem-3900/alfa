from django.urls import path

from .views import (
    # Lookup tables
    CategoryListCreateView,
    CategoryRetrieveUpdateDestroyView,
    ShelfListCreateView,
    ShelfRetrieveUpdateDestroyView,
    ShelfStockListView,
    CandidateShelvesForProductView,
    AutoAllocateShelvesView,
    MoveStockView,

    # Supplier
    SupplierListCreateView,
    SupplierRetrieveUpdateDestroyView,
    SupplierOutstandingListView,
    SupplierPayableSummaryView,
    SupplierOutstandingOrdersView,
    AllSupplierPaymentsView,

    # Product
    ProductListCreateView,
    ProductRetrieveUpdateDestroyView,

    # Purchase item / return item shelf allocations
    SetPurchaseItemShelfAllocationsView,
    SetPurchaseReturnItemShelfAllocationsView,

    # Purchase Orders
    PurchaseOrderListCreateView,
    PurchaseOrderRetrieveUpdateDestroyView,
    PurchaseOrderConfirmView,
    DraftPurchaseOrderListView,
    ConfirmedPurchaseOrderListView,
    AllOutstandingOrdersView,

    # Supplier Payments
    SupplierPaymentListCreateView,
    SupplierPaymentDestroyView,
    PurchaseOrderPaymentSummaryView,

    # Purchase Returns
    PurchaseReturnListCreateView,
    AllPurchaseReturnsListView,
    PurchaseReturnAcceptView,
    PurchaseReturnRetrieveUpdateDestroyView,

    # PDF
    PurchaseOrderPrintView,
    PurchaseOrderSavePDFView,
    PurchaseOrderSavedPDFListView,
    SavedPurchaseOrderPDFDeleteView,

    # Inventory
    InventoryListView,
    InventoryRetrieveView,
    InventoryStatsView,
    LowStockInventoryListView,
    OutOfStockInventoryListView,

    # Lost Inventory
    LostInventoryFifoPreviewView,
    LostInventoryListCreateView,
    LostInventoryRetrieveView,
    MarkLostInventoryFoundView,
)

urlpatterns = [

    # -----------------------------------------------------------------------
    # Lookup tables
    # -----------------------------------------------------------------------
    path("categories/",          CategoryListCreateView.as_view(),             name="category-list-create"),
    path("categories/<int:pk>/", CategoryRetrieveUpdateDestroyView.as_view(), name="category-detail"),

    path("shelves/",             ShelfListCreateView.as_view(),                name="shelf-list-create"),

    # static paths (candidates/, move/) BEFORE dynamic <int:pk> paths
    path("shelves/candidates/",  CandidateShelvesForProductView.as_view(),     name="shelf-candidates"),
    path("shelves/auto-allocate/", AutoAllocateShelvesView.as_view(),          name="shelf-auto-allocate"),
    path("shelves/move/",        MoveStockView.as_view(),                      name="shelf-move-stock"),

    path("shelves/<int:pk>/",    ShelfRetrieveUpdateDestroyView.as_view(),     name="shelf-detail"),
    path("shelves/<int:pk>/stock/", ShelfStockListView.as_view(),              name="shelf-stock-list"),

    # -----------------------------------------------------------------------
    # Supplier
    # IMPORTANT: static paths (outstanding/) BEFORE dynamic paths (<int:pk>/)
    # -----------------------------------------------------------------------
    path("suppliers/",
         SupplierListCreateView.as_view(),
         name="supplier-list-create"),

    path("suppliers/outstanding/",
         SupplierOutstandingListView.as_view(),
         name="supplier-outstanding-list"),

    path("suppliers/<int:pk>/",
         SupplierRetrieveUpdateDestroyView.as_view(),
         name="supplier-detail"),

    path("suppliers/<int:pk>/payable-summary/",
         SupplierPayableSummaryView.as_view(),
         name="supplier-payable-summary"),

    path("suppliers/<int:pk>/outstanding-orders/",
         SupplierOutstandingOrdersView.as_view(),
         name="supplier-outstanding-orders"),

    # -----------------------------------------------------------------------
    # Product
    # -----------------------------------------------------------------------
    path("products/",            ProductListCreateView.as_view(),             name="product-list-create"),
    path("products/<int:pk>/",   ProductRetrieveUpdateDestroyView.as_view(), name="product-detail"),

    # -----------------------------------------------------------------------
    # Purchase Orders
    # IMPORTANT: all static paths BEFORE dynamic <int:pk> paths
    # -----------------------------------------------------------------------
    path("orders/",
         PurchaseOrderListCreateView.as_view(),
         name="purchase-order-list-create"),

    path("orders/drafts/",
         DraftPurchaseOrderListView.as_view(),
         name="purchase-order-drafts"),

    path("orders/confirmed/",
         ConfirmedPurchaseOrderListView.as_view(),
         name="purchase-order-confirmed"),

    path("orders/outstanding/",
         AllOutstandingOrdersView.as_view(),
         name="all-outstanding-orders"),

    path("orders/<int:pk>/",
         PurchaseOrderRetrieveUpdateDestroyView.as_view(),
         name="purchase-order-detail"),

    path("orders/<int:pk>/confirm/",
         PurchaseOrderConfirmView.as_view(),
         name="purchase-order-confirm"),

    path("orders/<int:pk>/payment-summary/",
         PurchaseOrderPaymentSummaryView.as_view(),
         name="purchase-order-payment-summary"),

    path("orders/<int:pk>/print/",
         PurchaseOrderPrintView.as_view(),
         name="purchase-order-print"),

    path("orders/<int:pk>/pdf/save/",
         PurchaseOrderSavePDFView.as_view(),
         name="purchase-order-pdf-save"),

    path("orders/<int:pk>/pdf/",
         PurchaseOrderSavedPDFListView.as_view(),
         name="purchase-order-pdf-list"),

    # -----------------------------------------------------------------------
    # Purchase item / return item shelf allocations
    # -----------------------------------------------------------------------
    path("purchase-items/<int:pk>/shelf-allocations/",
         SetPurchaseItemShelfAllocationsView.as_view(),
         name="purchase-item-shelf-allocations"),

    path("return-items/<int:pk>/shelf-allocations/",
         SetPurchaseReturnItemShelfAllocationsView.as_view(),
         name="purchase-return-item-shelf-allocations"),

    # -----------------------------------------------------------------------
    # Supplier Payments (nested under order)
    # -----------------------------------------------------------------------
    path("orders/<int:order_id>/payments/",
         SupplierPaymentListCreateView.as_view(),
         name="supplier-payment-list-create"),

    path("payments/",
         AllSupplierPaymentsView.as_view(),
         name="supplier-payment-list-all"),

    path("payments/<int:pk>/",
         SupplierPaymentDestroyView.as_view(),
         name="supplier-payment-delete"),

    # -----------------------------------------------------------------------
    # Purchase Returns
    # -----------------------------------------------------------------------
    path("returns/",
         AllPurchaseReturnsListView.as_view(),
         name="purchase-return-list-all"),

    path("returns/<int:pk>/accept/",
         PurchaseReturnAcceptView.as_view(),
         name="purchase-return-accept"),

    path("returns/<int:pk>/",
         PurchaseReturnRetrieveUpdateDestroyView.as_view(),
         name="purchase-return-detail"),

    path("orders/<int:order_id>/returns/",
         PurchaseReturnListCreateView.as_view(),
         name="purchase-return-list-create"),

    # -----------------------------------------------------------------------
    # Saved PDFs
    # -----------------------------------------------------------------------
    path("pdf/<int:saved_pdf_id>/",
         SavedPurchaseOrderPDFDeleteView.as_view(),
         name="purchase-order-pdf-delete"),

    # -----------------------------------------------------------------------
    # Inventory
    # -----------------------------------------------------------------------
    path("inventory/",
         InventoryListView.as_view(),
         name="inventory-list"),

    path("inventory/stats/",
         InventoryStatsView.as_view(),
         name="inventory-stats"),

    path("inventory/low-stock/",
         LowStockInventoryListView.as_view(),
         name="inventory-low-stock"),

    path("inventory/out-of-stock/",
         OutOfStockInventoryListView.as_view(),
         name="inventory-out-of-stock"),

    path("inventory/<int:product_id>/",
         InventoryRetrieveView.as_view(),
         name="inventory-detail"),

    # -----------------------------------------------------------------------
    # Lost Inventory
    # IMPORTANT: static paths (fifo-preview/) BEFORE dynamic paths (<int:pk>/)
    # -----------------------------------------------------------------------
    path("lost-inventory/",
         LostInventoryListCreateView.as_view(),
         name="lost-inventory-list-create"),

    path("lost-inventory/fifo-preview/",
         LostInventoryFifoPreviewView.as_view(),
         name="lost-inventory-fifo-preview"),

    path("lost-inventory/<int:pk>/",
         LostInventoryRetrieveView.as_view(),
         name="lost-inventory-detail"),

    path("lost-inventory/items/<int:item_id>/found/",
         MarkLostInventoryFoundView.as_view(),
         name="lost-inventory-item-found"),
]