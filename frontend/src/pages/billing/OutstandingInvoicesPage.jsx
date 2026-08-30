import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { AlertTriangle, SlidersHorizontal, X, CircleCheckBig } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { billingApi } from '../../services/billingApi';
import Table from '../../components/ui/Table';
import SearchBar from '../../components/ui/SearchBar';
import Button from '../../components/ui/Button';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import PaymentStatusBadge from '../../components/billing/PaymentStatusBadge';
import InvoiceStatusBadge from '../../components/billing/InvoiceStatusBadge';
import FilterBar from '../../components/ui/FilterBar';
import Pagination from '../../components/ui/Pagination';
import InlineAlert from '../../components/ui/InlineAlert';
import EmptyState from '../../components/ui/EmptyState';
import { usePaginatedList } from '../../hooks/usePaginatedList';

const formatCurrency = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : value;
    if (isNaN(num)) return 'PKR 0.00';
    return `PKR ${num.toLocaleString('en-PK', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

// Visual urgency cue for the outstanding amount column — higher balances
// read as more urgent at a glance.
const urgencyClasses = (num) => {
    if (isNaN(num) || num <= 0) return 'text-neutral-500';
    if (num >= 100000) return 'text-error-700 font-bold';
    if (num >= 25000) return 'text-warning-700 font-semibold';
    return 'text-neutral-800 font-semibold';
};

const OutstandingInvoicesPage = () => {
    const navigate = useNavigate();
    const { user } = useAuth();

    const [searchTerm, setSearchTerm] = useState('');
    const [showFilters, setShowFilters] = useState(false);

    // Fetch outstanding invoices
    const fetchOutstandingInvoicesPage = (params) => {
        const p = { ...params };
        if (searchTerm) p.customer_name = searchTerm;
        return billingApi.invoices.getOutstanding(p);
    };

    const {
        data: invoices, meta, setPage, loading, error, refetch,
        filters, setFilters,
    } = usePaginatedList(fetchOutstandingInvoicesPage, {}, 25, [searchTerm]);

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

    const columns = [
        { key: 'bill_number', label: 'Bill #', width: '120px' },
        {
            key: 'customer',
            label: 'Customer',
            render: (value) => value?.name || 'N/A'
        },
        {
            key: 'status',
            label: 'Status',
            render: (value) => <InvoiceStatusBadge status={value} />
        },
        {
            key: 'grand_total',
            label: 'Grand Total',
            render: (value) => formatCurrency(value)
        },
        {
            key: 'credit_outstanding',
            label: 'Outstanding',
            render: (value) => {
                const num = typeof value === 'string' ? parseFloat(value) : value;
                return (
                    <span className={`inline-flex items-center gap-1.5 ${urgencyClasses(num)}`}>
                        {!isNaN(num) && num >= 100000 && <AlertTriangle className="w-3.5 h-3.5" />}
                        {formatCurrency(value)}
                    </span>
                );
            }
        },
        {
            key: 'payment_status',
            label: 'Payment Status',
            render: (value) => <PaymentStatusBadge status={value} />
        },
        {
            key: 'confirmed_at',
            label: 'Confirmed',
            render: (value) => value ? new Date(value).toLocaleDateString() : 'N/A'
        },
    ];

    // Filter configuration for the FilterBar
    const filterConfig = [
        {
            name: 'payment_status',
            label: 'Payment Status',
            type: 'select',
            options: [
                { value: '', label: 'All Payment Status' },
                { value: 'unpaid', label: 'Unpaid' },
                { value: 'partial', label: 'Partial' },
            ],
        },
        { name: 'date_from', label: 'Date From', type: 'date' },
        { name: 'date_to', label: 'Date To', type: 'date' },
        { name: 'min_outstanding', label: 'Min Outstanding', type: 'number' },
        { name: 'max_outstanding', label: 'Max Outstanding', type: 'number' },
    ];

    if (loading && invoices.length === 0 && !error) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    return (
        <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
            className="space-y-6"
        >
            <div className="flex items-center gap-3">
                <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-warning-500 to-error-500 flex items-center justify-center shadow-lg shadow-warning-500/20">
                    <AlertTriangle className="w-5 h-5 text-white" />
                </div>
                <div>
                    <h1 className="text-3xl font-bold text-neutral-900">Outstanding Invoices</h1>
                    <p className="text-neutral-500 mt-0.5">
                        All invoices with an outstanding balance
                    </p>
                    {!error && (
                        <p className="text-sm text-neutral-400 mt-0.5">
                            {meta.count} invoice{meta.count !== 1 ? 's' : ''} with outstanding balance
                        </p>
                    )}
                </div>
            </div>

            <div className="space-y-4">
                <div className="flex flex-col sm:flex-row gap-3">
                    <div className="flex-1">
                        <SearchBar
                            onSearch={handleSearch}
                            placeholder="Search by customer name..."
                            className="w-full"
                            value={searchTerm}
                        />
                    </div>
                    <div className="flex gap-3">
                        <Button
                            variant="secondary"
                            onClick={() => setShowFilters(!showFilters)}
                            icon={SlidersHorizontal}
                        >
                            {showFilters ? 'Hide Filters' : 'Filters'}
                        </Button>
                        {(Object.keys(filters).length > 0 || searchTerm) && (
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

            {error && (
                <InlineAlert
                    variant="error"
                    message={error || 'Failed to load outstanding invoices.'}
                    onRetry={refetch}
                />
            )}

            {!error && invoices.length === 0 ? (
                <EmptyState
                    icon={<CircleCheckBig className="w-8 h-8 text-success-500" />}
                    title="No Outstanding Invoices"
                    description="All invoices have been fully paid or there are no invoices yet."
                />
            ) : !error && (
                <>
                    <div className={loading ? 'opacity-60 pointer-events-none transition-opacity' : 'transition-opacity'}>
                        <Table
                            columns={columns}
                            data={invoices}
                            onRowClick={(invoice) => navigate(`/billing/invoices/${invoice.id}`)}
                        />
                    </div>

                    {meta.totalPages > 1 && (
                        <Pagination
                            currentPage={meta.currentPage}
                            totalPages={meta.totalPages}
                            onPageChange={setPage}
                        />
                    )}
                </>
            )}
        </motion.div>
    );
};

export default OutstandingInvoicesPage;
