import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
    Receipt, Wallet, TrendingDown, PackageX, RotateCcw, Undo2,
    TrendingUp, Tag, Calculator, Repeat, LineChart, Package, CreditCard,
    ChevronRight,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import Card from '../../components/ui/Card';

const REPORTS = [
    {
        title: 'Invoices Report',
        description: 'Total invoices and their value for a selected date range',
        icon: Receipt,
        path: '/reports/invoices',
    },
    {
        title: 'Cash Collected Report',
        description: 'Total cash collected from customers for a selected date range',
        icon: Wallet,
        path: '/reports/cash-collected',
    },
    {
        title: 'Expenses Report',
        description: 'Total expenses and their value for a selected date range',
        icon: TrendingDown,
        path: '/reports/expenses',
    },
    {
        title: 'Lost Inventory Report',
        description: 'Products marked as lost, damaged, or missing for a selected date range',
        icon: PackageX,
        path: '/reports/lost-inventory',
    },
    {
        title: 'Purchase Returns Report',
        description: 'Accepted returns to suppliers for a selected date range',
        icon: RotateCcw,
        path: '/reports/purchase-returns',
    },
    {
        title: 'Customer Returns Report',
        description: 'Accepted returns from customers for a selected date range',
        icon: Undo2,
        path: '/reports/customer-returns',
    },
    {
        title: 'Profit / Margin Report',
        description: 'Revenue, cost of goods sold, and gross profit for a selected date range',
        icon: TrendingUp,
        path: '/reports/profit-margin',
    },
    {
        title: 'Inventory Valuation Report',
        description: 'Live snapshot of current stock valued at FIFO cost',
        icon: Tag,
        path: '/reports/inventory-valuation',
    },
    {
        title: 'Sales Tax Report',
        description: 'Input Tax (paid to suppliers) vs Output Tax (charged to customers) for a selected date range',
        icon: Calculator,
        path: '/reports/sales-tax',
    },
    {
        title: 'Recurring Expenses Report',
        description: 'Every recurring expense assignment — rent, salaries, utilities — for a selected date range',
        icon: Repeat,
        path: '/reports/recurring-expenses',
    },
    {
        title: 'Net Profit Report',
        description: '"Real" profit per finalized month, with the full deduction breakdown, for a selected date range',
        icon: LineChart,
        path: '/reports/net-profit',
    },
    {
        title: 'Asset Depreciation Report',
        description: 'Every depreciation posting across all assets for a selected date range',
        icon: TrendingDown,
        path: '/reports/asset-depreciation',
    },
    {
        title: 'Stock Movement Report',
        description: 'How much of each product was purchased, returned to suppliers, sold, returned by customers, lost, and found',
        icon: Package,
        path: '/reports/stock-movement',
    },
    {
        title: 'Credit Customer Report',
        description: 'Customers grouped by their system-calculated credit score — Good, Average, or Poor',
        icon: CreditCard,
        path: '/reports/credit-customers',
    },
];

const ReportsHomePage = () => {
    const { user } = useAuth();
    const navigate = useNavigate();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    if (!isAdmin) {
        navigate('/dashboard');
        return null;
    }

    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-3xl font-bold text-neutral-900">Reports</h1>
                <p className="text-neutral-500 mt-1">Business reports and analytics</p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
                {REPORTS.map((report, index) => {
                    const Icon = report.icon;
                    return (
                        <motion.div
                            key={report.path}
                            initial={{ opacity: 0, y: 12 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: Math.min(index * 0.04, 0.4) }}
                        >
                            <Card
                                className="group cursor-pointer h-full flex flex-col"
                                onClick={() => navigate(report.path)}
                            >
                                <div className="flex items-start justify-between">
                                    <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-primary-700 to-accent-600 flex items-center justify-center shadow-md shadow-primary-900/20">
                                        <Icon className="w-5 h-5 text-white" />
                                    </div>
                                    <ChevronRight className="w-5 h-5 text-neutral-300 group-hover:text-accent-600 group-hover:translate-x-0.5 transition-all" />
                                </div>
                                <h3 className="text-lg font-semibold text-neutral-900 mt-4">{report.title}</h3>
                                <p className="text-sm text-neutral-500 mt-1.5 leading-relaxed">{report.description}</p>
                            </Card>
                        </motion.div>
                    );
                })}
            </div>
        </div>
    );
};

export default ReportsHomePage;
