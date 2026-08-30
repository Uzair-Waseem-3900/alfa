import { motion } from 'framer-motion';
import PropTypes from 'prop-types';
import PriceChangeBadge from './PriceChangeBadge';
import LoadingSpinner from '../ui/LoadingSpinner';
import EmptyState from '../ui/EmptyState';

const PriceHistoryTable = ({ history, loading }) => {
    if (loading) {
        return (
            <div className="flex items-center justify-center py-12">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    if (history.length === 0) {
        return <EmptyState title="No price history" description="This product has no price change history yet." />;
    }

    // Calculate price changes
    const historyWithChanges = history.map((item, index) => {
        const prevPrice = index < history.length - 1 ? history[index + 1].selling_price : null;
        const change = prevPrice !== null ? parseFloat(item.selling_price) - parseFloat(prevPrice) : null;
        return { ...item, change };
    });

    return (
        <div className="overflow-x-auto">
            <table className="w-full">
                <thead>
                    <tr className="border-b border-neutral-200">
                        <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 uppercase tracking-wider">
                            Date & Time
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 uppercase tracking-wider">
                            Selling Price
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 uppercase tracking-wider">
                            Change
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 uppercase tracking-wider">
                            Changed By
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 uppercase tracking-wider">
                            Note
                        </th>
                    </tr>
                </thead>
                <tbody className="divide-y divide-neutral-100">
                    {historyWithChanges.map((item, index) => (
                        <motion.tr
                            key={item.id}
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            transition={{ delay: index * 0.05 }}
                            className="hover:bg-neutral-50 transition-colors"
                        >
                            <td className="px-4 py-3 text-sm text-neutral-700">
                                {new Date(item.changed_at).toLocaleString()}
                            </td>
                            <td className="px-4 py-3 text-sm font-medium text-primary-600">
                                {parseFloat(item.selling_price).toFixed(2)}
                            </td>
                            <td className="px-4 py-3 text-sm">
                                {item.change !== null ? (
                                    <PriceChangeBadge change={item.change} />
                                ) : (
                                    <span className="text-neutral-400 text-sm">Initial</span>
                                )}
                            </td>
                            <td className="px-4 py-3 text-sm text-neutral-700">
                                {item.changed_by || 'N/A'}
                            </td>
                            <td className="px-4 py-3 text-sm text-neutral-500">
                                {item.note || '-'}
                            </td>
                        </motion.tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
};

PriceHistoryTable.propTypes = {
    history: PropTypes.array.isRequired,
    loading: PropTypes.bool,
};

export default PriceHistoryTable;