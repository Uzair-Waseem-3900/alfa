import PropTypes from 'prop-types';
import BalanceDisplay from './BalanceDisplay';

// Default (supplier ledger) wording. Customer ledger callers pass their own
// `getBalanceMessage` since the debit/credit direction — and therefore what
// a positive/negative balance means — is the opposite for receivables.
const defaultGetBalanceMessage = (balance) => {
    const num = typeof balance === 'string' ? parseFloat(balance) : balance;
    if (isNaN(num)) return 'Account Settled';
    if (num === 0) return 'Account Settled';
    if (num > 0) return `Amount Payable: Rs. ${num.toFixed(2)} — You owe supplier this amount`;
    return `Supplier Credit: Rs. ${Math.abs(num).toFixed(2)} — Supplier owes you this amount`;
};

const ClosingBalanceSummary = ({ entries, getBalanceMessage = defaultGetBalanceMessage }) => {
    let totalDebits = 0;
    let totalCredits = 0;
    let closingBalance = 0;

    entries.forEach(entry => {
        const debit = parseFloat(entry.debit) || 0;
        const credit = parseFloat(entry.credit) || 0;
        totalDebits += debit;
        totalCredits += credit;
        closingBalance = parseFloat(entry.balance) || 0;
    });

    const netMovement = totalCredits - totalDebits;

    return (
        <div className="mt-6 p-4 bg-neutral-50 border-t border-neutral-200 rounded-b-xl">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                    <p className="text-xs text-neutral-500 font-medium uppercase tracking-wider">Total Debits</p>
                    <p className="text-lg font-mono font-semibold text-neutral-900">
                        {totalDebits.toFixed(2)}
                    </p>
                </div>
                <div>
                    <p className="text-xs text-neutral-500 font-medium uppercase tracking-wider">Total Credits</p>
                    <p className="text-lg font-mono font-semibold text-neutral-900">
                        {totalCredits.toFixed(2)}
                    </p>
                </div>
                <div>
                    <p className="text-xs text-neutral-500 font-medium uppercase tracking-wider">Net Movement</p>
                    <p className={`text-lg font-mono font-semibold ${netMovement >= 0 ? 'text-error-600' : 'text-success-600'}`}>
                        {netMovement >= 0 ? '+' : ''}{netMovement.toFixed(2)}
                    </p>
                </div>
                <div>
                    <p className="text-xs text-neutral-500 font-medium uppercase tracking-wider">Closing Balance</p>
                    <div className="text-lg font-mono font-semibold">
                        <BalanceDisplay balance={closingBalance} />
                    </div>
                    <p className="text-xs text-neutral-500 mt-1">
                        {getBalanceMessage(closingBalance)}
                    </p>
                </div>
            </div>
        </div>
    );
};

ClosingBalanceSummary.propTypes = {
    entries: PropTypes.array.isRequired,
    getBalanceMessage: PropTypes.func,
};

export default ClosingBalanceSummary;