import PropTypes from 'prop-types';
import { TrendingDown, Search, AlertTriangle } from 'lucide-react';
import StatCard from './StatCard';
import StatCardSkeleton from './StatCardSkeleton';

const LostInventorySectionStats = ({ stats, loading, onCardClick }) => {
    if (loading) {
        return (
            <div className="space-y-4">
                <h2 className="text-lg font-semibold text-neutral-900">Lost Inventory</h2>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <StatCardSkeleton color="red" />
                    <StatCardSkeleton color="green" />
                    <StatCardSkeleton color="orange" />
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            <h2 className="text-lg font-semibold text-neutral-900">Lost Inventory</h2>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <StatCard
                    label="Total Lost (Gross)"
                    value={stats?.total_lost_inventory_worth}
                    icon={TrendingDown}
                    color="red"
                    onClick={() => onCardClick('lostInventory', 'Lost Inventory Breakdown')}
                />
                <StatCard
                    label="Recovered (Found)"
                    value={stats?.total_lost_inventory_recovered}
                    icon={Search}
                    color="green"
                    onClick={() => onCardClick('lostInventory', 'Lost Inventory Breakdown')}
                />
                <StatCard
                    label="Net Lost Worth"
                    value={stats?.net_lost_inventory_worth}
                    icon={AlertTriangle}
                    color="orange"
                    onClick={() => onCardClick('lostInventory', 'Lost Inventory Breakdown')}
                />
            </div>
        </div>
    );
};

LostInventorySectionStats.propTypes = {
    stats: PropTypes.object,
    loading: PropTypes.bool,
    onCardClick: PropTypes.func.isRequired,
};

export default LostInventorySectionStats;
