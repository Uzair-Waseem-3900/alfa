import PropTypes from 'prop-types';

const BalanceDisplay = ({ balance }) => {
    const num = typeof balance === 'string' ? parseFloat(balance) : balance;

    if (isNaN(num)) {
        return <span className="text-neutral-400 font-mono">0.00</span>;
    }

    const absBalance = Math.abs(num);
    const displayValue = absBalance.toFixed(2);

    if (num === 0) {
        return <span className="text-neutral-400 font-mono">0.00</span>;
    }

    if (num > 0) {
        return (
            <span className="text-error-600 font-mono font-semibold">
                {displayValue}
            </span>
        );
    }

    return (
        <span className="text-success-600 font-mono font-semibold">
            ({displayValue})
        </span>
    );
};

BalanceDisplay.propTypes = {
    balance: PropTypes.oneOfType([PropTypes.string, PropTypes.number]).isRequired,
};

export default BalanceDisplay;