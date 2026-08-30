import { motion } from 'framer-motion';
import PropTypes from 'prop-types';
import { CreditCard, Tag, ShoppingCart, Package } from 'lucide-react';
import StatCard from './StatCard';
import StatCardSkeleton from './StatCardSkeleton';

const PayablesSection = ({ stats, loading, onCardClick }) => {
    if (loading) {
        return (
            <div className="space-y-4">
                <h2 className="text-lg font-semibold text-neutral-900">Payables</h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                    <StatCardSkeleton color="green" />
                    <StatCardSkeleton color="red" />
                    <StatCardSkeleton color="blue" />
                    <StatCardSkeleton color="blue" />
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            <h2 className="text-lg font-semibold text-neutral-900">Payables</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <StatCard
                    label="Total Paid Payables"
                    value={stats?.total_paid_payables}
                    icon={CreditCard}
                    color="green"
                    onClick={() => onCardClick('paidPayables', 'Paid Payables Breakdown')}
                />
                <StatCard
                    label="Outstanding Payable"
                    value={stats?.total_outstanding_payable}
                    icon={Tag}
                    color="red"
                    onClick={() => onCardClick('supplierOutstanding', 'Supplier Outstanding Breakdown')}
                />
                <StatCard
                    label="Total Purchases Cash"
                    value={stats?.total_purchases_cash}
                    icon={ShoppingCart}
                    color="blue"
                    onClick={() => onCardClick('purchases', 'Purchases Breakdown')}
                />
                <StatCard
                    label="Total Purchases"
                    value={stats?.total_number_of_purchases}
                    icon={Package}
                    color="blue"
                    isCurrency={false}
                    onClick={() => onCardClick('purchases', 'Purchases Breakdown')}
                />
            </div>
        </div>
    );
};

PayablesSection.propTypes = {
    stats: PropTypes.object,
    loading: PropTypes.bool,
    onCardClick: PropTypes.func.isRequired,
};

export default PayablesSection;