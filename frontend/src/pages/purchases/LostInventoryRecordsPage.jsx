import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { purchasesApi } from '../../services/purchasesApi';
import { usePaginatedList } from '../../hooks/usePaginatedList';
import Table from '../../components/ui/Table';
import SearchBar from '../../components/ui/SearchBar';
import Button from '../../components/ui/Button';
import BackLink from '../../components/ui/BackLink';
import FilterBar from '../../components/ui/FilterBar';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Pagination from '../../components/ui/Pagination';
import EmptyState from '../../components/ui/EmptyState';

const formatCurrency = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : value;
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const LostInventoryRecordsPage = () => {
    const { user } = useAuth();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const [searchTerm, setSearchTerm] = useState('');
    const [showFilters, setShowFilters] = useState(false);

    const fetchRecordsPage = (params) => {
        const p = { ...params };
        if (searchTerm) p.search = searchTerm;
        return purchasesApi.lostInventory.getAll(p);
    };

    const {
        data: records, meta, page, setPage, loading,
        filters, setFilters,
    } = usePaginatedList(fetchRecordsPage, {}, 25, [searchTerm]);

    const handleSearch = (value) => {
        setSearchTerm(value);
        setPage(1);
    };

    const handleApplyFilters = (filterValues) => {
        setFilters(filterValues);
    };

    const handleResetFilters = () => {
        setFilters({});
        setSearchTerm('');
    };

    const filterConfig = [
        { name: 'product_name', label: 'Product Name', type: 'text' },
        { name: 'product_code', label: 'Product Code', type: 'text' },
        { name: 'reason', label: 'Reason', type: 'text' },
        { name: 'date', label: 'Date', type: 'date' },
        { name: 'date_from', label: 'Date From', type: 'date' },
        { name: 'date_to', label: 'Date To', type: 'date' },
        { name: 'min_amount', label: 'Min Amount', type: 'number' },
        { name: 'max_amount', label: 'Max Amount', type: 'number' },
    ];

    const columns = [
        {
            key: 'reference_number',
            label: 'Reference',
            width: '140px',
            render: (value) => (
                <span className="font-mono font-medium text-neutral-900">{value}</span>
            ),
        },
        {
            key: 'items',
            label: 'Products',
            render: (items) => (items || []).map((it) => `${it.product_name} x${it.quantity}`).join(', ') || 'N/A',
        },
        {
            key: 'reason',
            label: 'Reason',
            render: (_value, row) => (row.items || []).map((it) => it.reason).filter(Boolean).join(', ') || '-',
        },
        {
            key: 'total_lost_amount',
            label: 'Total Loss (PKR)',
            render: (value) => (
                <span className="font-semibold text-error-600">Rs. {formatCurrency(value)}</span>
            ),
        },
        { key: 'note', label: 'Note', render: (value) => value || '-' },
        {
            key: 'created_at',
            label: 'Date',
            render: (value) => value ? new Date(value).toLocaleString() : 'N/A',
        },
        {
            key: 'created_by',
            label: 'Recorded By',
            render: (value) => value || 'N/A',
        },
        {
            key: 'id',
            label: 'Action',
            width: '100px',
            render: (value) => (
                <Link
                    to={`/purchases/lost-inventory/records/${value}`}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-primary-600 bg-primary-50 hover:bg-primary-100 border border-primary-200 rounded-lg transition-colors"
                >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                    View
                </Link>
            ),
        },
    ];

    if (!isAdmin) {
        return (
            <div className="text-center py-12">
                <h2 className="text-2xl font-semibold text-neutral-900">Access Denied</h2>
                <p className="text-neutral-500 mt-2">Only admins or superusers can view lost inventory records.</p>
                <BackLink to="/purchases/inventory" className="mt-4">Back to Inventory</BackLink>
            </div>
        );
    }

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-3xl font-bold text-neutral-900">Lost Inventory Records</h1>
                <p className="text-neutral-500 mt-1">Full history of products marked as lost, damaged, or missing</p>
                <div className="mt-2 flex gap-4">
                    <BackLink to="/purchases/inventory">Back to Inventory</BackLink>
                    <BackLink to="/purchases/lost-inventory">Back to Manage Inventory</BackLink>
                </div>
            </div>

            <div className="space-y-4">
                <div className="flex gap-4">
                    <div className="flex-1">
                        <SearchBar
                            onSearch={handleSearch}
                            placeholder="Search by reference number..."
                            className="w-full"
                        />
                    </div>
                    <Button
                        variant="secondary"
                        onClick={() => setShowFilters(!showFilters)}
                        icon={({ className }) => (
                            <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
                            </svg>
                        )}
                    >
                        {showFilters ? 'Hide Filters' : 'Show Filters'}
                    </Button>
                    {(Object.keys(filters).length > 0 || searchTerm) && (
                        <Button variant="secondary" onClick={handleResetFilters}>
                            Clear All
                        </Button>
                    )}
                </div>

                {showFilters && (
                    <FilterBar
                        filters={filterConfig}
                        onApply={handleApplyFilters}
                        onReset={handleResetFilters}
                    />
                )}
            </div>

            <Table columns={columns} data={records} />

            {meta.totalPages > 1 && (
                <Pagination
                    currentPage={meta.currentPage}
                    totalPages={meta.totalPages}
                    onPageChange={setPage}
                />
            )}

            {records.length === 0 && !loading && (
                <EmptyState title="No lost inventory records found" description="Try adjusting your search or filters" />
            )}
        </div>
    );
};

export default LostInventoryRecordsPage;
