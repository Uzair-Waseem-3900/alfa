import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ToastProvider } from './context/ToastContext';
import { useKeepAlive } from './hooks/useKeepAlive';
import ProtectedRoute from './components/auth/ProtectedRoute';
import Layout from './components/layout/Layout';
import Login from './pages/Login';
import Users from './pages/Users';
import Profile from './pages/Profile';
import DashboardPage from './pages/DashboardPage';

// Purchases pages
import CategoriesPage from './pages/purchases/CategoriesPage';
import ShelvesPage from './pages/purchases/ShelvesPage';
import ShelfDetailPage from './pages/purchases/ShelfDetailPage';
import SuppliersPage from './pages/purchases/SuppliersPage';
import SupplierDetailPage from './pages/purchases/SupplierDetailPage';
import ProductsPage from './pages/purchases/ProductsPage';
import PurchaseOrdersPage from './pages/purchases/PurchaseOrdersPage';
import PurchaseOrderDetailPage from './pages/purchases/PurchaseOrderDetailPage';
import PaymentsPage from './pages/purchases/PaymentsPage';
import ReturnsPage from './pages/purchases/ReturnsPage';
import AllReturnsPage from './pages/purchases/AllReturnsPage';
import PurchaseReturnDetailPage from './pages/purchases/PurchaseReturnDetailPage';
import SuppliersOutstandingPage from './pages/purchases/SuppliersOutstandingPage';
import InventoryPage from './pages/purchases/InventoryPage';
import LostInventoryPage from './pages/purchases/LostInventoryPage';
import LostInventoryRecordsPage from './pages/purchases/LostInventoryRecordsPage';
import LostInventoryDetailPage from './pages/purchases/LostInventoryDetailPage';
import GlobalPaymentsPage from './pages/purchases/GlobalPaymentsPage';
import PurchasePaymentDetailPage from './pages/purchases/PurchasePaymentDetailPage';

// Rates pages
import RatesPage from './pages/rates/RatesPage';
import UnpricedProductsPage from './pages/rates/UnpricedProductsPage';
import PriceHistoryPage from './pages/rates/PriceHistoryPage';

// Billing pages
import CustomersPage from './pages/billing/CustomersPage';
import CustomerDetailPage from './pages/billing/CustomerDetailPage';
import CustomerCreditScorePage from './pages/billing/CustomerCreditScorePage';
import CustomerCreditScoreHistoryPage from './pages/billing/CustomerCreditScoreHistoryPage';
import CustomerOutstandingPage from './pages/billing/CustomerOutstandingPage';
import InvoicesPage from './pages/billing/InvoicesPage';
import CreateInvoicePage from './pages/billing/CreateInvoicePage';
import EditInvoicePage from './pages/billing/EditInvoicePage';
import InvoiceDetailPage from './pages/billing/InvoiceDetailPage';
import InvoicePreviewPage from './pages/billing/InvoicePreviewPage';
import BillingPaymentsPage from "./pages/billing/PaymentsPage";
import PaymentDetailPage from './pages/billing/PaymentDetailPage';
import OutstandingInvoicesPage from './pages/billing/OutstandingInvoicesPage';
import DueInvoicesPage from './pages/billing/DueInvoicesPage';
import BillingReturnsPage from './pages/billing/ReturnsPage';
import ReturnDetailPage from './pages/billing/ReturnDetailPage';

// Expenses pages
import ExpenseCategoriesPage from './pages/expenses/ExpenseCategoriesPage';
import ExpensesPage from './pages/expenses/ExpensesPage';
import ExpenseDetailPage from './pages/expenses/ExpenseDetailPage';
import EditExpensePage from './pages/expenses/EditExpensePage';

// Ledger pages
import LedgerListPage from './pages/ledger/LedgerListPage';
import LedgerDetailPage from './pages/ledger/LedgerDetailPage';
import LedgerBySupplierPage from './pages/ledger/LedgerBySupplierPage';
import CustomerLedgerDetailPage from './pages/ledger/CustomerLedgerDetailPage';

// Accounting pages
import ARAgingPage from './pages/accounting/ARAgingPage';
import APAgingPage from './pages/accounting/APAgingPage';
import FixedAssetRegisterPage from './pages/accounting/FixedAssetRegisterPage';
import CashFlowStatementPage from './pages/accounting/CashFlowStatementPage';
import IncomeStatementPage from './pages/accounting/IncomeStatementPage';
import BalanceSheetPage from './pages/accounting/BalanceSheetPage';

// Reports pages
import ReportsHomePage from './pages/reports/ReportsHomePage';
import InvoicesReportPage from './pages/reports/InvoicesReportPage';
import CashCollectedReportPage from './pages/reports/CashCollectedReportPage';
import ExpensesReportPage from './pages/reports/ExpensesReportPage';
import LostInventoryReportPage from './pages/reports/LostInventoryReportPage';
import PurchaseReturnsReportPage from './pages/reports/PurchaseReturnsReportPage';
import CustomerReturnsReportPage from './pages/reports/CustomerReturnsReportPage';
import ProfitMarginReportPage from './pages/reports/ProfitMarginReportPage';
import InventoryValuationReportPage from './pages/reports/InventoryValuationReportPage';
import SalesTaxReportPage from './pages/reports/SalesTaxReportPage';
import RecurringExpensesReportPage from './pages/reports/RecurringExpensesReportPage';
import NetProfitReportPage from './pages/reports/NetProfitReportPage';
import AssetDepreciationReportPage from './pages/reports/AssetDepreciationReportPage';
import StockMovementReportPage from './pages/reports/StockMovementReportPage';
import CreditCustomerReportPage from './pages/reports/CreditCustomerReportPage';

// Taxes pages
import TaxesPage from './pages/taxes/TaxesPage';
import TaxPaymentsPage from './pages/taxes/TaxPaymentsPage';
import TaxPaymentDetailPage from './pages/taxes/TaxPaymentDetailPage';
import WHTPaymentsPage from './pages/taxes/WHTPaymentsPage';
import WHTPaymentDetailPage from './pages/taxes/WHTPaymentDetailPage';

// Cash Management pages
import CashManagementPage from './pages/cashManagement/CashManagementPage';
import CashAdjustmentsPage from './pages/cashManagement/CashAdjustmentsPage';
import CashAdjustmentDetailPage from './pages/cashManagement/CashAdjustmentDetailPage';
import InvestorsPage from './pages/cashManagement/InvestorsPage';
import InvestorDetailPage from './pages/cashManagement/InvestorDetailPage';
import InvestorTransactionDetailPage from './pages/cashManagement/InvestorTransactionDetailPage';
import InvestorGrowthHistoryPage from './pages/cashManagement/InvestorGrowthHistoryPage';
import OwnerTransactionsPage from './pages/cashManagement/OwnerTransactionsPage';
import OwnerTransactionDetailPage from './pages/cashManagement/OwnerTransactionDetailPage';

// Profits pages
import BusinessWorthPage from './pages/profits/BusinessWorthPage';
import MonthlyProfitsPage from './pages/profits/MonthlyProfitsPage';
import MonthlyProfitDetailPage from './pages/profits/MonthlyProfitDetailPage';
import InvestorPayoutsPage from './pages/profits/InvestorPayoutsPage';
import InvestorPayoutDetailPage from './pages/profits/InvestorPayoutDetailPage';
import ProfitInvestorsListPage from './pages/profits/ProfitInvestorsListPage';
import ProfitInvestorDetailPage from './pages/profits/ProfitInvestorDetailPage';
import BackupPage from './pages/backups/BackupPage';
import BackupHistoryPage from './pages/backups/BackupHistoryPage';

// Assets pages
import AssetsPage from './pages/assets/AssetsPage';
import AssetCategoriesPage from './pages/assets/AssetCategoriesPage';
import AssetItemsPage from './pages/assets/AssetItemsPage';
import AssetDetailPage from './pages/assets/AssetDetailPage';
import AssetDisposalsPage from './pages/assets/AssetDisposalsPage';
import AssetPaymentsPage from './pages/assets/AssetPaymentsPage';
import AssetPaymentDetailPage from './pages/assets/AssetPaymentDetailPage';

// Payment Methods pages
import PaymentMethodsListPage from './pages/paymentMethods/PaymentMethodsListPage';
import PaymentMethodDetailPage from './pages/paymentMethods/PaymentMethodDetailPage';
import AccountTransfersPage from './pages/paymentMethods/AccountTransfersPage';

// Recurring Expenses pages
import RecurringExpensesPage from './pages/recurringExpenses/RecurringExpensesPage';
import RecurringExpenseCategoriesPage from './pages/recurringExpenses/RecurringExpenseCategoriesPage';
import RecurringExpenseTemplatesPage from './pages/recurringExpenses/RecurringExpenseTemplatesPage';
import RecurringExpensePostDuesPage from './pages/recurringExpenses/RecurringExpensePostDuesPage';
import RecurringExpenseAssignmentsPage from './pages/recurringExpenses/RecurringExpenseAssignmentsPage';
import RecurringExpenseAssignmentDetailPage from './pages/recurringExpenses/RecurringExpenseAssignmentDetailPage';
import RecurringExpensePaymentDetailPage from './pages/recurringExpenses/RecurringExpensePaymentDetailPage';
import RecurringExpenseMonthlyStatsPage from './pages/recurringExpenses/RecurringExpenseMonthlyStatsPage';

// Data Entry (superuser-only bootstrap tool)
import DataEntryPage from './pages/dataentry/DataEntryPage';

// Activity Log (superuser-only, system-wide audit trail)
import ActivityLogPage from './pages/ActivityLogPage';

// Cash Calculator (frontend-only utility, all roles)
import CashCalculatorPage from './pages/cashCalculator/CashCalculatorPage';

import './App.css';

const AppContent = () => {
  const { isAuthenticated } = useAuth();

  return (
    <AnimatePresence mode="wait">
      <Routes>
        {/* Auth Routes */}
        <Route path="/login" element={
          isAuthenticated ? <Navigate to="/dashboard" /> : <Login />
        } />

        <Route path="/" element={
          <ProtectedRoute>
            <Layout>
              <Navigate to="/dashboard" />
            </Layout>
          </ProtectedRoute>
        } />

        {/* Dashboard */}
        <Route path="/dashboard" element={
          <ProtectedRoute>
            <Layout>
              <DashboardPage />
            </Layout>
          </ProtectedRoute>
        } />

        {/* User Management */}
        <Route path="/users" element={
          <ProtectedRoute>
            <Layout>
              <Users />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/profile" element={
          <ProtectedRoute>
            <Layout>
              <Profile />
            </Layout>
          </ProtectedRoute>
        } />

        {/* Purchases Routes */}
        <Route path="/purchases/categories" element={
          <ProtectedRoute>
            <Layout>
              <CategoriesPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/purchases/shelves" element={
          <ProtectedRoute>
            <Layout>
              <ShelvesPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/purchases/shelves/:id" element={
          <ProtectedRoute>
            <Layout>
              <ShelfDetailPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/purchases/suppliers" element={
          <ProtectedRoute>
            <Layout>
              <SuppliersPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/purchases/suppliers/:id" element={
          <ProtectedRoute>
            <Layout>
              <SupplierDetailPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/purchases/products" element={
          <ProtectedRoute>
            <Layout>
              <ProductsPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/purchases/orders" element={
          <ProtectedRoute>
            <Layout>
              <PurchaseOrdersPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/purchases/orders/:id" element={
          <ProtectedRoute>
            <Layout>
              <PurchaseOrderDetailPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/purchases/payments" element={
          <ProtectedRoute>
            <Layout>
              <GlobalPaymentsPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/purchases/payments/ref/:reference" element={
          <ProtectedRoute>
            <Layout>
              <PurchasePaymentDetailPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/purchases/orders/:orderId/payments" element={
          <ProtectedRoute>
            <Layout>
              <PaymentsPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/purchases/returns" element={
          <ProtectedRoute>
            <Layout>
              <AllReturnsPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/purchases/returns/:returnId" element={
          <ProtectedRoute>
            <Layout>
              <PurchaseReturnDetailPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/purchases/orders/:orderId/returns" element={
          <ProtectedRoute>
            <Layout>
              <ReturnsPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/purchases/suppliers/outstanding" element={
          <ProtectedRoute>
            <Layout>
              <SuppliersOutstandingPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/purchases/inventory" element={
          <ProtectedRoute>
            <Layout>
              <InventoryPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/purchases/lost-inventory" element={
          <ProtectedRoute>
            <Layout>
              <LostInventoryPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/purchases/lost-inventory/records" element={
          <ProtectedRoute>
            <Layout>
              <LostInventoryRecordsPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/purchases/lost-inventory/records/:recordId" element={
          <ProtectedRoute>
            <Layout>
              <LostInventoryDetailPage />
            </Layout>
          </ProtectedRoute>
        } />

        {/* Rates Routes */}
        <Route path="/rates" element={
          <ProtectedRoute>
            <Layout>
              <RatesPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/rates/unpriced" element={
          <ProtectedRoute>
            <Layout>
              <UnpricedProductsPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/rates/history/:productId" element={
          <ProtectedRoute>
            <Layout>
              <PriceHistoryPage />
            </Layout>
          </ProtectedRoute>
        } />

        {/* Billing Routes */}
        <Route path="/billing/customers" element={
          <ProtectedRoute>
            <Layout>
              <CustomersPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/billing/customers/:id" element={
          <ProtectedRoute>
            <Layout>
              <CustomerDetailPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/billing/customers/:id/credit-score" element={
          <ProtectedRoute>
            <Layout>
              <CustomerCreditScorePage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/billing/customers/:id/credit-score/history" element={
          <ProtectedRoute>
            <Layout>
              <CustomerCreditScoreHistoryPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/billing/customers/outstanding" element={
          <ProtectedRoute>
            <Layout>
              <CustomerOutstandingPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/billing/invoices" element={
          <ProtectedRoute>
            <Layout>
              <InvoicesPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/billing/invoices/create" element={
          <ProtectedRoute>
            <Layout>
              <CreateInvoicePage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/billing/invoices/:id" element={
          <ProtectedRoute>
            <Layout>
              <InvoiceDetailPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/billing/invoices/:id/edit" element={
          <ProtectedRoute>
            <Layout>
              <EditInvoicePage />
            </Layout>
          </ProtectedRoute>
        } />

        {/* Deliberately no <Layout> — this is a mobile screenshot surface,
            not app navigation. See InvoicePreviewPage.jsx's comment. */}
        <Route path="/billing/invoices/:id/preview" element={
          <ProtectedRoute>
            <InvoicePreviewPage />
          </ProtectedRoute>
        } />

        <Route path="/billing/payments" element={
          <ProtectedRoute>
            <Layout>
              <BillingPaymentsPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/billing/payments/:paymentId" element={
          <ProtectedRoute>
            <Layout>
              <PaymentDetailPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/billing/returns" element={
          <ProtectedRoute>
            <Layout>
              <BillingReturnsPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/billing/returns/:returnId" element={
          <ProtectedRoute>
            <Layout>
              <ReturnDetailPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/billing/invoices/outstanding" element={
          <ProtectedRoute>
            <Layout>
              <OutstandingInvoicesPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/billing/invoices/due" element={
          <ProtectedRoute>
            <Layout>
              <DueInvoicesPage />
            </Layout>
          </ProtectedRoute>
        } />

        {/* Expenses Routes */}
        <Route path="/expenses/categories" element={
          <ProtectedRoute>
            <Layout>
              <ExpenseCategoriesPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/expenses" element={
          <ProtectedRoute>
            <Layout>
              <ExpensesPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/expenses/:id" element={
          <ProtectedRoute>
            <Layout>
              <ExpenseDetailPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/expenses/:id/edit" element={
          <ProtectedRoute>
            <Layout>
              <EditExpensePage />
            </Layout>
          </ProtectedRoute>
        } />

        {/* Ledger Routes */}
        <Route path="/ledger" element={
          <ProtectedRoute>
            <Layout>
              <LedgerListPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/ledger/customers" element={
          <ProtectedRoute>
            <Layout>
              <LedgerListPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/ledger/:id" element={
          <ProtectedRoute>
            <Layout>
              <LedgerDetailPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/ledger/customers/:id" element={
          <ProtectedRoute>
            <Layout>
              <CustomerLedgerDetailPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/ledger/supplier/:supplierId" element={
          <ProtectedRoute>
            <Layout>
              <LedgerBySupplierPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/reports" element={
          <ProtectedRoute>
            <Layout>
              <ReportsHomePage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/reports/invoices" element={
          <ProtectedRoute>
            <Layout>
              <InvoicesReportPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/reports/cash-collected" element={
          <ProtectedRoute>
            <Layout>
              <CashCollectedReportPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/reports/expenses" element={
          <ProtectedRoute>
            <Layout>
              <ExpensesReportPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/accounting/income-statement" element={
          <ProtectedRoute>
            <Layout>
              <IncomeStatementPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/accounting/balance-sheet" element={
          <ProtectedRoute>
            <Layout>
              <BalanceSheetPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/accounting/cash-flow-statement" element={
          <ProtectedRoute>
            <Layout>
              <CashFlowStatementPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/accounting/ar-aging" element={
          <ProtectedRoute>
            <Layout>
              <ARAgingPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/accounting/ap-aging" element={
          <ProtectedRoute>
            <Layout>
              <APAgingPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/accounting/fixed-asset-register" element={
          <ProtectedRoute>
            <Layout>
              <FixedAssetRegisterPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/reports/lost-inventory" element={
          <ProtectedRoute>
            <Layout>
              <LostInventoryReportPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/reports/purchase-returns" element={
          <ProtectedRoute>
            <Layout>
              <PurchaseReturnsReportPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/reports/customer-returns" element={
          <ProtectedRoute>
            <Layout>
              <CustomerReturnsReportPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/reports/profit-margin" element={
          <ProtectedRoute>
            <Layout>
              <ProfitMarginReportPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/reports/inventory-valuation" element={
          <ProtectedRoute>
            <Layout>
              <InventoryValuationReportPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/reports/sales-tax" element={
          <ProtectedRoute>
            <Layout>
              <SalesTaxReportPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/reports/recurring-expenses" element={
          <ProtectedRoute>
            <Layout>
              <RecurringExpensesReportPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/reports/net-profit" element={
          <ProtectedRoute>
            <Layout>
              <NetProfitReportPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/reports/asset-depreciation" element={
          <ProtectedRoute>
            <Layout>
              <AssetDepreciationReportPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/reports/stock-movement" element={
          <ProtectedRoute>
            <Layout>
              <StockMovementReportPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/reports/credit-customers" element={
          <ProtectedRoute>
            <Layout>
              <CreditCustomerReportPage />
            </Layout>
          </ProtectedRoute>
        } />

        {/* Taxes Routes */}
        <Route path="/taxes" element={
          <ProtectedRoute>
            <Layout>
              <TaxesPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/taxes/payments" element={
          <ProtectedRoute>
            <Layout>
              <TaxPaymentsPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/taxes/payments/:id" element={
          <ProtectedRoute>
            <Layout>
              <TaxPaymentDetailPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/taxes/wht-payments" element={
          <ProtectedRoute>
            <Layout>
              <WHTPaymentsPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/taxes/wht-payments/:id" element={
          <ProtectedRoute>
            <Layout>
              <WHTPaymentDetailPage />
            </Layout>
          </ProtectedRoute>
        } />

        {/* Cash Management Routes */}
        <Route path="/cash-management" element={
          <ProtectedRoute>
            <Layout>
              <CashManagementPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/cash-management/adjustments" element={
          <ProtectedRoute>
            <Layout>
              <CashAdjustmentsPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/cash-management/adjustments/:id" element={
          <ProtectedRoute>
            <Layout>
              <CashAdjustmentDetailPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/cash-management/investors" element={
          <ProtectedRoute>
            <Layout>
              <InvestorsPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/cash-management/investors/:id" element={
          <ProtectedRoute>
            <Layout>
              <InvestorDetailPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/cash-management/investor-transactions/:id" element={
          <ProtectedRoute>
            <Layout>
              <InvestorTransactionDetailPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/cash-management/growth-history" element={
          <ProtectedRoute>
            <Layout>
              <InvestorGrowthHistoryPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/cash-management/owner-transactions" element={
          <ProtectedRoute>
            <Layout>
              <OwnerTransactionsPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/cash-management/owner-transactions/:id" element={
          <ProtectedRoute>
            <Layout>
              <OwnerTransactionDetailPage />
            </Layout>
          </ProtectedRoute>
        } />

        {/* Assets Routes */}
        <Route path="/assets" element={
          <ProtectedRoute>
            <Layout>
              <AssetsPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/assets/categories" element={
          <ProtectedRoute>
            <Layout>
              <AssetCategoriesPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/assets/items" element={
          <ProtectedRoute>
            <Layout>
              <AssetItemsPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/assets/items/:id" element={
          <ProtectedRoute>
            <Layout>
              <AssetDetailPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/assets/disposals" element={
          <ProtectedRoute>
            <Layout>
              <AssetDisposalsPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/assets/payments" element={
          <ProtectedRoute>
            <Layout>
              <AssetPaymentsPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/assets/payments/:id" element={
          <ProtectedRoute>
            <Layout>
              <AssetPaymentDetailPage />
            </Layout>
          </ProtectedRoute>
        } />

        {/* Business Worth Route */}
        <Route path="/business-worth" element={
          <ProtectedRoute>
            <Layout>
              <BusinessWorthPage />
            </Layout>
          </ProtectedRoute>
        } />

        {/* Monthly Profits Routes */}
        <Route path="/monthly-profits" element={
          <ProtectedRoute>
            <Layout>
              <MonthlyProfitsPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/monthly-profits/:period" element={
          <ProtectedRoute>
            <Layout>
              <MonthlyProfitDetailPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/profits/payouts" element={
          <ProtectedRoute>
            <Layout>
              <InvestorPayoutsPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/profits/payouts/:id" element={
          <ProtectedRoute>
            <Layout>
              <InvestorPayoutDetailPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/profits/investors" element={
          <ProtectedRoute>
            <Layout>
              <ProfitInvestorsListPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/profits/investors/:id" element={
          <ProtectedRoute>
            <Layout>
              <ProfitInvestorDetailPage />
            </Layout>
          </ProtectedRoute>
        } />

        {/* Backups Routes */}
        <Route path="/backups" element={
          <ProtectedRoute>
            <Layout>
              <BackupPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/backups/history" element={
          <ProtectedRoute>
            <Layout>
              <BackupHistoryPage />
            </Layout>
          </ProtectedRoute>
        } />

        {/* Payment Methods Routes */}
        <Route path="/payment-methods" element={
          <ProtectedRoute>
            <Layout>
              <PaymentMethodsListPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/payment-methods/transfers" element={
          <ProtectedRoute>
            <Layout>
              <AccountTransfersPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/payment-methods/:id" element={
          <ProtectedRoute>
            <Layout>
              <PaymentMethodDetailPage />
            </Layout>
          </ProtectedRoute>
        } />

        {/* Recurring Expenses Routes */}
        <Route path="/recurring-expenses" element={
          <ProtectedRoute>
            <Layout>
              <RecurringExpensesPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/recurring-expenses/categories" element={
          <ProtectedRoute>
            <Layout>
              <RecurringExpenseCategoriesPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/recurring-expenses/templates" element={
          <ProtectedRoute>
            <Layout>
              <RecurringExpenseTemplatesPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/recurring-expenses/post-dues" element={
          <ProtectedRoute>
            <Layout>
              <RecurringExpensePostDuesPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/recurring-expenses/assignments" element={
          <ProtectedRoute>
            <Layout>
              <RecurringExpenseAssignmentsPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/recurring-expenses/assignments/:id" element={
          <ProtectedRoute>
            <Layout>
              <RecurringExpenseAssignmentDetailPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/recurring-expenses/payments/:id" element={
          <ProtectedRoute>
            <Layout>
              <RecurringExpensePaymentDetailPage />
            </Layout>
          </ProtectedRoute>
        } />

        <Route path="/recurring-expenses/monthly-stats" element={
          <ProtectedRoute>
            <Layout>
              <RecurringExpenseMonthlyStatsPage />
            </Layout>
          </ProtectedRoute>
        } />

        {/* Data Entry (superuser-only; page self-guards + backend enforces) */}
        <Route path="/data-entry" element={
          <ProtectedRoute>
            <Layout>
              <DataEntryPage />
            </Layout>
          </ProtectedRoute>
        } />

        {/* Activity Log (superuser-only; page self-guards + backend enforces) */}
        <Route path="/activity-log" element={
          <ProtectedRoute>
            <Layout>
              <ActivityLogPage />
            </Layout>
          </ProtectedRoute>
        } />

        {/* Cash Calculator — frontend-only utility, all authenticated roles */}
        <Route path="/cash-calculator" element={
          <ProtectedRoute>
            <Layout>
              <CashCalculatorPage />
            </Layout>
          </ProtectedRoute>
        } />

        {/* Catch all route - redirect to dashboard */}
        <Route path="*" element={
          <ProtectedRoute>
            <Layout>
              <Navigate to="/dashboard" />
            </Layout>
          </ProtectedRoute>
        } />
      </Routes>
    </AnimatePresence>
  );
};

function App() {
  useKeepAlive();

  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <AppContent />
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;