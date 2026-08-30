import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { systemApi } from '../../services/systemApi';
import { useCashFlowStats } from '../../hooks/useCashFlow';
import { useTaxesStats } from '../../hooks/useTaxes';
import { useCashManagementStats } from '../../hooks/useCashManagement';
import { useAssetStats } from '../../hooks/useAssets';
import { useRecurringExpenseFlowStats } from '../../hooks/useRecurringExpenses';
import { useProfitFlowStats } from '../../hooks/useProfits';
import ReceivablesSection from './ReceivablesSection';
import PayablesSection from './PayablesSection';
import ExpensesSectionStats from './ExpensesSectionStats';
import LostInventorySectionStats from './LostInventorySectionStats';
import ReturnsSectionStats from './ReturnsSectionStats';
import ProfitSectionStats from './ProfitSectionStats';
import TaxesSectionStats from './TaxesSectionStats';
import CashManagementSectionStats from './CashManagementSectionStats';
import AssetsSectionStats from './AssetsSectionStats';
import RecurringExpensesSectionStats from './RecurringExpensesSectionStats';
import { DollarSign, ShoppingCart, AlertTriangle, Landmark, Banknote, BarChart3, Receipt, Package } from 'lucide-react';
import GrossProfitTrendChart from './GrossProfitTrendChart';
import NetProfitTrendChart from './NetProfitTrendChart';
import BreakdownDrawer from './BreakdownDrawer';
import CollapsibleGroup from './CollapsibleGroup';
import KpiStrip from './KpiStrip';
import Badge from '../ui/Badge';
import InlineAlert from '../ui/InlineAlert';

const AdminDashboard = () => {
    const { user } = useAuth();
    const { toast } = useToast();

    // IMPORTANT — SYSTEM DESIGN, DO NOT REMOVE THIS WHEN REPLACING THE DASHBOARD:
    // This triggers every "catch-up on read" calculation in the backend
    // (asset depreciation, investor growth, monthly profit finalization —
    // see backend/backend/views.py TriggerAllCatchUpsView) once per
    // dashboard load. It exists precisely so those three stay fresh
    // regardless of which specific stat hooks/endpoints the dashboard ends
    // up calling — do not assume the individual stats hooks below cover
    // this on their own; whatever replaces this component must keep this
    // call (or move it somewhere that still fires on every dashboard load).
    useEffect(() => {
        systemApi.triggerAllCatchUps().catch((err) => {
            console.error('Failed to trigger backend catch-up calculations:', err);
            toast.error('Some background calculations failed to refresh — figures may be slightly stale.');
        });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const { data: stats, loading: statsLoading, error: statsError } = useCashFlowStats();
    const { data: taxStats, loading: taxStatsLoading, error: taxStatsError } = useTaxesStats();
    const { data: cashMgmtStats, loading: cashMgmtStatsLoading, error: cashMgmtStatsError } = useCashManagementStats();
    const { data: assetStats, loading: assetStatsLoading, error: assetStatsError } = useAssetStats();
    const { data: recurringExpenseStats, loading: recurringExpenseStatsLoading, error: recurringExpenseStatsError } = useRecurringExpenseFlowStats();
    const { data: profitFlowStats, loading: profitFlowLoading, error: profitFlowError } = useProfitFlowStats();

    // UI State
    const [drawerOpen, setDrawerOpen] = useState(false);
    const [drawerConfig, setDrawerConfig] = useState({ type: '', title: '' });

    const handleCardClick = (type, title) => {
        setDrawerConfig({ type, title });
        setDrawerOpen(true);
    };

    // Surface hook errors as transient toasts — persistent context lives in the
    // InlineAlert rendered inside the affected section below.
    useEffect(() => {
        if (statsError) toast.error(statsError);
    }, [statsError]); // eslint-disable-line react-hooks/exhaustive-deps
    useEffect(() => {
        if (taxStatsError) toast.error(taxStatsError);
    }, [taxStatsError]); // eslint-disable-line react-hooks/exhaustive-deps
    useEffect(() => {
        if (cashMgmtStatsError) toast.error(cashMgmtStatsError);
    }, [cashMgmtStatsError]); // eslint-disable-line react-hooks/exhaustive-deps
    useEffect(() => {
        if (assetStatsError) toast.error(assetStatsError);
    }, [assetStatsError]); // eslint-disable-line react-hooks/exhaustive-deps
    useEffect(() => {
        if (recurringExpenseStatsError) toast.error(recurringExpenseStatsError);
    }, [recurringExpenseStatsError]); // eslint-disable-line react-hooks/exhaustive-deps
    useEffect(() => {
        if (profitFlowError) toast.error(profitFlowError);
    }, [profitFlowError]); // eslint-disable-line react-hooks/exhaustive-deps

    const kpiItems = [
        {
            label: 'Cash in Hand',
            value: stats?.cash_in_hand,
            icon: Banknote,
            color: 'primary',
            onClick: () => handleCardClick('cashInHand', 'Cash in Hand Breakdown'),
        },
        {
            label: 'Net Profit',
            value: profitFlowStats?.total_net_profit,
            icon: BarChart3,
            color: 'green',
            subtitle: `${profitFlowStats?.months_finalized_count ?? 0} months finalized`,
            onClick: () => handleCardClick('monthlyProfit', 'Monthly Net Profit'),
        },
        {
            label: 'Customer Outstanding',
            value: stats?.customer_outstanding,
            icon: Receipt,
            color: 'amber',
            onClick: () => handleCardClick('customerOutstanding', 'Customer Outstanding Breakdown'),
        },
        {
            label: 'Supplier Outstanding',
            value: stats?.total_outstanding_payable,
            icon: Package,
            color: 'rose',
            onClick: () => handleCardClick('supplierOutstanding', 'Supplier Outstanding Breakdown'),
        },
    ];

    return (
        <div className="space-y-6">
            {/* Welcome Section */}
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="bg-gradient-to-r from-primary-700 to-accent-600 rounded-2xl p-6 text-white"
            >
                <h1 className="text-2xl font-bold">
                    Welcome back, {user?.first_name} {user?.last_name}!
                </h1>
                <div className="flex items-center gap-2 mt-1">
                    <Badge variant="info" className="bg-white/20 text-white">
                        {user?.role === 'superuser' ? 'Superuser' : 'Admin'}
                    </Badge>
                    <span className="text-white/80 text-sm">Full access</span>
                </div>
            </motion.div>

            {/* KPI Strip — the numbers that matter most, at a glance */}
            <KpiStrip items={kpiItems} loading={statsLoading || profitFlowLoading} />

            {/* Trend charts — always visible, not tucked behind an accordion */}
            <div className="space-y-6">
                <GrossProfitTrendChart />
                <NetProfitTrendChart />
            </div>

            {/* Grouped, collapsible stat sections */}
            <div className="space-y-4">
                <CollapsibleGroup
                    title="Sales & Profit"
                    icon={DollarSign}
                    description="Profit, receivables, and customer returns"
                    defaultOpen
                >
                    {statsError && <InlineAlert variant="error" message={statsError} />}
                    <ProfitSectionStats stats={stats} loading={statsLoading} onCardClick={handleCardClick} />
                    <ReceivablesSection stats={stats} loading={statsLoading} onCardClick={handleCardClick} />
                    <ReturnsSectionStats stats={stats} loading={statsLoading} onCardClick={handleCardClick} />
                </CollapsibleGroup>

                <CollapsibleGroup
                    title="Purchasing & Expenses"
                    icon={ShoppingCart}
                    description="Payables, expenses, and recurring costs"
                >
                    {statsError && <InlineAlert variant="error" message={statsError} />}
                    {recurringExpenseStatsError && <InlineAlert variant="error" message={recurringExpenseStatsError} />}
                    <PayablesSection stats={stats} loading={statsLoading} onCardClick={handleCardClick} />
                    <ExpensesSectionStats stats={stats} loading={statsLoading} onCardClick={handleCardClick} />
                    <RecurringExpensesSectionStats stats={recurringExpenseStats} loading={recurringExpenseStatsLoading} />
                </CollapsibleGroup>

                <CollapsibleGroup
                    title="Operations & Risk"
                    icon={AlertTriangle}
                    description="Lost inventory and tax position"
                >
                    {statsError && <InlineAlert variant="error" message={statsError} />}
                    {taxStatsError && <InlineAlert variant="error" message={taxStatsError} />}
                    <LostInventorySectionStats stats={stats} loading={statsLoading} onCardClick={handleCardClick} />
                    <TaxesSectionStats stats={taxStats} loading={taxStatsLoading} />
                </CollapsibleGroup>

                <CollapsibleGroup
                    title="Capital & Assets"
                    icon={Landmark}
                    description="Investor capital and fixed assets"
                >
                    {cashMgmtStatsError && <InlineAlert variant="error" message={cashMgmtStatsError} />}
                    {assetStatsError && <InlineAlert variant="error" message={assetStatsError} />}
                    <CashManagementSectionStats stats={cashMgmtStats} loading={cashMgmtStatsLoading} />
                    <AssetsSectionStats stats={assetStats} loading={assetStatsLoading} />
                </CollapsibleGroup>
            </div>

            {/* Breakdown Drawer */}
            <BreakdownDrawer
                isOpen={drawerOpen}
                onClose={() => setDrawerOpen(false)}
                title={drawerConfig.title}
                type={drawerConfig.type}
            />
        </div>
    );
};

export default AdminDashboard;
