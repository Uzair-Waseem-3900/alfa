import { motion } from 'framer-motion';
import PropTypes from 'prop-types';

const Select = ({
    label,
    value,
    onChange,
    options,
    placeholder = 'Select...',
    error,
    required,
    disabled,
    className = '',
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

            <select
                value={value}
                onChange={onChange}
                disabled={disabled}
                required={required}
                className={`
          w-full px-4 py-3 bg-white border rounded-xl 
          transition-all duration-300 outline-none
          ${error ? 'border-error-500 focus:ring-2 focus:ring-error-500/20' : 'border-neutral-200 focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500'}
          ${disabled ? 'bg-neutral-50 cursor-not-allowed opacity-60' : ''}
        `}
                {...props}
            >
                <option value="">{placeholder}</option>
                {options.map((option) => (
                    <option key={option.value} value={option.value}>
                        {option.label}
                    </option>
                ))}
            </select>

            {error && (
                <p className="mt-1.5 text-sm text-error-500">{error}</p>
            )}
        </motion.div>
    );
};

Select.propTypes = {
    label: PropTypes.string,
    value: PropTypes.any,
    onChange: PropTypes.func.isRequired,
    options: PropTypes.arrayOf(
        PropTypes.shape({
            value: PropTypes.any.isRequired,
            label: PropTypes.string.isRequired,
        })
    ).isRequired,
    placeholder: PropTypes.string,
    error: PropTypes.string,
    required: PropTypes.bool,
    disabled: PropTypes.bool,
    className: PropTypes.string,
};

export default Select;