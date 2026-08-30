import { motion } from 'framer-motion';
import PropTypes from 'prop-types';
import { Link } from 'react-router-dom';
import EntryTypeBadge from './EntryTypeBadge';
import BalanceDisplay from './BalanceDisplay';

const LedgerRow = ({ entry, index }) => {
    const isDebit = parseFloat(entry.debit) > 0;
    const isCredit = parseFloat(entry.credit) > 0;

    const formatAmount = (value) => {
        const num = typeof value === 'string' ? parseFloat(value) : value;
        if (isNaN(num) || num === 0) return '—';
        return num.toFixed(2);
    };

    const getReferenceLink = (reference) => {
        if (!reference) return null;
        if (reference.startsWith('PO-')) {
            return `/purchases/orders/${reference}`;
        }
        if (reference.startsWith('SPY-')) {
            return `/purchases/payments/ref/${reference}`;
        }
        if (reference.startsWith('RTN-')) {
            return `/purchases/returns`;
        }
        return null;
    };

    return (
        <motion.tr
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: index * 0.03 }}
            className="hover:bg-neutral-50 transition-colors"
        >
            <td className="px-4 py-3 text-sm text-neutral-700 whitespace-nowrap">
                {new Date(entry.date).toLocaleDateString()}
            </td>
            <td className="px-4 py-3 text-sm text-neutral-700">
                {entry.details}
            </td>
            <td className="px-4 py-3 text-sm font-mono text-neutral-500">
                {entry.reference}
            </td>
            <td className="px-4 py-3">
                <EntryTypeBadge type={entry.entry_type} />
            </td>
            <td className="px-4 py-3 text-sm font-mono text-right">
                {isDebit ? formatAmount(entry.debit) : '—'}
            </td>
            <td className="px-4 py-3 text-sm font-mono text-right">
                {isCredit ? formatAmount(entry.credit) : '—'}
            </td>
            <td className="px-4 py-3 text-sm font-mono text-right">
                <BalanceDisplay balance={entry.balance} />
            </td>
        </motion.tr>
    );
};

LedgerRow.propTypes = {
    entry: PropTypes.object.isRequired,
    index: PropTypes.number.isRequired,
};

export default LedgerRow;