import { motion } from 'framer-motion';
import PropTypes from 'prop-types';

const DatePicker = ({
    label,
    value,
    onChange,
    error,
    required,
    disabled,
    className = '',
    min,
    max,
    ...props
}) => {
    return (
        <motion.div
            className={`${className}`}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
        >
            {label && (
                <label className="block text-sm font-medium text-neutral-700 mb-1.5">
                    {label}
                    {required && <span className="text-error-500 ml-1">*</span>}
                </label>
            )}

            <input
                type="date"
                value={value}
                onChange={onChange}
                disabled={disabled}
                required={required}
                min={min}
                max={max}
                className={`
          w-full px-4 py-3 bg-white border rounded-xl 
          transition-all duration-300 outline-none
          ${error ? 'border-error-500 focus:ring-2 focus:ring-error-500/20' : 'border-neutral-200 focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500'}
          ${disabled ? 'bg-neutral-50 cursor-not-allowed opacity-60' : ''}
        `}
                {...props}
            />

            {error && (
                <p className="mt-1.5 text-sm text-error-500">{error}</p>
            )}
        </motion.div>
    );
};

DatePicker.propTypes = {
    label: PropTypes.string,
    value: PropTypes.string,
    onChange: PropTypes.func.isRequired,
    error: PropTypes.string,
    required: PropTypes.bool,
    disabled: PropTypes.bool,
    className: PropTypes.string,
    min: PropTypes.string,
    max: PropTypes.string,
};

export default DatePicker;