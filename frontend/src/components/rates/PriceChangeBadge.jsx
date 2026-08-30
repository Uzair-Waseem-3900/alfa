import { motion } from 'framer-motion';
import PropTypes from 'prop-types';

const PriceChangeBadge = ({ change }) => {
    if (change === 0 || !change) {
        return <span className="text-neutral-400 text-sm">No change</span>;
    }

    const isPositive = change > 0;
    const color = isPositive ? 'text-success-600' : 'text-error-600';
    const arrow = isPositive ? '↑' : '↓';

    return (
        <motion.span
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            className={`inline-flex items-center gap-1 font-medium ${color}`}
        >
            <span>{arrow}</span>
            <span>{Math.abs(change).toFixed(2)}</span>
        </motion.span>
    );
};

PriceChangeBadge.propTypes = {
    change: PropTypes.number,
};

export default PriceChangeBadge;