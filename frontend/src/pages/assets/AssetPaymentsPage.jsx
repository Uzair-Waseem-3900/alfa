import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Receipt, ShieldAlert, SlidersHorizontal, X, TrendingDown, TrendingUp } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useAssetPayments } from '../../hooks/useAssets';
import Badge from '../../components/ui/Badge';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Table from '../../components/ui/Table';
import SearchBar from '../../components/ui/SearchBar';
import Button from '../../components/ui/Button';
import FilterBar from '../../components/ui/FilterBar';
import Pagination from '../../components/ui/Pagination';
import BackLink from '../../components/ui/BackLink';
import InlineAlert from '../../components/ui/InlineAlert';
import EmptyState from '../../components/ui/EmptyState';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const MethodSplitDisplay = ({ allocations }) => {
    if (!Array.isArray(allocations) || allocations.length === 0) {
        return <span className="text-neutral-300">—</span>;
    }
    return (
        <div className="flex flex-wrap gap-1">
            {allocations.map((a) => (
                <span
                    key={a.id}
                    className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-primary-50 text-primary-700"
                >
                    {a.payment_method_name}: Rs. {fmt(a.amount)}
                </span>
            ))}
        </div>
    );
};

const AssetPaymentsPage = () => {
    const { user } = useAuth();
    const navigate = useNavigate();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const [searchTerm, setSearchTerm] = useState('');
    const [showFilters, setShowFilters] = useState(false);

    const {
        data: payments, meta, page, setPage, loading, error, filters, setFilters, refetch,
    } = useAssetPayments();

    const handleApplyFilters = (values) => setFilters({ ...values, search: searchTerm || undefined });
    const handleResetFilters = () => { setFilters({}); setSearchTerm(''); };
    const handleSearch = (value) => {
        setSearchTerm(value);
        setFilters((prev) => ({ ...prev, search: value || undefined }));
    };
    const handleRowClick = (row) => navigate(`/assets/payments/${row.id}`);

    const filterConfig = [
        { name: 'payment_type', label: 'Type', type: 'select', options: [
            { value: '', label: 'All' },
            { value: 'purchase', label: 'Purchase' },
            { value: 'sale', label: 'Sale' },
        ] },
        { name: 'date_from', label: 'Date From', type: 'date' },
        { name: 'date_to', label: 'Date To', type: 'date' },
    ];

    const columns = [
        { key: 'date', label: 'Date', render: (v) => new Date(v).toLocaleDateString() },
        { key: 'asset_name', label: 'Asset' },
        { key: 'category_name', label: 'Category' },
        {
            key: 'payment_type',
            label: 'Type',
            render: (v) => v === 'sale'
                ? <Badge variant="info" size="sm">Sale</Badge>
                : <Badge variant="success" size="sm">Purchase</Badge>,
        },
        {
            key: 'amount',
            label: 'Amount',
            render: (v, row) => (
                <span className={`inline-flex items-center gap-1 font-semibold ${row.direction === 'inflow' ? 'text-success-600' : 'text-error-600'}`}>
                    {row.direction === 'inflow' ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
                    Rs. {fmt(v)}
                </span>
            ),
        },
        { key: 'allocations', label: 'Method', render: (v) => <MethodSplitDisplay allocations={v} /> },
    ];

    if (!isAdmin) {
        return (
            <div className="text-center py-16">
                <div className="w-16 h-16 rounded-full bg-error-50 flex items-center justify-center mx-auto mb-4">
                    <ShieldAlert className="w-8 h-8 text-error-500" />
                </div>
                <h2 className="text-2xl font-semibold text-neutral-900">Access Denied</h2>
                <p className="text-neutral-500 mt-2">Only admins or superusers can view asset payments.</p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div>
                <BackLink to="/assets">Back to Assets</BackLink>
                <div className="flex items-center gap-3 mt-2">
                    <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-primary-700 to-accent-600 flex items-center justify-center shadow-lg shadow-primary-900/20 flex-shrink-0">
                        <Receipt className="w-5 h-5 text-white" />
                    </div>
                    <div>
                        <h1 className="text-3xl font-bold text-neutral-900">Asset Payments</h1>
                        <p className="text-neutral-500 mt-0.5">
                            Every real cash movement from assets — purchases and sales — newest first.
                        </p>
                    </div>
                </div>
            </div>

            {error && (
                <InlineAlert variant="error" message={error} onRetry={refetch} />
            )}

            <div className="flex flex-col sm:flex-row gap-3">
                <div className="flex-1">
                    <SearchBar value={searchTerm} onChange={handleSearch} placeholder="Search by asset name..." />
                </div>
                <div className="flex gap-3">
                    <Button variant="secondary" icon={showFilters ? X : SlidersHorizontal} onClick={() => setShowFilters(!showFilters)}>
                        {showFilters ? 'Hide Filters' : 'Show Filters'}
                    </Button>
                    {Object.keys(filters).length > 0 && (
                        <Button variant="secondary" onClick={handleResetFilters}>Clear Filters</Button>
                    )}
                </div>
            </div>
            {showFilters && (
                <FilterBar filters={filterConfig} onApply={handleApplyFilters} onReset={handleResetFilters} />
            )}

            {loading ? (
                <div className="flex items-center justify-center py-12">
                    <LoadingSpinner size="lg" />
                </div>
            ) : payments.length === 0 ? (
                <EmptyState
                    icon={<Receipt className="w-8 h-8 text-neutral-400" />}
                    title="No Asset Payments Yet"
                    description="Payments appear here once a new asset is purchased or a disposed asset is sold."
                />
            ) : (
                <>
                    <Table columns={columns} data={payments} onRowClick={handleRowClick} />
                    {meta.totalPages > 1 && (
                        <Pagination currentPage={meta.currentPage} totalPages={meta.totalPages} onPageChange={setPage} />
                    )}
                </>
            )}
        </div>
    );
};

export default AssetPaymentsPage;
