import { motion } from 'framer-motion';
import PropTypes from 'prop-types';
import { Wallet, ClipboardList } from 'lucide-react';
import StatCard from './StatCard';
import StatCardSkeleton from './StatCardSkeleton';

const ExpensesSectionStats = ({ stats, loading, onCardClick }) => {
    if (loading) {
        return (
            <div className="space-y-4">
                <h2 className="text-lg font-semibold text-neutral-900">Expenses</h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <StatCardSkeleton color="orange" />
                    <StatCardSkeleton color="orange" />
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            <h2 className="text-lg font-semibold text-neutral-900">Expenses</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <StatCard
                    label="Total Expenses"
                    value={stats?.total_expenses_amount}
                    icon={Wallet}
                    color="orange"
                    onClick={() => onCardClick('expenses', 'Expenses Breakdown')}
                />
                <StatCard
                    label="Number of Expenses"
                    value={stats?.total_number_of_expenses}
                    icon={ClipboardList}
                    color="orange"
                    isCurrency={false}
                    onClick={() => onCardClick('expenses', 'Expenses Breakdown')}
                />
            </div>
        </div>
    );
};

ExpensesSectionStats.propTypes = {
    stats: PropTypes.object,
    loading: PropTypes.bool,
    onCardClick: PropTypes.func.isRequired,
};

export default ExpensesSectionStats;