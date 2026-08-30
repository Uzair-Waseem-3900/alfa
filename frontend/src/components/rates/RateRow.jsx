import { motion } from 'framer-motion';
import PropTypes from 'prop-types';
import Button from '../ui/Button';
import NoRateBadge from './NoRateBadge';

const RateRow = ({
    product,
    rate,
    isAdmin,
    onEdit,
    onViewHistory,
    index
}) => {
    const hasRate = !!rate;
    const isRecentlyUpdated = hasRate && rate.updated_at &&
        (new Date() - new Date(rate.updated_at)) < 24 * 60 * 60 * 1000;

    return (
        <motion.tr
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: index * 0.05 }}
            className={`hover:bg-neutral-50 transition-colors ${isRecentlyUpdated ? 'bg-amber-50/30' : ''
                }`}
        >
            <td className="px-4 py-3 text-sm font-medium text-neutral-900">
                {product.code}
            </td>
            <td className="px-4 py-3 text-sm text-neutral-700">
                {product.name}
            </td>
            <td className="px-4 py-3 text-sm text-neutral-700">
                {product.category?.name || 'N/A'}
            </td>
            <td className="px-4 py-3 text-sm">
                {hasRate ? (
                    <span className="font-semibold text-primary-600">
                        {parseFloat(rate.selling_price).toFixed(2)}
                    </span>
                ) : (
                    <NoRateBadge />
                )}
            </td>
            <td className="px-4 py-3 text-sm text-neutral-500">
                {hasRate ? rate.updated_by || 'N/A' : 'N/A'}
            </td>
            <td className="px-4 py-3 text-sm text-neutral-500">
                {hasRate && rate.updated_at ? new Date(rate.updated_at).toLocaleString() : 'N/A'}
            </td>
            <td className="px-4 py-3">
                <div className="flex gap-2">
                    {isAdmin && (
                        <Button
                            size="sm"
                            variant={hasRate ? 'secondary' : 'primary'}
                            onClick={() => onEdit(product, rate)}
                        >
                            {hasRate ? 'Edit Price' : 'Set Price'}
                        </Button>
                    )}
                    <Button
                        size="sm"
                        variant="outline"
                        onClick={() => onViewHistory(product)}
                    >
                        History
                    </Button>
                </div>
            </td>
        </motion.tr>
    );
};

RateRow.propTypes = {
    product: PropTypes.object.isRequired,
    rate: PropTypes.object,
    isAdmin: PropTypes.bool.isRequired,
    onEdit: PropTypes.func.isRequired,
    onViewHistory: PropTypes.func.isRequired,
    index: PropTypes.number.isRequired,
};

export default RateRow;