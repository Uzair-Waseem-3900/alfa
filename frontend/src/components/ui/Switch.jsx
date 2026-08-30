import { motion } from 'framer-motion';
import PropTypes from 'prop-types';

// Simple on/off pill toggle — no other switch component exists yet in this
// codebase, this is the first one, following the same semantic-token /
// framer-motion conventions as Button/Card.
const Switch = ({ checked, onChange, disabled = false, loading = false }) => {
    return (
        <button
            type="button"
            role="switch"
            aria-checked={checked}
            disabled={disabled || loading}
            onClick={() => onChange(!checked)}
            className={`relative inline-flex h-7 w-12 flex-shrink-0 items-center rounded-full transition-colors duration-200 ${
                checked ? 'bg-success-500' : 'bg-neutral-300'
            } ${disabled || loading ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'}`}
        >
            <motion.span
                className="inline-block h-5 w-5 rounded-full bg-white shadow-sm"
                animate={{ x: checked ? 22 : 4 }}
                transition={{ type: 'spring', stiffness: 500, damping: 30 }}
            />
        </button>
    );
};

Switch.propTypes = {
    checked: PropTypes.bool.isRequired,
    onChange: PropTypes.func.isRequired,
    disabled: PropTypes.bool,
    loading: PropTypes.bool,
};

export default Switch;
