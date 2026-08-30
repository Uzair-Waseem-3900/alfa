import PropTypes from 'prop-types';
import RateRow from './RateRow';
import LoadingSpinner from '../ui/LoadingSpinner';
import EmptyState from '../ui/EmptyState';

const RateTable = ({
    rates,
    isAdmin,
    onEdit,
    onViewHistory,
    loading
}) => {
    if (loading) {
        return (
            <div className="flex items-center justify-center py-12">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    if (rates.length === 0) {
        return <EmptyState title="No rates found" description="Try adjusting your search or filters" />;
    }

    return (
        <div className="overflow-x-auto">
            <table className="w-full">
                <thead>
                    <tr className="border-b border-neutral-200">
                        <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 uppercase tracking-wider">
                            Product Code
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 uppercase tracking-wider">
                            Product Name
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 uppercase tracking-wider">
                            Category
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 uppercase tracking-wider">
                            Selling Price
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 uppercase tracking-wider">
                            Last Updated By
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 uppercase tracking-wider">
                            Last Updated
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 uppercase tracking-wider">
                            Actions
                        </th>
                    </tr>
                </thead>
                <tbody className="divide-y divide-neutral-100">
                    {rates.map((item, index) => (
                        <RateRow
                            key={item.product.id}
                            product={item.product}
                            rate={item.rate}
                            isAdmin={isAdmin}
                            onEdit={onEdit}
                            onViewHistory={onViewHistory}
                            index={index}
                        />
                    ))}
                </tbody>
            </table>
        </div>
    );
};

RateTable.propTypes = {
    rates: PropTypes.array.isRequired,
    isAdmin: PropTypes.bool.isRequired,
    onEdit: PropTypes.func.isRequired,
    onViewHistory: PropTypes.func.isRequired,
    loading: PropTypes.bool,
};

export default RateTable;