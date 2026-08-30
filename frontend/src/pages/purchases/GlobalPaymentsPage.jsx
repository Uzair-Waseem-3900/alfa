import { useState } from 'react';
import { purchasesApi } from '../../services/purchasesApi';
import Table from '../../components/ui/Table';
import Button from '../../components/ui/Button';
import SearchBar from '../../components/ui/SearchBar';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Badge from '../../components/ui/Badge';
import FilterBar from '../../components/ui/FilterBar';
import Pagination from '../../components/ui/Pagination';
import InlineAlert from '../../components/ui/InlineAlert';
import EmptyState from '../../components/ui/EmptyState';
import { usePaginatedList } from '../../hooks/usePaginatedList';
import { Link } from 'react-router-dom';
import { SlidersHorizontal, Eye, Wallet, X } from 'lucide-react';

const GlobalPaymentsPage = () => {
    const [searchTerm, setSearchTerm] = useState('');
    const [showFilters, setShowFilters] = useState(false);

    const fetchPaymentsPage = (params) => {
        const p = { ...params };
        if (searchTerm) {
            p.reference = searchTerm;
        }
        return purchasesApi.payments.getAll(p);
    };

    const {
        data: payments, meta, page, setPage, loading, initialLoading, error: listError, refetch,
        filters, setFilters,
    } = usePaginatedList(fetchPaymentsPage, {}, 25, [searchTerm]);

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

    const columns = [
        { key: 'reference_number', label: 'Reference', width: '140px' },
        {
            key: 'order_number',
            label: 'Order #',
            render: (value) => value || 'N/A',
        },
        {
            key: 'supplier_name',
            label: 'Supplier',
            render: (value) => value || 'N/A',
        },
        {
            key: 'amount',
            label: 'Amount (PKR)',
            render: (value) => {
                const num = typeof value === 'string' ? parseFloat(value) : value;
                return isNaN(num) ? '0.00' : num.toFixed(2);
            }
        },
        {
            key: 'method_display',
            label: 'Method',
            render: (value, row) => (
                Array.isArray(row.allocations) && row.allocations.length > 0 ? (
                    <div className="flex flex-wrap gap-1">
                        {row.allocations.map((a) => (
                            <Badge key={a.id}>{a.payment_method_name}: {parseFloat(a.amount).toFixed(2)}</Badge>
                        ))}
                    </div>
                ) : <Badge>{value || 'N/A'}</Badge>
            )
        },
        {
            key: 'payment_date',
            label: 'Date',
            render: (value) => value ? new Date(value).toLocaleDateString() : 'N/A'
        },
        {
            key: 'note',
            label: 'Note',
            render: (value) => value || '-'
        },
        {
            key: 'actions',
            label: 'Actions',
            width: '100px',
            render: (_, row) => (
                <Link
                    to={`/purchases/payments/ref/${row.reference_number}`}
                    className="inline-flex items-center gap-1 text-primary-600 hover:text-primary-700 text-sm font-medium"
                >
                    <Eye className="w-4 h-4" /> View
                </Link>
            ),
        },
    ];

    const filterConfig = [
        { name: 'supplier_name', label: 'Supplier Name', type: 'text' },
        { name: 'supplier_code', label: 'Supplier Code', type: 'text' },
        {
            name: 'method',
            label: 'Payment Method',
            type: 'select',
            options: [
                { value: '', label: 'All Methods' },
                { value: 'cash', label: 'Cash' },
                { value: 'jazzcash', label: 'JazzCash' },
                { value: 'easypaisa', label: 'Easypaisa' },
                { value: 'bank', label: 'Bank Transfer' },
            ],
        },
        { name: 'date_from', label: 'Date From', type: 'date' },
        { name: 'date_to', label: 'Date To', type: 'date' },
    ];

    // Full-page spinner only before the first fetch completes — later
    // search/filter changes keep the page shell mounted with a small inline
    // indicator instead of blanking to a spinner.
    if (initialLoading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center gap-3">
                <div className="w-11 h-11 rounded-xl bg-primary-50 text-primary-600 flex items-center justify-center flex-shrink-0">
                    <Wallet className="w-5.5 h-5.5" />
                </div>
                <div>
                    <h1 className="text-3xl font-bold text-neutral-900">All Payments</h1>
                    <p className="text-neutral-500 mt-1">
                        Search and manage all payments across all purchase orders
                    </p>
                </div>
            </div>

            <div className="space-y-4">
                <div className="flex flex-col sm:flex-row gap-3">
                    <div className="flex-1">
                        <SearchBar
                            onSearch={handleSearch}
                            placeholder="Search by reference number (e.g., SPY-2026-0001)..."
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
                <InlineAlert variant="error" message={listError} onRetry={refetch} />
            )}

            <div className={`relative transition-opacity ${loading ? 'opacity-60' : 'opacity-100'}`}>
                {loading && (
                    <div className="absolute right-2 top-2 z-10">
                        <LoadingSpinner size="sm" />
                    </div>
                )}
                {payments.length === 0 && !loading ? (
                    <EmptyState
                        title="No payments found"
                        description="Try adjusting your search or filters."
                    />
                ) : (
                    <Table columns={columns} data={payments} />
                )}
            </div>

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

export default GlobalPaymentsPage;