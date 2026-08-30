import { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { purchasesApi } from '../../services/purchasesApi';
import { extractErrorMessage } from '../../utils/errorMessage';
import Table from '../../components/ui/Table';
import Button from '../../components/ui/Button';
import BackLink from '../../components/ui/BackLink';
import SearchBar from '../../components/ui/SearchBar';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Badge from '../../components/ui/Badge';
import FilterBar from '../../components/ui/FilterBar';
import Pagination from '../../components/ui/Pagination';
import InlineAlert from '../../components/ui/InlineAlert';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import EmptyState from '../../components/ui/EmptyState';
import { usePaginatedList } from '../../hooks/usePaginatedList';
import { useNavigate } from 'react-router-dom';
import { SlidersHorizontal, X, CheckCircle2, Undo2 } from 'lucide-react';

const AllReturnsPage = () => {
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';
    const navigate = useNavigate();

    const [searchTerm, setSearchTerm] = useState('');
    const [suppliers, setSuppliers] = useState([]);
    const [showFilters, setShowFilters] = useState(false);
    const [acceptTarget, setAcceptTarget] = useState(null);
    const [acceptLoading, setAcceptLoading] = useState(false);

    const fetchReturnsPage = (params) => {
        const p = { ...params };
        if (searchTerm) {
            p.order_number = searchTerm;
        }
        return purchasesApi.returns.getAll(p);
    };

    const {
        data: returns, meta, page, setPage, loading, initialLoading, error: listError,
        filters, setFilters, refetch: fetchAllReturns,
    } = usePaginatedList(fetchReturnsPage, {}, 25, [searchTerm]);

    useEffect(() => {
        loadSuppliers();
    }, []);

    const loadSuppliers = async () => {
        try {
            const data = await purchasesApi.suppliers.getAll();
            setSuppliers(data || []);
        } catch (error) {
            console.error('Failed to load suppliers:', error);
        }
    };

    const handleApplyFilters = (filterValues) => {
        setFilters(filterValues);
    };

    const handleResetFilters = () => {
        setFilters({});
        setSearchTerm('');
    };

    const handleSearch = (value) => {
        setSearchTerm(value);
        setPage(1);
    };

    const handleAcceptReturn = async () => {
        if (!acceptTarget) return;
        setAcceptLoading(true);
        try {
            await purchasesApi.returns.accept(acceptTarget);
            fetchAllReturns();
            toast.success('Return accepted.');
            setAcceptTarget(null);
        } catch (error) {
            console.error('Failed to accept return:', error);
            toast.error(extractErrorMessage(error, 'Failed to accept return.'));
        } finally {
            setAcceptLoading(false);
        }
    };

    const getStatusBadge = (status) => {
        const variants = {
            pending: 'pending',
            accepted: 'accepted',
        };
        return <Badge variant={variants[status] || 'default'}>{status}</Badge>;
    };

    const columns = [
        { key: 'reference_number', label: 'Return #', width: '140px' },
        {
            key: 'order_number',
            label: 'Order #',
            render: (value) => value || 'N/A'
        },
        {
            key: 'supplier_name',
            label: 'Supplier',
            render: (value) => value || 'N/A'
        },
        {
            key: 'status',
            label: 'Status',
            render: getStatusBadge
        },
        {
            key: 'total_return_amount',
            label: 'Amount (PKR)',
            render: (value) => {
                const num = typeof value === 'string' ? parseFloat(value) : value;
                return <span className="font-medium tabular-nums">{isNaN(num) ? '0.00' : num.toFixed(2)}</span>;
            }
        },
        {
            key: 'created_at',
            label: 'Date',
            render: (value) => value ? new Date(value).toLocaleDateString() : 'N/A'
        },
        { key: 'note', label: 'Note', render: (value) => value || <span className="text-neutral-400">&mdash;</span> },
        {
            key: 'actions',
            label: 'Actions',
            width: '120px',
            render: (_, row) => row.status === 'pending' && isAdmin && (
                <Button
                    size="sm"
                    variant="success"
                    icon={CheckCircle2}
                    onClick={(e) => {
                        e.stopPropagation();
                        setAcceptTarget(row.id);
                    }}
                >
                    Accept
                </Button>
            ),
        },
    ];

    // Filter configuration for the FilterBar
    const filterConfig = [
        {
            name: 'status',
            label: 'Status',
            type: 'select',
            options: [
                { value: '', label: 'All Status' },
                { value: 'pending', label: 'Pending' },
                { value: 'accepted', label: 'Accepted' },
            ],
        },
        {
            name: 'supplier_name',
            label: 'Supplier Name',
            type: 'select',
            options: [
                { value: '', label: 'All Suppliers' },
                ...suppliers.map(s => ({ value: s.name, label: s.name })),
            ],
        },
        {
            name: 'supplier_code',
            label: 'Supplier Code',
            type: 'select',
            options: [
                { value: '', label: 'All Supplier Codes' },
                ...suppliers.map(s => ({ value: s.code, label: s.code })),
            ],
        },
        { name: 'order_number', label: 'Order Number', type: 'text' },
        { name: 'date_from', label: 'Date From', type: 'date' },
        { name: 'date_to', label: 'Date To', type: 'date' },
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
                <div className="flex items-center gap-3">
                    <div className="w-11 h-11 rounded-xl bg-primary-50 text-primary-600 flex items-center justify-center flex-shrink-0">
                        <Undo2 className="w-5.5 h-5.5" />
                    </div>
                    <div>
                        <h1 className="text-3xl font-bold text-neutral-900">All Returns</h1>
                        <p className="text-neutral-500 mt-1">View all purchase returns across all orders</p>
                    </div>
                </div>
                <BackLink to="/purchases/orders">Back to Orders</BackLink>
            </div>

            <div className="space-y-4">
                <div className="flex flex-col sm:flex-row gap-3">
                    <div className="flex-1">
                        <SearchBar
                            onSearch={handleSearch}
                            placeholder="Search by order number..."
                            className="w-full"
                        />
                    </div>
                    <div className="flex gap-3">
                        <Button
                            variant="secondary"
                            onClick={() => setShowFilters(!showFilters)}
                            icon={SlidersHorizontal}
                        >
                            {showFilters ? 'Hide Filters' : 'Show Filters'}
                        </Button>
                        {(Object.keys(filters).length > 0 || searchTerm) && (
                            <Button variant="secondary" icon={X} onClick={handleResetFilters}>
                                Clear
                            </Button>
                        )}
                    </div>
                </div>

                {showFilters && (
                    <FilterBar
                        filters={filterConfig}
                        onApply={handleApplyFilters}
                        onReset={handleResetFilters}
                    />
                )}
            </div>

            {listError && (
                <InlineAlert variant="error" message={listError} onRetry={fetchAllReturns} />
            )}

            <div className={`relative transition-opacity ${loading ? 'opacity-60' : 'opacity-100'}`}>
                {loading && (
                    <div className="absolute right-2 top-2 z-10">
                        <LoadingSpinner size="sm" />
                    </div>
                )}
                {returns.length === 0 && !loading ? (
                    <EmptyState
                        title="No returns found"
                        description="Try adjusting your search or filters."
                    />
                ) : (
                    <Table
                        columns={columns}
                        data={returns}
                        onRowClick={(ret) => navigate(`/purchases/returns/${ret.id}`)}
                    />
                )}
            </div>

            {meta.totalPages > 1 && (
                <Pagination
                    currentPage={meta.currentPage}
                    totalPages={meta.totalPages}
                    onPageChange={setPage}
                />
            )}

            <ConfirmDialog
                isOpen={!!acceptTarget}
                onClose={() => setAcceptTarget(null)}
                onConfirm={handleAcceptReturn}
                title="Accept Return"
                message="Are you sure you want to accept this return? This action cannot be undone."
                confirmText="Accept"
                variant="primary"
                loading={acceptLoading}
            />
        </div>
    );
};

export default AllReturnsPage;