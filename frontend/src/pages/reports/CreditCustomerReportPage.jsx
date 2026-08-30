import { useNavigate } from 'react-router-dom';
import { CreditCard } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { creditScoreApi } from '../../services/creditScoreApi';
import { usePaginatedList } from '../../hooks/usePaginatedList';
import Card from '../../components/ui/Card';
import Table from '../../components/ui/Table';
import Button from '../../components/ui/Button';
import BackLink from '../../components/ui/BackLink';
import Badge from '../../components/ui/Badge';
import SearchBar from '../../components/ui/SearchBar';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Pagination from '../../components/ui/Pagination';
import InlineAlert from '../../components/ui/InlineAlert';
import EmptyState from '../../components/ui/EmptyState';

const TIER_BADGE_VARIANT = {
    good: 'success',
    average: 'warning',
    poor: 'error',
};

const columns = [
    { key: 'customer_code', label: 'Code', width: '100px' },
    { key: 'customer_name', label: 'Customer' },
    { key: 'score', label: 'Score', width: '100px' },
    {
        key: 'tier',
        label: 'Tier',
        render: (value, row) => (
            <Badge variant={TIER_BADGE_VARIANT[value] || 'default'}>{row.tier_display}</Badge>
        ),
    },
    {
        key: 'last_calculated_at',
        label: 'Last Calculated',
        render: (value) => value ? new Date(value).toLocaleString() : 'N/A',
    },
];

const TIER_TABS = [
    { value: '', label: 'All' },
    { value: 'good', label: 'Good (70+)' },
    { value: 'average', label: 'Average (31-69)' },
    { value: 'poor', label: 'Poor (≤30)' },
];

const CreditCustomerReportPage = () => {
    const { user } = useAuth();
    const navigate = useNavigate();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const {
        data: results, meta, page, setPage, loading, error,
        filters, setFilters, refetch,
    } = usePaginatedList(creditScoreApi.customers.getAll, {});

    if (!isAdmin) {
        navigate('/dashboard');
        return null;
    }

    const activeTier = filters.tier || '';

    const handleTierChange = (tier) => {
        setFilters({ ...filters, tier: tier || undefined });
    };

    const handleSearch = (value) => {
        setFilters({ ...filters, search: value || undefined });
    };

    const handleClearFilters = () => {
        setFilters({});
    };

    const handleRowClick = (row) => {
        navigate(`/billing/customers/${row.customer_id}`);
    };

    return (
        <div className="space-y-6">
            <div>
                <BackLink to="/reports">Back to Reports</BackLink>
                <div className="flex items-center gap-3 mt-2">
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-700 to-accent-600 flex items-center justify-center shadow-md shadow-primary-900/20 flex-shrink-0">
                        <CreditCard className="w-5 h-5 text-white" />
                    </div>
                    <h1 className="text-3xl font-bold text-neutral-900">Credit Customer Report</h1>
                </div>
                <p className="text-neutral-500 mt-1">Customers grouped by their system-calculated credit score</p>
            </div>

            <div className="space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                    <SearchBar
                        onSearch={handleSearch}
                        placeholder="Search by customer name or code..."
                        value={filters.search || ''}
                        className="w-full flex-1"
                    />
                    {(filters.search || activeTier) && (
                        <Button variant="secondary" onClick={handleClearFilters}>
                            Clear Filters
                        </Button>
                    )}
                </div>

                <div className="flex gap-2 flex-wrap">
                    {TIER_TABS.map((tab) => (
                        <Button
                            key={tab.value || 'all'}
                            size="sm"
                            variant={activeTier === tab.value ? 'primary' : 'secondary'}
                            onClick={() => handleTierChange(tab.value)}
                        >
                            {tab.label}
                        </Button>
                    ))}
                </div>
            </div>

            {error && <InlineAlert variant="error" message={error} onRetry={refetch} />}

            {loading ? (
                <div className="flex items-center justify-center min-h-[40vh]">
                    <LoadingSpinner size="lg" />
                </div>
            ) : results.length === 0 ? (
                <EmptyState
                    title="No Customers Found"
                    description="Try a different tier or search term"
                />
            ) : (
                <>
                    <Card className="p-0 overflow-hidden">
                        <Table columns={columns} data={results} onRowClick={handleRowClick} />
                    </Card>
                    {meta.totalPages > 1 && (
                        <Pagination
                            currentPage={meta.currentPage}
                            totalPages={meta.totalPages}
                            onPageChange={setPage}
                        />
                    )}
                </>
            )}
        </div>
    );
};

export default CreditCustomerReportPage;
