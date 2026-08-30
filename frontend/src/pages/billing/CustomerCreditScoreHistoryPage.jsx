import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { History } from 'lucide-react';
import { creditScoreApi } from '../../services/creditScoreApi';
import { usePaginatedList } from '../../hooks/usePaginatedList';
import { extractErrorMessage } from '../../utils/errorMessage';
import BackLink from '../../components/ui/BackLink';
import Card from '../../components/ui/Card';
import Table from '../../components/ui/Table';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Pagination from '../../components/ui/Pagination';
import InlineAlert from '../../components/ui/InlineAlert';
import EmptyState from '../../components/ui/EmptyState';

const historyColumns = [
    {
        key: 'created_at',
        label: 'Date',
        render: (value) => new Date(value).toLocaleString(),
    },
    { key: 'trigger', label: 'Event' },
    { key: 'reference', label: 'Reference', render: (value) => value || '—' },
    {
        key: 'score_before',
        label: 'Score Before → After',
        render: (value, row) => `${value ?? '—'} → ${row.score_after}`,
    },
    {
        key: 'delta',
        label: 'Change',
        render: (value) => value === null || value === undefined ? '—' : (
            <span className={value > 0 ? 'text-success-600' : value < 0 ? 'text-error-600' : 'text-neutral-500'}>
                {value > 0 ? `+${value}` : value}
            </span>
        ),
    },
];

const CustomerCreditScoreHistoryPage = () => {
    const { id } = useParams();
    const [customer, setCustomer] = useState(null);
    const [customerLoading, setCustomerLoading] = useState(true);
    const [customerError, setCustomerError] = useState(null);

    const {
        data: history, meta, setPage, loading: historyLoading, error: historyError, refetch: refetchHistory,
    } = usePaginatedList((params) => creditScoreApi.customers.getHistory(id, params), {}, 25, [id]);

    const fetchCustomer = useCallback(async () => {
        setCustomerLoading(true);
        setCustomerError(null);
        try {
            const data = await creditScoreApi.customers.getById(id);
            setCustomer(data);
        } catch (err) {
            setCustomerError(extractErrorMessage(err, 'Failed to load customer.'));
        } finally {
            setCustomerLoading(false);
        }
    }, [id]);

    useEffect(() => {
        fetchCustomer();
    }, [fetchCustomer]);

    return (
        <div className="space-y-6">
            <div>
                <BackLink to={`/billing/customers/${id}/credit-score`}>Back to Credit Score</BackLink>
                <h1 className="text-3xl font-bold text-neutral-900 mt-2">Credit Score History</h1>
                <p className="text-neutral-500">
                    {customerLoading
                        ? 'Loading customer…'
                        : customerError
                            ? customerError
                            : `${customer?.customer_name} (${customer?.customer_code})`}
                </p>
            </div>

            <Card className="p-6" hover={false}>
                {historyLoading ? (
                    <div className="flex justify-center py-8">
                        <LoadingSpinner size="md" />
                    </div>
                ) : historyError ? (
                    <InlineAlert variant="error" message={historyError} onRetry={refetchHistory} />
                ) : history.length === 0 ? (
                    <EmptyState
                        icon={<History className="w-8 h-8 text-neutral-400" />}
                        title="No history yet"
                        description="Score-changing events for this customer will appear here."
                    />
                ) : (
                    <>
                        <Table columns={historyColumns} data={history} />
                        {meta.totalPages > 1 && (
                            <div className="mt-4">
                                <Pagination
                                    currentPage={meta.currentPage}
                                    totalPages={meta.totalPages}
                                    onPageChange={setPage}
                                />
                            </div>
                        )}
                    </>
                )}
            </Card>
        </div>
    );
};

export default CustomerCreditScoreHistoryPage;
