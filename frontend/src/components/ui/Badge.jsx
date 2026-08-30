import { motion } from 'framer-motion';
import PropTypes from 'prop-types';

const Badge = ({ variant = 'default', children, className = '', ...props }) => {
    const variants = {
        default: 'bg-neutral-100 text-neutral-700',
        draft: 'bg-gray-100 text-gray-700',
        confirmed: 'bg-blue-100 text-blue-700',
        unpaid: 'bg-red-100 text-red-700',
        partial: 'bg-amber-100 text-amber-700',
        paid: 'bg-green-100 text-green-700',
        pending: 'bg-orange-100 text-orange-700',
        accepted: 'bg-green-100 text-green-700',
        success: 'bg-success-100 text-success-700',
        warning: 'bg-warning-100 text-warning-700',
        error: 'bg-error-100 text-error-700',
        info: 'bg-info-100 text-info-700',
    };

    return (
        <motion.span
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className={`
        inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium
        ${variants[variant] || variants.default}
        ${className}
      `}
            {...props}
        >
            {children}
        </motion.span>
    );
};

Badge.propTypes = {
    variant: PropTypes.oneOf([
        'default', 'draft', 'confirmed', 'unpaid', 'partial',
        'paid', 'pending', 'accepted', 'success', 'warning', 'error', 'info'
    ]),
    children: PropTypes.node,
    className: PropTypes.string,
};

export default Badge;