import PropTypes from 'prop-types';
import { Banknote, TrendingUp, Package, DollarSign } from 'lucide-react';
import StatCard from './StatCard';
import StatCardSkeleton from './StatCardSkeleton';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toLocaleString('en-PK', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

const ProfitSectionStats = ({ stats, loading, onCardClick }) => {
    if (loading) {
        return (
            <div className="space-y-4">
                <h2 className="text-lg font-semibold text-neutral-900">Profit</h2>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                    <StatCardSkeleton color="primary" />
                    <StatCardSkeleton color="green" />
                    <StatCardSkeleton color="amber" />
                    <StatCardSkeleton color="green" />
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            <h2 className="text-lg font-semibold text-neutral-900">Profit</h2>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <StatCard
                    label="Cash in Hand"
                    value={stats?.cash_in_hand}
                    icon={Banknote}
                    color="primary"
                    onClick={() => onCardClick('cashInHand', 'Cash in Hand Breakdown')}
                />
                <StatCard
                    label="Net Revenue"
                    value={stats?.net_invoice_revenue}
                    icon={TrendingUp}
                    color="green"
                    subtitle={`Before returns: Rs. ${fmt(stats?.total_invoice_revenue)}`}
                    onClick={() => onCardClick('profit', 'Profit Breakdown')}
                />
                <StatCard
                    label="Net COGS"
                    value={stats?.net_invoice_cogs}
                    icon={Package}
                    color="amber"
                    subtitle={`Before returns: Rs. ${fmt(stats?.total_invoice_cogs)}`}
                    onClick={() => onCardClick('profit', 'Profit Breakdown')}
                />
                <StatCard
                    label="Net Gross Profit"
                    value={stats?.net_gross_profit}
                    icon={DollarSign}
                    color="green"
                    subtitle={`Gross (before returns): Rs. ${fmt(stats?.total_gross_profit)}`}
                    onClick={() => onCardClick('profit', 'Profit Breakdown')}
                />
            </div>
        </div>
    );
};

ProfitSectionStats.propTypes = {
    stats: PropTypes.object,
    loading: PropTypes.bool,
    onCardClick: PropTypes.func.isRequired,
};

export default ProfitSectionStats;
