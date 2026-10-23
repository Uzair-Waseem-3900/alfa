import PropTypes from 'prop-types';
import { useRecoveryRecords } from '../../hooks/useBilling';
import Modal from '../ui/Modal';
import Table from '../ui/Table';
import Pagination from '../ui/Pagination';
import LoadingSpinner from '../ui/LoadingSpinner';
import InlineAlert from '../ui/InlineAlert';
import EmptyState from '../ui/EmptyState';

const formatAmount = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : value;
    return isNaN(num) ? '0.00' : num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

const columns = [
    { key: 'customer_name', label: 'Customer' },
    { key: 'bill_number', label: 'Bill #', width: '140px' },
    {
        key: 'amount',
        label: 'Amount (PKR)',
        render: (value) => <span className="font-semibold text-neutral-900">Rs. {formatAmount(value)}</span>,
    },
];

// Lives inside the modal so the records are only fetched while it is open.
const RecoveryRecordsTable = ({ total, count }) => {
    const { data: records, meta, loading, error, setPage, refetch } = useRecoveryRecords();

    return (
        <div className="space-y-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="text-sm text-neutral-500">
                    {count.toLocaleString()} {count === 1 ? 'payment' : 'payments'} recorded
                </p>
                <p className="text-lg font-bold text-neutral-900">Total: Rs. {formatAmount(total)}</p>
            </div>

            {error && <InlineAlert variant="error" message={error} onRetry={refetch} />}

            {loading ? (
                <div className="flex items-center justify-center py-10">
                    <LoadingSpinner size="md" />
                </div>
            ) : !error && records.length === 0 ? (
                <EmptyState
                    title="No payments recorded yet"
                    description="Payments recorded on invoices while recovery is active will appear here."
                />
            ) : (
                !error && <Table columns={columns} data={records} />
            )}

            {meta.totalPages > 1 && (
                <Pagination
                    currentPage={meta.currentPage}
                    totalPages={meta.totalPages}
                    onPageChange={setPage}
                />
            )}
        </div>
    );
};

RecoveryRecordsTable.propTypes = {
    total: PropTypes.oneOfType([PropTypes.string, PropTypes.number]).isRequired,
    count: PropTypes.number.isRequired,
};

const RecoveryDetailsModal = ({ isOpen, onClose, total, count }) => (
    <Modal isOpen={isOpen} onClose={onClose} title="Recovery Details" size="lg">
        {isOpen && <RecoveryRecordsTable total={total} count={count} />}
    </Modal>
);

RecoveryDetailsModal.propTypes = {
    isOpen: PropTypes.bool.isRequired,
    onClose: PropTypes.func.isRequired,
    total: PropTypes.oneOfType([PropTypes.string, PropTypes.number]).isRequired,
    count: PropTypes.number.isRequired,
};

export default RecoveryDetailsModal;
