import { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import PropTypes from 'prop-types';
import { CheckCircle2, XCircle, AlertTriangle, Info, X } from 'lucide-react';

const VARIANTS = {
    success: {
        icon: CheckCircle2,
        classes: 'bg-success-50 border-success-500 text-success-700',
        iconClasses: 'text-success-500',
    },
    error: {
        icon: XCircle,
        classes: 'bg-error-50 border-error-500 text-error-700',
        iconClasses: 'text-error-500',
    },
    warning: {
        icon: AlertTriangle,
        classes: 'bg-warning-50 border-warning-500 text-warning-700',
        iconClasses: 'text-warning-500',
    },
    info: {
        icon: Info,
        classes: 'bg-info-50 border-info-500 text-info-700',
        iconClasses: 'text-info-500',
    },
};

const Toast = ({ variant = 'info', message, duration = 5000, onDismiss }) => {
    const [paused, setPaused] = useState(false);
    const remainingRef = useRef(duration);
    const startRef = useRef(null);
    const timerRef = useRef(null);

    useEffect(() => {
        const start = () => {
            startRef.current = Date.now();
            timerRef.current = setTimeout(onDismiss, remainingRef.current);
        };
        if (!paused) start();
        return () => clearTimeout(timerRef.current);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [paused]);

    const handleMouseEnter = () => {
        clearTimeout(timerRef.current);
        remainingRef.current -= Date.now() - startRef.current;
        setPaused(true);
    };

    const handleMouseLeave = () => setPaused(false);

    const { icon: Icon, classes, iconClasses } = VARIANTS[variant] || VARIANTS.info;

    return (
        <motion.div
            layout
            initial={{ opacity: 0, x: 40, scale: 0.95 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: 40, scale: 0.95, transition: { duration: 0.15 } }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            onMouseEnter={handleMouseEnter}
            onMouseLeave={handleMouseLeave}
            className={`flex items-start gap-3 w-full max-w-sm rounded-xl border-l-4 shadow-dropdown p-4 pr-3 ${classes}`}
        >
            <Icon className={`w-5 h-5 flex-shrink-0 mt-0.5 ${iconClasses}`} />
            <p className="text-sm font-medium flex-1 leading-snug">{message}</p>
            <button
                type="button"
                onClick={onDismiss}
                aria-label="Dismiss notification"
                className="p-1 rounded-lg hover:bg-black/5 transition-colors flex-shrink-0 cursor-pointer"
            >
                <X className="w-4 h-4" />
            </button>
        </motion.div>
    );
};

Toast.propTypes = {
    variant: PropTypes.oneOf(['success', 'error', 'warning', 'info']),
    message: PropTypes.node.isRequired,
    duration: PropTypes.number,
    onDismiss: PropTypes.func.isRequired,
};

export default Toast;
