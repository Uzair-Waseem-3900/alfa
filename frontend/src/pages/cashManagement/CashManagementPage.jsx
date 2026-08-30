import { Link } from 'react-router-dom';
import {
    Wallet, TrendingDown, TrendingUp, Scale, Users, ArrowDownCircle,
    ArrowUpCircle, Landmark, HandCoins, ChevronRight, ShieldAlert,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useCashManagementStats } from '../../hooks/useCashManagement';
import Card from '../../components/ui/Card';
import Button from '../../components/ui/Button';
import InlineAlert from '../../components/ui/InlineAlert';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const TONES = {
    neutral: { text: 'text-neutral-900', bg: 'bg-neutral-100', icon: 'text-neutral-500' },
    red: { text: 'text-error-600', bg: 'bg-error-50', icon: 'text-error-500' },
    green: { text: 'text-success-600', bg: 'bg-success-50', icon: 'text-success-500' },
    amber: { text: 'text-warning-700', bg: 'bg-warning-50', icon: 'text-warning-600' },
    blue: { text: 'text-info-600', bg: 'bg-info-50', icon: 'text-info-500' },
    purple: { text: 'text-purple-600', bg: 'bg-purple-50', icon: 'text-purple-500' },
    orange: { text: 'text-orange-600', bg: 'bg-orange-50', icon: 'text-orange-500' },
    teal: { text: 'text-teal-600', bg: 'bg-teal-50', icon: 'text-teal-500' },
};

const StatBox = ({ label, value, tone = 'neutral', subtitle, icon: Icon, isCount = false }) => {
    const t = TONES[tone] || TONES.neutral;
    return (
        <Card className="p-5" hover={false}>
            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                    <p className="text-xs font-medium text-neutral-500 mb-1.5 truncate">{label}</p>
                    <p className={`text-xl font-bold tracking-tight ${t.text}`}>
                        {isCount ? (value ?? 0) : `Rs. ${fmt(value)}`}
                    </p>
                    {subtitle && <p className="text-xs text-neutral-400 mt-1">{subtitle}</p>}
                </div>
                {Icon && (
                    <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${t.bg}`}>
                        <Icon className={`w-5 h-5 ${t.icon}`} />
                    </div>
                )}
            </div>
        </Card>
    );
};

const SkeletonStat = () => (
    <div className="p-5 rounded-2xl bg-white shadow-card animate-pulse">
        <div className="h-3 w-24 bg-neutral-200 rounded mb-3" />
        <div className="h-6 w-32 bg-neutral-200 rounded mb-2" />
        <div className="h-2 w-20 bg-neutral-100 rounded" />
    </div>
);

const SectionHeading = ({ icon: Icon, children }) => (
    <div className="flex items-center gap-2 mb-3">
        <Icon className="w-5 h-5 text-primary-600" />
        <h2 className="text-lg font-semibold text-neutral-900">{children}</h2>
    </div>
);

const NAV_CARDS = [
    {
        to: '/cash-management/adjustments',
        icon: Scale,
        title: 'Cash Adjustments',
        description: "Record cash that's been lost (theft, miscount, misplaced) or found/recovered.",
        cta: 'View Cash Adjustments',
    },
    {
        to: '/cash-management/investors',
        icon: Users,
        title: 'Investors',
        description: 'Manage investors and record their investments and withdrawals.',
        cta: 'View Investors',
    },
    {
        to: '/cash-management/growth-history',
        icon: TrendingUp,
        title: 'Growth History',
        description: 'Browse every monthly compounding entry ever posted, across all investors.',
        cta: 'View Growth History',
    },
    {
        to: '/cash-management/owner-transactions',
        icon: Landmark,
        title: 'Owner Transactions',
        description: 'Record money the owner puts in or draws out of the business.',
        cta: 'View Owner Transactions',
    },
];

const CashManagementPage = () => {
    const { user } = useAuth();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const { data: stats, loading: statsLoading, error: statsError, refetch: refetchStats } = useCashManagementStats();

    if (!isAdmin) {
        return (
            <div className="text-center py-16">
                <div className="w-14 h-14 rounded-full bg-error-50 flex items-center justify-center mx-auto mb-4">
                    <ShieldAlert className="w-7 h-7 text-error-500" />
                </div>
                <h2 className="text-2xl font-semibold text-neutral-900">Access Denied</h2>
                <p className="text-neutral-500 mt-2">Only admins or superusers can view cash management.</p>
            </div>
        );
    }

    return (
        <div className="space-y-8">
            <div className="flex items-center gap-3">
                <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-primary-700 to-accent-600 flex items-center justify-center shadow-lg shadow-primary-900/20 flex-shrink-0">
                    <Wallet className="w-5 h-5 text-white" />
                </div>
                <div>
                    <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900">Cash Management</h1>
                    <p className="text-neutral-500 mt-0.5">
                        Reconcile physical cash discrepancies and manage investor capital.
                    </p>
                </div>
            </div>

            {statsError && !statsLoading && (
                <InlineAlert
                    variant="error"
                    title="Couldn't load cash management stats"
                    message={statsError}
                    onRetry={refetchStats}
                />
            )}

            <div>
                <SectionHeading icon={Scale}>Cash Reconciliation</SectionHeading>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    {statsLoading ? (
                        <>
                            <SkeletonStat /><SkeletonStat /><SkeletonStat />
                        </>
                    ) : (
                        <>
                            <StatBox label="Total Cash Lost" value={stats?.total_cash_lost} tone="red" icon={ArrowDownCircle} subtitle="All-time, gross" />
                            <StatBox label="Total Cash Recovered" value={stats?.total_cash_recovered} tone="green" icon={ArrowUpCircle} subtitle="All-time, gross" />
                            <StatBox label="Net Cash Lost" value={stats?.net_cash_lost} tone="amber" icon={TrendingDown} subtitle="Lost minus recovered" />
                        </>
                    )}
                </div>
            </div>

            <div>
                <SectionHeading icon={Users}>Investor Capital</SectionHeading>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                    {statsLoading ? (
                        <>
                            <SkeletonStat /><SkeletonStat /><SkeletonStat /><SkeletonStat />
                        </>
                    ) : (
                        <>
                            <StatBox label="Total Invested" value={stats?.total_investor_capital} tone="blue" icon={ArrowUpCircle} subtitle="All-time, gross" />
                            <StatBox label="Total Withdrawn" value={stats?.total_investor_withdrawn} tone="orange" icon={ArrowDownCircle} subtitle="All-time, gross" />
                            <StatBox label="Net Investor Capital" value={stats?.net_investor_capital} tone="purple" icon={Scale} subtitle="Currently in the business" />
                            <StatBox label="Total Investor Net Worth" value={stats?.total_investor_net_worth} tone="teal" icon={TrendingUp} subtitle="Theoretical, growth-compounded" />
                        </>
                    )}
                </div>
            </div>

            <InlineAlert
                variant="info"
                message="Investor capital is equity financing — it increases cash in hand but is never counted as revenue or profit. It's tracked separately so it can be used later to calculate each investor's share once net (actual) profit is tracked, not just gross profit. Net Worth includes each investor's compounded growth and is informational only — never used for withdrawal validation."
            />

            <div>
                <SectionHeading icon={Landmark}>Owner Capital</SectionHeading>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
                    {statsLoading ? (
                        <>
                            <SkeletonStat /><SkeletonStat /><SkeletonStat /><SkeletonStat /><SkeletonStat />
                        </>
                    ) : (
                        <>
                            <StatBox label="Total Contributions" value={stats?.total_owner_contributions} tone="blue" icon={ArrowUpCircle} subtitle="All-time, gross" />
                            <StatBox label="Number of Contributions" value={stats?.total_owner_contributions_count} isCount icon={HandCoins} subtitle="All-time count" />
                            <StatBox label="Total Drawings" value={stats?.total_owner_drawings} tone="orange" icon={ArrowDownCircle} subtitle="All-time, gross" />
                            <StatBox label="Number of Drawings" value={stats?.total_owner_withdrawals_count} isCount icon={HandCoins} subtitle="All-time count" />
                            <StatBox
                                label="Net Owner Capital"
                                value={stats?.net_owner_capital}
                                tone={parseFloat(stats?.net_owner_capital) < 0 ? 'red' : 'purple'}
                                icon={Scale}
                                subtitle="Contributions minus drawings"
                            />
                        </>
                    )}
                </div>
            </div>

            <InlineAlert
                variant="warning"
                message="Owner drawings are not capped by contributions — the owner can draw out more than they've deposited, financed by the business's profits. A negative net owner capital is normal."
            />

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {NAV_CARDS.map(({ to, icon: Icon, title, description, cta }) => (
                    <Card key={to} className="p-6 flex flex-col">
                        <div className="w-10 h-10 rounded-xl bg-primary-50 flex items-center justify-center mb-3">
                            <Icon className="w-5 h-5 text-primary-600" />
                        </div>
                        <h3 className="font-semibold text-neutral-900 mb-1.5">{title}</h3>
                        <p className="text-sm text-neutral-500 mb-4 flex-1">{description}</p>
                        <Link to={to}>
                            <Button variant="secondary" className="w-full">
                                {cta}
                                <ChevronRight className="w-4 h-4" />
                            </Button>
                        </Link>
                    </Card>
                ))}
            </div>
        </div>
    );
};

export default CashManagementPage;
