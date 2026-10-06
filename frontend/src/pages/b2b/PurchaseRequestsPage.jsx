import { Navigate, useNavigate } from 'react-router-dom';
import { ShoppingCart, Plus, RefreshCw } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { usePurchaseRequests, usePurchaseRequestActions } from '../../hooks/useB2B';
import { extractErrorMessage } from '../../utils/errorMessage';
import Button from '../../components/ui/Button';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Table from '../../components/ui/Table';
import Badge from '../../components/ui/Badge';
import Tabs from '../../components/ui/Tabs';
import Pagination from '../../components/ui/Pagination';
import EmptyState from '../../components/ui/EmptyState';
import InlineAlert from '../../components/ui/InlineAlert';

const STATUS_TABS = [
    { value: '', label: 'All' },
    { value: 'pending', label: 'Pending' },
    { value: 'accepted', label: 'Accepted' },
    { value: 'denied', label: 'Not accepted' },
    { value: 'cancelled', label: 'Cancelled' },
];

export const REQUEST_STATUS_BADGE = {
    pending: { variant: 'pending', label: 'Pending' },
    accepted: { variant: 'success', label: 'Accepted' },
    denied: { variant: 'error', label: 'Not accepted' },
    cancelled: { variant: 'default', label: 'Cancelled' },
};

const formatDateTime = (value) => (value ? new Date(value).toLocaleString() : '—');

const PurchaseRequestsPage = () => {
    const { user } = useAuth();
    const { toast } = useToast();
    const navigate = useNavigate();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const {
        data: requests, meta, page, setPage, loading, initialLoading, error: listError,
        filters, setFilters, refetch,
    } = usePurchaseRequests();
    const { sync, mutating } = usePurchaseRequestActions();

    if (!isAdmin) {
        return <Navigate to="/dashboard" replace />;
    }

    const handleSync = async () => {
        try {
            const result = await sync();
            toast.success(result?.updated ? `${result.updated} request(s) updated` : 'Everything is up to date');
            await refetch();
        } catch (error) {
            toast.error(extractErrorMessage(error, 'Failed to check for updates'));
        }
    };

    const columns = [
        {
            key: 'provider_name',
            label: 'Partner',
            render: (value) => <span className="font-medium text-neutral-900">{value}</span>,
        },
        {
            key: 'created_at',
            label: 'Created',
            render: (value) => <span className="text-neutral-600">{formatDateTime(value)}</span>,
        },
        {
            key: 'item_count',
            label: 'Items',
            width: '90px',
            render: (value) => <span className="text-neutral-700">{value}</span>,
        },
        {
            key: 'status',
            label: 'Status',
            render: (value, row) => {
                const badge = REQUEST_STATUS_BADGE[value] || { variant: 'default', label: value };
                return (
                    <div className="flex flex-wrap items-center gap-1.5">
                        <Badge variant={badge.variant}>{badge.label}</Badge>
                        {!row.delivered && value === 'pending' && <Badge variant="warning">Waiting to send</Badge>}
                        {value === 'accepted' && !row.order && <Badge variant="warning">Creating order…</Badge>}
                    </div>
                );
            },
        },
        {
            key: 'order_number',
            label: 'Order',
            render: (value) => value || <span className="text-neutral-300">—</span>,
        },
    ];

    if (initialLoading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <div className="flex items-center gap-2.5">
                        <ShoppingCart className="w-6 h-6 text-primary-600" />
                        <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900">Purchase Requests</h1>
                    </div>
                    <p className="text-neutral-500 mt-1">
                        Ask a partner to sell you products. When they accept, a confirmed purchase order is created for you automatically.
                    </p>
                </div>
                <div className="flex gap-2">
                    <Button variant="secondary" icon={RefreshCw} onClick={handleSync} loading={mutating}>
                        Check for Updates
                    </Button>
                    <Button icon={Plus} onClick={() => navigate('/b2b/purchase-requests/new')}>
                        Create Request
                    </Button>
                </div>
            </div>

            {listError && (
                <InlineAlert variant="error" title="Couldn't load requests" message={listError} onRetry={refetch} />
            )}

            <Tabs
                tabs={STATUS_TABS}
                activeTab={filters.status || ''}
                onChange={(status) => setFilters({ ...filters, status: status || undefined })}
                className="overflow-x-auto"
            />

            {loading ? (
                <div className="flex items-center justify-center py-16">
                    <LoadingSpinner size="lg" />
                </div>
            ) : requests.length === 0 ? (
                <EmptyState
                    title="No Purchase Requests"
                    description="Create a request to buy from a partner software."
                />
            ) : (
                <>
                    <Table columns={columns} data={requests} onRowClick={(row) => navigate(`/b2b/purchase-requests/${row.id}`)} />
                    {meta.totalPages > 1 && (
                        <Pagination currentPage={meta.currentPage} totalPages={meta.totalPages} onPageChange={setPage} />
                    )}
                </>
            )}
        </div>
    );
};

export default PurchaseRequestsPage;
