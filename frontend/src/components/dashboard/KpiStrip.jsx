import PropTypes from 'prop-types';
import { motion } from 'framer-motion';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    if (isNaN(num)) return '0';
    if (Math.abs(num) >= 1000000) return `${(num / 1000000).toFixed(2)}M`;
    if (Math.abs(num) >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return num.toLocaleString('en-PK', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
};

const KPI_STYLES = {
    primary: 'from-primary-700 to-primary-800',
    green: 'from-emerald-600 to-emerald-700',
    amber: 'from-amber-500 to-amber-600',
    rose: 'from-rose-500 to-rose-600',
};

const KpiStripSkeleton = () => (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-24 rounded-2xl bg-neutral-100 animate-pulse" />
        ))}
    </div>
);

const KpiStrip = ({ items, loading }) => {
    if (loading) return <KpiStripSkeleton />;

    return (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {items.map((item, i) => (
                <motion.div
                    key={item.label}
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.05 }}
                    whileHover={item.onClick ? { y: -3 } : {}}
                    whileTap={item.onClick ? { scale: 0.98 } : {}}
                    onClick={item.onClick}
                    className={`relative overflow-hidden rounded-2xl p-5 text-white bg-gradient-to-br ${KPI_STYLES[item.color] || KPI_STYLES.primary} shadow-card ${item.onClick ? 'cursor-pointer' : ''}`}
                >
                    <div className="flex items-center justify-between">
                        <p className="text-sm font-medium text-white/80">{item.label}</p>
                        {item.icon && (
                            <div className="w-9 h-9 rounded-lg bg-white/15 flex items-center justify-center">
                                <item.icon className="w-4 h-4 text-white/90" />
                            </div>
                        )}
                    </div>
                    <p className="text-2xl font-bold mt-2 tracking-tight">
                        Rs. {fmt(item.value)}
                    </p>
                    {item.subtitle && (
                        <p className="text-xs text-white/70 mt-1">{item.subtitle}</p>
                    )}
                </motion.div>
            ))}
        </div>
    );
};

KpiStrip.propTypes = {
    items: PropTypes.arrayOf(PropTypes.shape({
        label: PropTypes.string.isRequired,
        value: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
        icon: PropTypes.elementType,
        color: PropTypes.oneOf(['primary', 'green', 'amber', 'rose']),
        subtitle: PropTypes.string,
        onClick: PropTypes.func,
    })).isRequired,
    loading: PropTypes.bool,
};

export default KpiStrip;
