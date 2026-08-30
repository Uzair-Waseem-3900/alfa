import PropTypes from 'prop-types';
import { RotateCcw, Undo2 } from 'lucide-react';
import StatCard from './StatCard';
import StatCardSkeleton from './StatCardSkeleton';

const ReturnsSectionStats = ({ stats, loading, onCardClick }) => {
    if (loading) {
        return (
            <div className="space-y-4">
                <h2 className="text-lg font-semibold text-neutral-900">Returns</h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                    <StatCardSkeleton color="orange" />
                    <StatCardSkeleton color="orange" />
                    <StatCardSkeleton color="orange" />
                    <StatCardSkeleton color="orange" />
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            <h2 className="text-lg font-semibold text-neutral-900">Returns</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <StatCard
                    label="Supplier Returns Value"
                    value={stats?.total_purchase_returns_value}
                    icon={RotateCcw}
                    color="orange"
                    onClick={() => onCardClick('purchaseReturns', 'Supplier Returns Breakdown')}
                />
                <StatCard
                    label="Supplier Returns COGS"
                    value={stats?.total_purchase_returns_cogs}
                    icon={RotateCcw}
                    color="orange"
                    onClick={() => onCardClick('purchaseReturns', 'Supplier Returns Breakdown')}
                />
                <StatCard
                    label="Customer Returns Value"
                    value={stats?.total_customer_returns_value}
                    icon={Undo2}
                    color="orange"
                    onClick={() => onCardClick('customerReturns', 'Customer Returns Breakdown')}
                />
                <StatCard
                    label="Customer Returns COGS"
                    value={stats?.total_customer_returns_cogs}
                    icon={Undo2}
                    color="orange"
                    onClick={() => onCardClick('customerReturns', 'Customer Returns Breakdown')}
                />
            </div>
        </div>
    );
};

ReturnsSectionStats.propTypes = {
    stats: PropTypes.object,
    loading: PropTypes.bool,
    onCardClick: PropTypes.func.isRequired,
};

export default ReturnsSectionStats;
