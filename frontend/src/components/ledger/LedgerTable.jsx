import { motion } from 'framer-motion';
import PropTypes from 'prop-types';
import LedgerRow from './LedgerRow';
import EmptyState from '../ui/EmptyState';

const LedgerTable = ({ entries, loading }) => {
    if (loading) {
        return (
            <div className="overflow-x-auto">
                <table className="w-full">
                    <thead>
                        <tr className="border-b border-neutral-200">
                            <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 uppercase tracking-wider">Date</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 uppercase tracking-wider">Details</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 uppercase tracking-wider">Reference</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 uppercase tracking-wider">Type</th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-neutral-500 uppercase tracking-wider">Debit (PKR)</th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-neutral-500 uppercase tracking-wider">Credit (PKR)</th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-neutral-500 uppercase tracking-wider">Balance (PKR)</th>
                        </tr>
                    </thead>
                    <tbody>
                        {Array.from({ length: 5 }).map((_, i) => (
                            <tr key={i} className="animate-pulse">
                                <td className="px-4 py-3"><div className="h-4 bg-neutral-200 rounded w-24"></div></td>
                                <td className="px-4 py-3"><div className="h-4 bg-neutral-200 rounded w-48"></div></td>
                                <td className="px-4 py-3"><div className="h-4 bg-neutral-200 rounded w-20"></div></td>
                                <td className="px-4 py-3"><div className="h-5 bg-neutral-200 rounded w-16"></div></td>
                                <td className="px-4 py-3"><div className="h-4 bg-neutral-200 rounded w-16 ml-auto"></div></td>
                                <td className="px-4 py-3"><div className="h-4 bg-neutral-200 rounded w-16 ml-auto"></div></td>
                                <td className="px-4 py-3"><div className="h-4 bg-neutral-200 rounded w-16 ml-auto"></div></td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        );
    }

    if (entries.length === 0) {
        return <EmptyState title="No entries found" description="Try adjusting your filters" />;
    }

    return (
        <div className="overflow-x-auto">
            <table className="w-full">
                <thead className="bg-neutral-50 border-b border-neutral-200">
                    <tr>
                        <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 uppercase tracking-wider">Date</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 uppercase tracking-wider">Details</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 uppercase tracking-wider">Reference</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 uppercase tracking-wider">Type</th>
                        <th className="px-4 py-3 text-right text-xs font-medium text-neutral-500 uppercase tracking-wider">Debit (PKR)</th>
                        <th className="px-4 py-3 text-right text-xs font-medium text-neutral-500 uppercase tracking-wider">Credit (PKR)</th>
                        <th className="px-4 py-3 text-right text-xs font-medium text-neutral-500 uppercase tracking-wider">Balance (PKR)</th>
                    </tr>
                </thead>
                <tbody className="divide-y divide-neutral-100">
                    {entries.map((entry, index) => (
                        <LedgerRow key={index} entry={entry} index={index} />
                    ))}
                </tbody>
            </table>
        </div>
    );
};

LedgerTable.propTypes = {
    entries: PropTypes.array.isRequired,
    loading: PropTypes.bool,
};

export default LedgerTable;