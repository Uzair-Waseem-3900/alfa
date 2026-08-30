import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SlidersHorizontal, X, CheckCircle2 } from 'lucide-react';
import Table from '../../components/ui/Table';
import SearchBar from '../../components/ui/SearchBar';
import Button from '../../components/ui/Button';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Badge from '../../components/ui/Badge';
import FilterBar from '../../components/ui/FilterBar';
import Pagination from '../../components/ui/Pagination';
import InlineAlert from '../../components/ui/InlineAlert';
import EmptyState from '../../components/ui/EmptyState';
import Card from '../../components/ui/Card';
import { billingApi } from '../../services/billingApi';
import { usePaginatedList } from '../../hooks/usePaginatedList';

const CustomerOutstandingPage = () => {
    const navigate = useNavigate();

    const [searchTerm, setSearchTerm] = useState('');
    const [showFilters, setShowFilters] = useState(false);

    const fetchCustomersPage = (params) => {
        const p = { ...params };
        if (searchTerm) p.search = searchTerm;
        return billingApi.customers.getOutstanding(p);
    };

    const {
        data: customers, meta, setPage, loading, error, refetch,
        filters, setFilters,
    } = usePaginatedList(fetchCustomersPage, {}, 25, [searchTerm]);

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
        { key: 'code', label: 'Code', width: '120px' },
        { key: 'name', label: 'Name' },
        {
            key: 'outstanding',
            label: 'Outstanding (PKR)',
            render: (value) => {
                const num = typeof value === 'string' ? parseFloat(value) : value;
                return isNaN(num) ? '0.00' : num.toFixed(2);
            }
        },
        {
            key: 'payment_status',
            label: 'Status',
            render: (value) => (
                <Badge variant={value === 'paid' ? 'paid' : value === 'partial' ? 'partial' : 'unpaid'}>
                    {value || 'N/A'}
                </Badge>
            ),
        },
    ];

    const filterConfig = [
        {
            name: 'payment_status',
            label: 'Payment Status',
            type: 'select',
            options: [
                { value: '', label: 'All Status' },
                { value: 'unpaid', label: 'Unpaid' },
                { value: 'partial', label: 'Partial' },
            ],
        },
        { name: 'min_outstanding', label: 'Min Outstanding', type: 'number' },
        { name: 'max_outstanding', label: 'Max Outstanding', type: 'number' },
    ];

    // Section-level spinner: header renders immediately, only the results
    // area blocks on the first load. Later filter/search changes keep the
    // existing rows visible (loading indicator inside the table area).
    const initialLoading = loading && customers.length === 0 && !error;

    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-3xl font-bold text-neutral-900">Customers Outstanding</h1>
                <p className="text-neutral-500 mt-1">View customers with outstanding balances</p>
                <p className="text-sm text-neutral-400 mt-1">
                    {meta.count} customer{meta.count !== 1 ? 's' : ''} with outstanding balance
                </p>
            </div>

            <Card className="p-4 sm:p-5" hover={false}>
                <div className="flex flex-col sm:flex-row gap-3">
                    <SearchBar
                        onSearch={handleSearch}
                        placeholder="Search by name or code..."
                        className="flex-1"
                        value={searchTerm}
                    />
                    <Button
                        variant="secondary"
                        onClick={() => setShowFilters(!showFilters)}
                        icon={SlidersHorizontal}
                        className="flex-shrink-0"
                    >
                        {showFilters ? 'Hide Filters' : 'Show Filters'}
                    </Button>
                    {(Object.keys(filters).length > 0 || searchTerm) && (
                        <Button variant="secondary" onClick={handleResetFilters} icon={X} className="flex-shrink-0">
                            Clear All
                        </Button>
                    )}
                </div>

                {showFilters && (
                    <div className="mt-4">
                        <FilterBar
                            filters={filterConfig}
                            onApply={handleApplyFilters}
                            onReset={handleResetFilters}
                        />
                    </div>
                )}
            </Card>

            {error && <InlineAlert variant="error" message={error} onRetry={refetch} />}

            {initialLoading ? (
                <div className="flex items-center justify-center min-h-[40vh]">
                    <LoadingSpinner size="lg" />
                </div>
            ) : customers.length === 0 ? (
                !error && (
                    <EmptyState
                        icon={<CheckCircle2 className="w-8 h-8 text-success-500" />}
                        title="No Customers with Outstanding"
                        description="All customers have settled their balances."
                    />
                )
            ) : (
                <Card className="p-0 overflow-hidden" hover={false}>
                    <div className={`relative transition-opacity ${loading ? 'opacity-60' : 'opacity-100'}`}>
                        {loading && (
                            <div className="absolute right-4 top-4 z-10">
                                <LoadingSpinner size="sm" />
                            </div>
                        )}
                        <Table
                            columns={columns}
                            data={customers}
                            onRowClick={(customer) => navigate(`/billing/customers/${customer.id}`)}
                        />
                    </div>
                </Card>
            )}

            {meta.totalPages > 1 && customers.length > 0 && (
                <Pagination
                    currentPage={meta.currentPage}
                    totalPages={meta.totalPages}
                    onPageChange={setPage}
                />
            )}
        </div>
    );
};

export default CustomerOutstandingPage;
