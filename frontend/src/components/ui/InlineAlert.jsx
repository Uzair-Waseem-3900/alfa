import PropTypes from 'prop-types';
import { AlertTriangle, AlertCircle, Info, CheckCircle2, RotateCw } from 'lucide-react';
import Button from './Button';

const VARIANTS = {
    error: {
        icon: AlertCircle,
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
    success: {
        icon: CheckCircle2,
        classes: 'bg-success-50 border-success-500 text-success-700',
        iconClasses: 'text-success-500',
    },
};

const InlineAlert = ({ variant = 'error', title, message, onRetry, retryLabel = 'Retry', className = '' }) => {
    const { icon: Icon, classes, iconClasses } = VARIANTS[variant] || VARIANTS.error;

    return (
        <div role={variant === 'error' ? 'alert' : 'status'} className={`flex items-start gap-3 rounded-xl border-l-4 p-4 ${classes} ${className}`}>
            <Icon className={`w-5 h-5 flex-shrink-0 mt-0.5 ${iconClasses}`} />
            <div className="flex-1 min-w-0">
                {title && <p className="text-sm font-semibold">{title}</p>}
                <p className="text-sm whitespace-pre-wrap">{message}</p>
            </div>
            {onRetry && (
                <Button variant="outline" size="sm" onClick={onRetry} icon={RotateCw} className="flex-shrink-0">
                    {retryLabel}
                </Button>
            )}
        </div>
    );
};

InlineAlert.propTypes = {
    variant: PropTypes.oneOf(['error', 'warning', 'info', 'success']),
    title: PropTypes.string,
    message: PropTypes.node.isRequired,
    onRetry: PropTypes.func,
    retryLabel: PropTypes.string,
    className: PropTypes.string,
};

export default InlineAlert;
