import { motion } from 'framer-motion';
import PropTypes from 'prop-types';
import Card from '../ui/Card';

const StatCard = ({
    label,
    value,
    icon: Icon,
    color = 'primary',
    isCurrency = true,
    onClick,
    loading = false,
    subtitle,
}) => {
    const colors = {
        primary: 'border-l-4 border-primary-500',
        green: 'border-l-4 border-success-500',
        amber: 'border-l-4 border-warning-500',
        red: 'border-l-4 border-error-500',
        blue: 'border-l-4 border-info-500',
        orange: 'border-l-4 border-orange-500',
        purple: 'border-l-4 border-purple-500',
    };

    // Abbreviated to K/M/B so the box width stays consistent as real data
    // grows over months/years — a raw "Rs. 7,279,266.79" is roughly 3x longer
    // than "Rs. 7.28M" and would otherwise stretch/wrap the card. The exact
    // figure is still available via the title tooltip on hover.
    const formatCurrency = (val) => {
        const num = typeof val === 'string' ? parseFloat(val) : val;
        if (isNaN(num)) return 'Rs. 0.00';
        const sign = num < 0 ? '-' : '';
        const abs = Math.abs(num);
        if (abs >= 1_000_000_000) return `${sign}Rs. ${(abs / 1_000_000_000).toFixed(2)}B`;
        if (abs >= 1_000_000) return `${sign}Rs. ${(abs / 1_000_000).toFixed(2)}M`;
        if (abs >= 100_000) return `${sign}Rs. ${(abs / 1_000).toFixed(1)}K`;
        return `${sign}Rs. ${abs.toLocaleString('en-PK', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    };

    const formatFullCurrency = (val) => {
        const num = typeof val === 'string' ? parseFloat(val) : val;
        if (isNaN(num)) return 'Rs. 0.00';
        return `Rs. ${num.toLocaleString('en-PK', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    };

    const formatNumber = (val) => {
        const num = typeof val === 'string' ? parseInt(val) : val;
        if (isNaN(num)) return '0';
        return num.toLocaleString('en-PK');
    };

    const displayValue = loading ? '...' : isCurrency ? formatCurrency(value) : formatNumber(value);
    const fullValueTitle = loading ? undefined : isCurrency ? formatFullCurrency(value) : formatNumber(value);

    return (
        <motion.div
            whileHover={{ y: -4, transition: { duration: 0.2 } }}
            whileTap={{ scale: 0.98 }}
            className={`h-full ${onClick ? 'cursor-pointer' : 'cursor-default'}`}
            onClick={onClick}
        >
            <Card className={`p-5 h-full min-h-[112px] ${colors[color] || colors.primary} hover:shadow-card-hover transition-all`}>
                <div className="flex items-start justify-between h-full">
                    <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-neutral-500 truncate">{label}</p>
                        <p
                            className="text-2xl font-bold text-neutral-900 mt-1 truncate"
                            title={fullValueTitle}
                        >
                            {displayValue}
                        </p>
                        {subtitle && <p className="text-xs text-neutral-400 mt-1 truncate">{subtitle}</p>}
                    </div>
                    {Icon && (
                        <div className="w-10 h-10 rounded-xl bg-neutral-100 flex items-center justify-center flex-shrink-0">
                            <Icon className="w-5 h-5 text-neutral-500" />
                        </div>
                    )}
                </div>
            </Card>
        </motion.div>
    );
};

StatCard.propTypes = {
    label: PropTypes.string.isRequired,
    value: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
    icon: PropTypes.elementType,
    color: PropTypes.oneOf(['primary', 'green', 'amber', 'red', 'blue', 'orange', 'purple']),
    isCurrency: PropTypes.bool,
    onClick: PropTypes.func,
    loading: PropTypes.bool,
    subtitle: PropTypes.string,
};

export default StatCard;