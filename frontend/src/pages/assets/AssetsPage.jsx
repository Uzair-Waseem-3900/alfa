import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
    ShieldAlert, Building2, Tag, Package, Trash2,
    Wallet, TrendingDown, TrendingUp, Layers, ArrowRight, Receipt,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useAssetStats } from '../../hooks/useAssets';
import Card from '../../components/ui/Card';
import Button from '../../components/ui/Button';
import InlineAlert from '../../components/ui/InlineAlert';

// Exact figures, never abbreviated. These tiles show real money — the cost of
// your assets, what they're worth now, what's been written off — and "2.65M"
// hides up to Rs 5,000 of difference behind a rounded label, which is not
// something a financial figure should do. Thousands separators keep a
// seven-figure number readable without losing a single rupee.
const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    if (isNaN(num)) return '0.00';
    return num.toLocaleString('en-PK', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

// Counts are whole numbers, but still get separators so a four-figure asset
// count doesn't read as a mistake.
const fmtCount = (value) => {
    const num = Number(value);
    return isNaN(num) ? '0' : num.toLocaleString('en-PK');
};

const KPI_STYLES = {
    blue: 'from-primary-700 to-accent-600',
    purple: 'from-purple-600 to-purple-700',
    orange: 'from-amber-500 to-orange-600',
    neutral: 'from-neutral-600 to-neutral-700',
    green: 'from-success-600 to-emerald-700',
    red: 'from-error-500 to-rose-600',
};

const StatTile = ({ label, value, tone = 'blue', subtitle, icon: Icon, isCount = false, index = 0 }) => (
    <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: index * 0.05 }}
        className={`relative overflow-hidden rounded-2xl p-5 text-white bg-gradient-to-br ${KPI_STYLES[tone]} shadow-card`}
    >
        <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-white/80">{label}</p>
            {Icon && (
                <div className="w-9 h-9 rounded-lg bg-white/15 flex items-center justify-center">
                    <Icon className="w-4 h-4 text-white/90" />
                </div>
            )}
        </div>
        {/* text-xl on narrow tiles so a full seven-figure amount still fits on
            one line; tabular-nums keeps the digits aligned tile to tile. */}
        <p className="text-xl lg:text-2xl font-bold mt-2 tracking-tight tabular-nums break-words">
            {isCount ? fmtCount(value) : `Rs. ${fmt(value)}`}
        </p>
        {subtitle && <p className="text-xs text-white/70 mt-1">{subtitle}</p>}
    </motion.div>
);

const StatsSkeleton = () => (
    <>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {[0, 1, 2].map((i) => <div key={i} className="h-24 rounded-2xl bg-neutral-100 animate-pulse" />)}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {[0, 1, 2].map((i) => <div key={i} className="h-24 rounded-2xl bg-neutral-100 animate-pulse" />)}
        </div>
    </>
);

const NavCard = ({ to, icon: Icon, title, description, cta, index }) => (
    <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 + index * 0.05 }}
    >
        <Card className="p-6 h-full flex flex-col">
            <div className="w-11 h-11 rounded-xl bg-primary-50 flex items-center justify-center mb-4">
                <Icon className="w-5.5 h-5.5 text-primary-700" />
            </div>
            <h3 className="font-semibold text-neutral-900 mb-1.5">{title}</h3>
            <p className="text-sm text-neutral-500 mb-5 flex-1">{description}</p>
            <Link to={to}>
                <Button variant="secondary" icon={ArrowRight} className="[&>svg]:order-last">
                    {cta}
                </Button>
            </Link>
        </Card>
    </motion.div>
);

const AssetsPage = () => {
    const { user } = useAuth();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const { data: stats, loading: statsLoading, error: statsError, refetch: refetchStats } = useAssetStats();

    if (!isAdmin) {
        return (
            <div className="text-center py-16">
                <div className="w-16 h-16 rounded-full bg-error-50 flex items-center justify-center mx-auto mb-4">
                    <ShieldAlert className="w-8 h-8 text-error-500" />
                </div>
                <h2 className="text-2xl font-semibold text-neutral-900">Access Denied</h2>
                <p className="text-neutral-500 mt-2">Only admins or superusers can view assets.</p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex items-start gap-3">
                <div className="w-11 h-11 rounded-xl bg-primary-50 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <Building2 className="w-5.5 h-5.5 text-primary-700" />
                </div>
                <div>
                    <h1 className="text-3xl font-bold text-neutral-900">Fixed Assets</h1>
                    <p className="text-neutral-500 mt-1">
                        Track equipment, vehicles, and land — depreciation and revaluation, computed automatically.
                    </p>
                </div>
            </div>

            {statsError && (
                <InlineAlert variant="error" message={statsError} onRetry={refetchStats} />
            )}

            {statsLoading ? (
                <StatsSkeleton />
            ) : (
                <>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                        <StatTile index={0} label="Total Asset Cost" value={stats?.total_asset_cost} tone="blue" subtitle="Active assets, at cost" icon={Wallet} />
                        <StatTile index={1} label="Total Current Worth" value={stats?.total_current_worth} tone="purple" subtitle="Book value today" icon={Layers} />
                        <StatTile index={2} label="Accumulated Depreciation" value={stats?.total_accumulated_depreciation} tone="orange" subtitle="Cost minus current worth" icon={TrendingDown} />
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                        <StatTile index={3} label="Assets Disposed" value={stats?.total_disposed_count} tone="neutral" subtitle="Scrapped + sold, all-time" icon={Trash2} isCount />
                        <StatTile index={4} label="Total Gain on Disposal" value={stats?.total_gain_on_disposal} tone="green" subtitle="Sold above book value" icon={TrendingUp} />
                        <StatTile index={5} label="Total Loss on Disposal" value={stats?.total_loss_on_disposal} tone="red" subtitle="Sold below book value" icon={TrendingDown} />
                    </div>
                </>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <NavCard
                    index={0}
                    to="/assets/categories"
                    icon={Tag}
                    title="Categories"
                    description="Set up depreciation or revaluation categories (e.g. Furniture 15%, Land — revaluation)."
                    cta="View Categories"
                />
                <NavCard
                    index={1}
                    to="/assets/items"
                    icon={Package}
                    title="Assets"
                    description="Register existing or newly purchased assets and track their worth over time."
                    cta="View Assets"
                />
                <NavCard
                    index={2}
                    to="/assets/disposals"
                    icon={Trash2}
                    title="Disposals"
                    description="Audit trail of every asset that's been scrapped or sold."
                    cta="View Disposals"
                />
                <NavCard
                    index={3}
                    to="/assets/payments"
                    icon={Receipt}
                    title="Payments"
                    description="Every real cash movement from assets — purchases and sales, in one place."
                    cta="View Payments"
                />
            </div>
        </div>
    );
};

export default AssetsPage;
