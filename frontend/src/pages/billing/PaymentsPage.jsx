import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
    Wallet, SlidersHorizontal, X, Banknote, Smartphone, Landmark, CreditCard,
    ChevronRight, Hash,
} from 'lucide-react';
import { billingApi } from '../../services/billingApi';
import Table from '../../components/ui/Table';
import SearchBar from '../../components/ui/SearchBar';
import Button from '../../components/ui/Button';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Badge from '../../components/ui/Badge';
import FilterBar from '../../components/ui/FilterBar';
import Pagination from '../../components/ui/Pagination';
import InlineAlert from '../../components/ui/InlineAlert';
import EmptyState from '../../components/ui/EmptyState';
import { usePaginatedList } from '../../hooks/usePaginatedList';

// Payment method → icon/color mapping, reused across the payments UI.
const METHOD_META = {
    cash: { icon: Banknote, label: 'Cash', classes: 'bg-success-50 text-success-700' },
    jazzcash: { icon: Smartphone, label: 'JazzCash', classes: 'bg-warning-50 text-warning-700' },
    easypaisa: { icon: Smartphone, label: 'Easypaisa', classes: 'bg-info-50 text-info-700' },
    bank: { icon: Landmark, label: 'Bank Transfer', classes: 'bg-primary-50 text-primary-700' },
};

const MethodBadge = ({ method, display }) => {
    const meta = METHOD_META[method] || { icon: CreditCard, label: display || 'N/A', classes: 'bg-neutral-100 text-neutral-700' };
    const Icon = meta.icon;
    return (
        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${meta.classes}`}>
            <Icon className="w-3.5 h-3.5" />
            {display || meta.label}
        </span>
    );
};

// Prefer the real per-method split (`allocations`, from the new multi-account
// payment methods system) over the single derived `method`/`method_display`
// label — falls back gracefully if the row doesn't carry it yet.
const MethodSplitDisplay = ({ payment }) => {
    if (Array.isArray(payment.allocations) && payment.allocations.length > 0) {
        return (
            <div className="flex flex-wrap gap-1">
                {payment.allocations.map((a) => (
                    <span
                        key={a.id}
                        className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-primary-50 text-primary-700"
                    >
                        {a.payment_method_name}: {formatCurrency(a.amount)}
                    </span>
                ))}
            </div>
        );
    }
    return <MethodBadge method={payment.method} display={payment.method_display} />;
};

const formatCurrency = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : value;
    if (isNaN(num)) return 'PKR 0.00';
    return `PKR ${num.toLocaleString('en-PK', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

const PaymentsPage = () => {
    const navigate = useNavigate();
    const [searchTerm, setSearchTerm] = useState('');
    const [showFilters, setShowFilters] = useState(false);

    const fetchPaymentsPage = (params) => {
        const p = { ...params };
        if (searchTerm) p.reference = searchTerm;
        return billingApi.payments.getAll(p);
    };

    const {
        data: payments, meta, setPage, loading, error, refetch,
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
        {
            key: 'reference_number',
            label: 'Reference',
            width: '160px',
            render: (value) => (
                <span className="inline-flex items-center gap-1.5 font-medium text-neutral-800">
                    <Hash className="w-3.5 h-3.5 text-neutral-400" />
                    {value}
                </span>
            ),
        },
        {
            key: 'bill_number',
            label: 'Bill #',
            render: (value) => value || 'N/A',
        },
        {
            key: 'customer_name',
            label: 'Customer',
            render: (value) => value || 'N/A',
        },
        {
            key: 'amount',
            label: 'Amount',
            render: (value) => (
                <span className="font-semibold text-success-700">{formatCurrency(value)}</span>
            )
        },
        {
            key: 'method',
            label: 'Method',
            render: (_value, row) => <MethodSplitDisplay payment={row} />
        },
        {
            key: 'payment_date',
            label: 'Date',
            render: (value) => value ? new Date(value).toLocaleDateString() : 'N/A'
        },
        { key: 'note', label: 'Note', render: (value) => value || <span className="text-neutral-400">-</span> },
        {
            key: 'actions',
            label: '',
            width: '80px',
            render: (_, row) => (
                <Link
                    to={`/billing/payments/${row.id}`}
                    className="inline-flex items-center gap-1 text-primary-600 hover:text-primary-700 text-sm font-medium"
                    onClick={(e) => e.stopPropagation()}
                >
                    View
                    <ChevronRight className="w-3.5 h-3.5" />
                </Link>
            ),
        },
    ];

    const filterConfig = [
        { name: 'customer_name', label: 'Customer Name', type: 'text' },
        { name: 'customer_code', label: 'Customer Code', type: 'text' },
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

    if (loading && payments.length === 0 && !error) {
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
                <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-primary-600 to-accent-600 flex items-center justify-center shadow-lg shadow-primary-900/20">
                    <Wallet className="w-5 h-5 text-white" />
                </div>
                <div>
                    <h1 className="text-3xl font-bold text-neutral-900">All Payments</h1>
                    <p className="text-neutral-500 mt-0.5">
                        Search and manage all payments across all invoices
                    </p>
                </div>
            </div>

            <div className="space-y-4">
                <div className="flex flex-col sm:flex-row gap-3">
                    <div className="flex-1">
                        <SearchBar
                            onSearch={handleSearch}
                            placeholder="Search by reference number..."
                            className="w-full"
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
                    message={error || 'Failed to load payments.'}
                    onRetry={refetch}
                />
            )}

            {!error && payments.length === 0 ? (
                <EmptyState
                    title="No payments found"
                    description="Try adjusting your search or filters"
                    icon={<Wallet className="w-8 h-8 text-neutral-400" />}
                />
            ) : !error && (
                <div className={loading ? 'opacity-60 pointer-events-none transition-opacity' : 'transition-opacity'}>
                    <Table
                        columns={columns}
                        data={payments}
                        onRowClick={(row) => navigate(`/billing/payments/${row.id}`)}
                    />
                </div>
            )}

            {meta.totalPages > 1 && (
                <Pagination
                    currentPage={meta.currentPage}
                    totalPages={meta.totalPages}
                    onPageChange={setPage}
                />
            )}
        </motion.div>
    );
};

export default PaymentsPage;
