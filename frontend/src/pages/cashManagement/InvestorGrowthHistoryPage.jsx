import { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { TrendingUp, SlidersHorizontal } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useInvestorValuationEntries } from '../../hooks/useCashManagement';
import { cashManagementApi } from '../../services/cashManagementApi';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Table from '../../components/ui/Table';
import Button from '../../components/ui/Button';
import FilterBar from '../../components/ui/FilterBar';
import Pagination from '../../components/ui/Pagination';
import BackLink from '../../components/ui/BackLink';
import EmptyState from '../../components/ui/EmptyState';
import InlineAlert from '../../components/ui/InlineAlert';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const InvestorGrowthHistoryPage = () => {
    const { user } = useAuth();
    const navigate = useNavigate();
    const location = useLocation();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const initialInvestorId = location.state?.investor_id;

    const {
        data: entries, meta, page, setPage, loading, error, filters, setFilters, refetch,
    } = useInvestorValuationEntries(initialInvestorId ? { investor_id: initialInvestorId } : {});

    const [showFilters, setShowFilters] = useState(!!initialInvestorId);
    const [investors, setInvestors] = useState([]);

    useEffect(() => {
        cashManagementApi.investors.getAll({ page_size: 500 })
            .then((res) => setInvestors(res?.results ?? res ?? []))
            .catch(() => setInvestors([]));
    }, []);

    const handleApplyFilters = (values) => setFilters(values);
    const handleResetFilters = () => setFilters({});
    const handleRowClick = (row) => navigate(`/cash-management/investors/${row.investor}`);

    const filterConfig = [
        { name: 'investor_id', label: 'Investor', type: 'select', options: [
            { value: '', label: 'All' },
            ...investors.map((i) => ({ value: i.id, label: i.name })),
        ] },
    ];

    const columns = [
        { key: 'investor_name', label: 'Investor' },
        { key: 'period', label: 'Period' },
        { key: 'rate_applied', label: 'Rate', render: (v) => `${(parseFloat(v) * 100).toFixed(2)}%` },
        { key: 'worth_before', label: 'Worth Before', render: (v) => `Rs. ${fmt(v)}` },
        {
            key: 'amount',
            label: 'Growth',
            render: (v) => <span className="font-semibold text-success-600">+Rs. {fmt(v)}</span>,
        },
        { key: 'worth_after', label: 'Worth After', render: (v) => <span className="font-semibold">Rs. {fmt(v)}</span> },
        { key: 'note', label: 'Note', render: (v) => v || <span className="text-neutral-300">—</span> },
    ];

    if (!isAdmin) {
        return (
            <div className="text-center py-16">
                <h2 className="text-2xl font-semibold text-neutral-900">Access Denied</h2>
                <p className="text-neutral-500 mt-2">Only admins or superusers can view investor growth history.</p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div>
                <BackLink to="/cash-management/investors">Back to Investors</BackLink>
                <div className="flex items-center gap-2.5 mt-2">
                    <TrendingUp className="w-6 h-6 text-primary-600" />
                    <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900">Investor Growth History</h1>
                </div>
                <p className="text-neutral-500 mt-1">
                    Every monthly compounding entry ever posted, across all investors — informational only, never used for withdrawal validation.
                </p>
            </div>

            <div className="flex gap-3">
                <Button variant="secondary" size="sm" icon={SlidersHorizontal} onClick={() => setShowFilters(!showFilters)}>
                    {showFilters ? 'Hide Filters' : 'Show Filters'}
                </Button>
                {Object.keys(filters).length > 0 && (
                    <Button variant="secondary" size="sm" onClick={handleResetFilters}>Clear Filters</Button>
                )}
            </div>
            {showFilters && (
                <FilterBar filters={filterConfig} onApply={handleApplyFilters} onReset={handleResetFilters} />
            )}

            {error && !loading && (
                <InlineAlert variant="error" title="Couldn't load growth history" message={error} onRetry={refetch} />
            )}

            {loading ? (
                <div className="flex items-center justify-center py-16">
                    <LoadingSpinner size="lg" />
                </div>
            ) : entries.length === 0 ? (
                <EmptyState
                    icon={<TrendingUp className="w-8 h-8 text-neutral-400 mx-auto" />}
                    title="No Growth Yet"
                    description="Monthly growth entries appear automatically for investors with a growth rate set."
                />
            ) : (
                <>
                    <Table columns={columns} data={entries} onRowClick={handleRowClick} />
                    {meta.totalPages > 1 && (
                        <Pagination currentPage={meta.currentPage} totalPages={meta.totalPages} onPageChange={setPage} />
                    )}
                </>
            )}
        </div>
    );
};

export default InvestorGrowthHistoryPage;
