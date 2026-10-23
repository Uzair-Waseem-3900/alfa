import PropTypes from 'prop-types';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useRecoveryRecords } from '../../hooks/useBilling';
import Modal from '../ui/Modal';
import Table from '../ui/Table';
import Pagination from '../ui/Pagination';
import Button from '../ui/Button';
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
//
// Mobile-first: below `sm` the three-column table becomes a compact list
// (customer + bill # on the left, amount on the right) and the numbered pager
// becomes a Previous / "x of y" / Next bar — neither needs sideways scrolling
// on a phone. From `sm` up the regular table and pager are used.
const RecoveryRecordsTable = ({ total, count }) => {
    const { data: records, meta, loading, error, setPage, refetch } = useRecoveryRecords();
    const hasRows = !loading && !error && records.length > 0;

    return (
        <div className="space-y-4">
            <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
                <p className="text-sm text-neutral-500">
                    {count.toLocaleString()} {count === 1 ? 'payment' : 'payments'} recorded
                </p>
                <p className="text-lg font-bold text-neutral-900 tabular-nums break-words">
                    Total: Rs. {formatAmount(total)}
                </p>
            </div>

            {error && <InlineAlert variant="error" message={error} onRetry={refetch} />}

            {loading && (
                <div className="flex items-center justify-center py-10">
                    <LoadingSpinner size="md" />
                </div>
            )}

            {!loading && !error && records.length === 0 && (
                <EmptyState
                    title="No payments recorded yet"
                    description="Payments recorded on invoices while recovery is active will appear here."
                />
            )}

            {hasRows && (
                <>
                    {/* Phones: compact list */}
                    <ul className="sm:hidden divide-y divide-neutral-100">
                        {records.map((row) => (
                            <li key={row.id} className="flex items-start justify-between gap-3 py-3">
                                <div className="min-w-0">
                                    <p className="font-medium text-neutral-900 break-words">{row.customer_name}</p>
                                    <p className="text-xs text-neutral-500 mt-0.5">{row.bill_number}</p>
                                </div>
                                <p className="font-semibold text-neutral-900 tabular-nums whitespace-nowrap">
                                    Rs. {formatAmount(row.amount)}
                                </p>
                            </li>
                        ))}
                    </ul>

                    {/* Tablet and up: table */}
                    <Table columns={columns} data={records} className="hidden sm:block" />
                </>
            )}

            {meta.totalPages > 1 && (
                <>
                    {/* Phones: Previous / x of y / Next */}
                    <div className="flex items-center gap-3 sm:hidden">
                        <Button
                            variant="secondary"
                            icon={ChevronLeft}
                            className="flex-1"
                            disabled={meta.currentPage <= 1 || loading}
                            onClick={() => setPage(meta.currentPage - 1)}
                        >
                            Prev
                        </Button>
                        <span className="text-sm text-neutral-500 whitespace-nowrap">
                            {meta.currentPage} / {meta.totalPages}
                        </span>
                        <Button
                            variant="secondary"
                            icon={ChevronRight}
                            className="flex-1"
                            disabled={meta.currentPage >= meta.totalPages || loading}
                            onClick={() => setPage(meta.currentPage + 1)}
                        >
                            Next
                        </Button>
                    </div>

                    {/* Tablet and up: numbered pager */}
                    <div className="hidden sm:block">
                        <Pagination
                            currentPage={meta.currentPage}
                            totalPages={meta.totalPages}
                            onPageChange={setPage}
                        />
                    </div>
                </>
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
