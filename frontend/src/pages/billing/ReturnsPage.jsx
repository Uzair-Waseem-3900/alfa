import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { RotateCcw, SlidersHorizontal, X } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { billingApi } from '../../services/billingApi';
import Table from '../../components/ui/Table';
import SearchBar from '../../components/ui/SearchBar';
import Button from '../../components/ui/Button';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Badge from '../../components/ui/Badge';
import FilterBar from '../../components/ui/FilterBar';
import Pagination from '../../components/ui/Pagination';
import EmptyState from '../../components/ui/EmptyState';
import InlineAlert from '../../components/ui/InlineAlert';
import { usePaginatedList } from '../../hooks/usePaginatedList';

const ReturnsPage = () => {
    const navigate = useNavigate();
    const { user } = useAuth();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const [searchTerm, setSearchTerm] = useState('');
    const [showFilters, setShowFilters] = useState(false);

    // Note: the backend supports `reference`, `bill_number`, `customer_name` as
    // separate search params, but searchTerm here can match any of those, so we
    // still filter the fetched page locally against all 3 fields.
    const {
        data: rawReturns, meta, page, setPage, loading, initialLoading, error, refetch,
        filters, setFilters,
    } = usePaginatedList((params) => billingApi.returns.getAll(params), {});

    const returns = searchTerm
        ? rawReturns.filter(r => {
            const term = searchTerm.toLowerCase();
            return (
                r.reference_number?.toLowerCase().includes(term) ||
                r.invoice_bill_number?.toLowerCase().includes(term) ||
                r.customer_name?.toLowerCase().includes(term)
            );
        })
        : rawReturns;

    const hasActiveFilters = Object.keys(filters).length > 0 || !!searchTerm;

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

    const handleRowClick = (returnItem) => {
        navigate(`/billing/returns/${returnItem.id}`);
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
            key: 'invoice_bill_number',
            label: 'Bill #',
            render: (value) => value || 'N/A'
        },
        {
            key: 'customer_name',
            label: 'Customer',
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
                return isNaN(num) ? '0.00' : num.toFixed(2);
            }
        },
        {
            key: 'created_at',
            label: 'Created',
            render: (value) => value ? new Date(value).toLocaleDateString() : 'N/A'
        },
        {
            key: 'accepted_at',
            label: 'Accepted',
            render: (value) => value ? new Date(value).toLocaleDateString() : 'N/A'
        },
    ];

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
            <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
                className="flex items-center gap-3"
            >
                <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-primary-700 to-accent-600 flex items-center justify-center shadow-lg shadow-primary-900/20 flex-shrink-0">
                    <RotateCcw className="w-5 h-5 text-white" />
                </div>
                <div>
                    <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900">Returns</h1>
                    <p className="text-sm text-neutral-500 mt-0.5">
                        View all customer returns across all invoices
                        {!loading && (
                            <span className="text-neutral-400"> &middot; {returns.length} found</span>
                        )}
                    </p>
                </div>
            </motion.div>

            {error && <InlineAlert variant="error" message={error} onRetry={refetch} />}

            <div className="space-y-4">
                <div className="flex flex-col sm:flex-row gap-3">
                    <div className="flex-1">
                        <SearchBar
                            onSearch={handleSearch}
                            placeholder="Search by return #, bill #, or customer..."
                            className="w-full"
                            value={searchTerm}
                        />
                    </div>
                    <div className="flex gap-2">
                        <Button
                            variant="secondary"
                            onClick={() => setShowFilters(!showFilters)}
                            icon={SlidersHorizontal}
                        >
                            {showFilters ? 'Hide Filters' : 'Filters'}
                        </Button>
                        {hasActiveFilters && (
                            <Button variant="secondary" onClick={handleResetFilters} icon={X}>
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

            {returns.length === 0 ? (
                <EmptyState
                    title="No returns found"
                    description={hasActiveFilters ? 'Try adjusting your search or filters' : 'No returns have been created yet.'}
                />
            ) : (
                <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.3 }}
                    className="bg-white rounded-2xl shadow-card border border-neutral-200 overflow-hidden"
                >
                    <Table
                        columns={columns}
                        data={returns}
                        onRowClick={handleRowClick}
                    />
                </motion.div>
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

export default ReturnsPage;
