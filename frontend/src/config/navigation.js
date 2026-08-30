// Single source of truth for sidebar navigation. Pure data — role filtering
// (isAdmin/isSuperuser) is applied at render time in Sidebar.jsx, not here.
import {
    LayoutDashboard, Users, User, Store, DollarSign, BookOpen, Calculator,
    DatabaseZap, ShoppingCart, FolderOpen, Library, Building2, Package,
    ClipboardList, Wallet, Undo2, BarChart3, FileText, Clock, TrendingUp,
    Repeat, Tag, Send, Calendar, Receipt, Banknote, PackageX, RotateCcw,
    LineChart, TrendingDown, IdCard, ArrowDownCircle, Handshake, Trash2,
    Gem, Archive, CreditCard, History, Landmark, ArrowLeftRight, FileBarChart, Scale,
    Wallet2,
} from 'lucide-react';

export const mainNavigation = [
    { name: 'Dashboard', path: '/dashboard', icon: LayoutDashboard },
    // Inventory + Rates are viewable by every role
    { name: 'Inventory', path: '/purchases/inventory', icon: Store },
    { name: 'Rates', path: '/rates', icon: DollarSign },
    // Cash Calculator — available to all authenticated roles
    { name: 'Cash Calculator', path: '/cash-calculator', icon: Calculator },
    // One-time bootstrap tool — superuser only
    { name: 'Data Entry', path: '/data-entry', icon: DatabaseZap, superuserOnly: true },
];

export const navGroups = [
    {
        // Ledger app is admin/superuser-only end to end
        key: 'ledger',
        label: 'Ledger',
        icon: BookOpen,
        adminOnly: true,
        items: [
            { name: 'Suppliers', path: '/ledger', icon: Building2 },
            { name: 'Customers', path: '/ledger/customers', icon: User },
        ],
    },
    {
        key: 'purchases',
        label: 'Purchases',
        icon: ShoppingCart,
        adminOnly: true,
        items: [
            { name: 'Categories', path: '/purchases/categories', icon: FolderOpen },
            { name: 'Shelves', path: '/purchases/shelves', icon: Library },
            { name: 'Suppliers', path: '/purchases/suppliers', icon: Building2 },
            { name: 'Products', path: '/purchases/products', icon: Package },
            { name: 'Orders', path: '/purchases/orders', icon: ClipboardList },
            { name: 'Payments', path: '/purchases/payments', icon: Wallet },
            { name: 'Returns', path: '/purchases/returns', icon: Undo2 },
            { name: 'Outstanding', path: '/purchases/suppliers/outstanding', icon: BarChart3 },
        ],
    },
    {
        key: 'billing',
        label: 'Billing',
        icon: Receipt,
        items: [
            { name: 'Customers', path: '/billing/customers', icon: User },
            { name: 'Invoices', path: '/billing/invoices', icon: FileText },
            { name: 'Returns', path: '/billing/returns', icon: Undo2 },
            { name: 'Payments', path: '/billing/payments', icon: Wallet, adminOnly: true },
            { name: 'Invoices Outstanding', path: '/billing/invoices/outstanding', icon: BarChart3, adminOnly: true },
            { name: 'Due Invoices', path: '/billing/invoices/due', icon: Clock },
            { name: 'Customer Outstanding', path: '/billing/customers/outstanding', icon: TrendingUp, adminOnly: true },
        ],
    },
    {
        key: 'recurringExpenses',
        label: 'Recurring Expenses',
        icon: Repeat,
        adminOnly: true,
        items: [
            { name: 'Overview', path: '/recurring-expenses', icon: Repeat },
            { name: 'Categories', path: '/recurring-expenses/categories', icon: Tag },
            { name: 'Templates', path: '/recurring-expenses/templates', icon: FileText },
            { name: 'Post Dues', path: '/recurring-expenses/post-dues', icon: Send },
            { name: 'Assignments', path: '/recurring-expenses/assignments', icon: ClipboardList },
            { name: 'Monthly Breakdown', path: '/recurring-expenses/monthly-stats', icon: Calendar },
        ],
    },
    {
        key: 'expenses',
        label: 'Expenses',
        icon: Wallet,
        adminOnly: true,
        items: [
            { name: 'Categories', path: '/expenses/categories', icon: FolderOpen },
            { name: 'All Expenses', path: '/expenses', icon: ClipboardList },
        ],
    },
    {
        key: 'taxes',
        label: 'Taxes',
        icon: Calculator,
        adminOnly: true,
        items: [
            { name: 'Overview', path: '/taxes', icon: Calculator },
            { name: 'GST Payments', path: '/taxes/payments', icon: Receipt },
            { name: 'WHT Payments', path: '/taxes/wht-payments', icon: IdCard },
        ],
    },
    {
        key: 'cashManagement',
        label: 'Cash Management',
        icon: Banknote,
        adminOnly: true,
        items: [
            { name: 'Overview', path: '/cash-management', icon: Banknote },
            { name: 'Cash Adjustments', path: '/cash-management/adjustments', icon: ArrowDownCircle },
            { name: 'Investors', path: '/cash-management/investors', icon: Handshake },
            { name: 'Growth History', path: '/cash-management/growth-history', icon: TrendingUp },
            { name: 'Owner Transactions', path: '/cash-management/owner-transactions', icon: User },
        ],
    },
    {
        key: 'paymentMethods',
        label: 'Payment Methods',
        icon: CreditCard,
        adminOnly: true,
        items: [
            { name: 'Payment Methods', path: '/payment-methods', icon: Wallet2 },
            { name: 'Transfers', path: '/payment-methods/transfers', icon: ArrowLeftRight },
        ],
    },
    {
        key: 'assets',
        label: 'Assets',
        icon: Building2,
        adminOnly: true,
        items: [
            { name: 'Overview', path: '/assets', icon: Building2 },
            { name: 'Categories', path: '/assets/categories', icon: Tag },
            { name: 'Assets', path: '/assets/items', icon: Package },
            { name: 'Disposals', path: '/assets/disposals', icon: Trash2 },
            { name: 'Payments', path: '/assets/payments', icon: Receipt },
        ],
    },
    {
        key: 'profits',
        label: 'Profits',
        icon: Gem,
        adminOnly: true,
        items: [
            { name: 'Business Worth', path: '/business-worth', icon: Gem },
            { name: 'Monthly Profits', path: '/monthly-profits', icon: BarChart3 },
            { name: 'Investor Payments', path: '/profits/payouts', icon: Banknote },
            { name: 'Investors', path: '/profits/investors', icon: Handshake },
        ],
    },
    {
        key: 'accounting',
        label: 'Accounting',
        icon: Landmark,
        adminOnly: true,
        items: [
            { name: 'Income Statement', path: '/accounting/income-statement', icon: FileBarChart },
            { name: 'Balance Sheet', path: '/accounting/balance-sheet', icon: Scale },
            { name: 'Cash Flow Statement', path: '/accounting/cash-flow-statement', icon: ArrowLeftRight },
            { name: 'A/R Aging', path: '/accounting/ar-aging', icon: TrendingUp },
            { name: 'A/P Aging', path: '/accounting/ap-aging', icon: TrendingDown },
            { name: 'Fixed Asset Register', path: '/accounting/fixed-asset-register', icon: Building2 },
        ],
    },
    {
        key: 'reports',
        label: 'Reports',
        icon: TrendingUp,
        adminOnly: true,
        items: [
            { name: 'Invoices Report', path: '/reports/invoices', icon: Receipt },
            { name: 'Cash Collected Report', path: '/reports/cash-collected', icon: Banknote },
            { name: 'Credit Customer Report', path: '/reports/credit-customers', icon: CreditCard },
            { name: 'Stock Movement Report', path: '/reports/stock-movement', icon: Package },
            { name: 'Inventory Valuation Report', path: '/reports/inventory-valuation', icon: Store },
            { name: 'Lost Inventory Report', path: '/reports/lost-inventory', icon: PackageX },
            { name: 'Recurring Expenses Report', path: '/reports/recurring-expenses', icon: Repeat },
            { name: 'Expenses Report', path: '/reports/expenses', icon: ClipboardList },
            { name: 'Purchase Returns Report', path: '/reports/purchase-returns', icon: RotateCcw },
            { name: 'Customer Returns Report', path: '/reports/customer-returns', icon: Undo2 },
            { name: 'Asset Depreciation Report', path: '/reports/asset-depreciation', icon: TrendingDown },
            { name: 'Sales Tax Report', path: '/reports/sales-tax', icon: Receipt },
            { name: 'Profit Margin Report', path: '/reports/profit-margin', icon: TrendingUp },
            { name: 'Net Profit Report', path: '/reports/net-profit', icon: LineChart },
        ],
    },
];

// Standalone links — not grouped, rendered after navGroups (in this order)
export const standaloneLinks = [
    // Listing all users is superuser-only (see users app permission matrix)
    { name: 'Users', path: '/users', icon: Users, superuserOnly: true },
    { name: 'Backups', path: '/backups', icon: Archive, adminOnly: true },
    // System-wide audit trail — superuser only
    { name: 'Activity Log', path: '/activity-log', icon: History, superuserOnly: true },
];
