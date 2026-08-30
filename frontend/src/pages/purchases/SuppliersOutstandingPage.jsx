import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SlidersHorizontal, X, CircleCheckBig, Wallet } from 'lucide-react';
import { useSuppliersOutstanding } from '../../hooks/usePurchases';
import Table from '../../components/ui/Table';
import SearchBar from '../../components/ui/SearchBar';
import Button from '../../components/ui/Button';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import FilterBar from '../../components/ui/FilterBar';
import Pagination from '../../components/ui/Pagination';
import Card from '../../components/ui/Card';
import InlineAlert from '../../components/ui/InlineAlert';
import EmptyState from '../../components/ui/EmptyState';

const SuppliersOutstandingPage = () => {
    const navigate = useNavigate();
    const { data, meta, page, setPage, loading, error, filters, setFilters, refetch } = useSuppliersOutstanding();
    const [showFilters, setShowFilters] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');

    const handleSearch = (value) => {
        setSearchTerm(value);
        const next = { ...filters };
        if (value) {
            next.search = value;
        } else {
            delete next.search;
        }
        setFilters(next);
    };

    const handleApplyFilters = (filterValues) => {
        setFilters({
            ...filterValues,
            ...(filters.search ? { search: filters.search } : {}),
        });
    };

    const handleResetFilters = () => {
        setSearchTerm('');
        setFilters({});
    };

    const filterConfig = [
        {
            name: 'payment_status',
            label: 'Payment Status',
            type: 'select',
            options: [
                { value: 'unpaid', label: 'Unpaid' },
                { value: 'partial', label: 'Partial' },
            ],
        },
        { name: 'min_outstanding', label: 'Min Outstanding', type: 'number' },
        { name: 'max_outstanding', label: 'Max Outstanding', type: 'number' },
    ];

    const columns = [
        { key: 'code', label: 'Code', width: '120px' },
        { key: 'name', label: 'Name' },
        {
            key: 'outstanding',
            label: 'Outstanding (PKR)',
            render: (value) => (
                <span className="font-semibold text-error-600">
                    Rs. {typeof value === 'string' ? parseFloat(value).toFixed(2) : '0.00'}
                </span>
            )
        },
    ];

    if (loading && data.length === 0) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center gap-3">
                <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-primary-600 to-accent-600 flex items-center justify-center shadow-lg shadow-primary-900/20 flex-shrink-0">
                    <Wallet className="w-5 h-5 text-white" />
                </div>
                <div>
                    <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900">Suppliers Outstanding</h1>
                    <p className="text-neutral-500 mt-0.5 text-sm sm:text-base">
                        {data.length} supplier{data.length !== 1 ? 's' : ''} with an outstanding balance
                    </p>
                </div>
            </div>

            {error && (
                <InlineAlert variant="error" message={error} onRetry={refetch} />
            )}

            <div className="space-y-4">
                <div className="flex flex-col sm:flex-row gap-3">
                    <div className="flex-1">
                        <SearchBar
                            onSearch={handleSearch}
                            placeholder="Search suppliers..."
                            className="w-full"
                        />
                    </div>
                    <div className="flex gap-3">
                        <Button
                            variant="secondary"
                            onClick={() => setShowFilters(!showFilters)}
                            icon={SlidersHorizontal}
                            className="flex-1 sm:flex-initial"
                        >
                            {showFilters ? 'Hide Filters' : 'Show Filters'}
                        </Button>
                        {(Object.keys(filters).length > 0 || searchTerm) && (
                            <Button variant="secondary" onClick={handleResetFilters} icon={X}>
                                Clear All
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

            <Card className="p-0 overflow-hidden" hover={false}>
                {data.length === 0 ? (
                    <EmptyState
                        icon={<CircleCheckBig className="w-8 h-8 text-success-500" />}
                        title="No suppliers with outstanding balance"
                        description="All suppliers have settled their balances."
                    />
                ) : (
                    <>
                        <div className="p-2">
                            <Table
                                columns={columns}
                                data={data}
                                onRowClick={(supplier) => navigate(`/purchases/suppliers/${supplier.id}`)}
                            />
                        </div>

                        {meta.totalPages > 1 && (
                            <div className="px-4 pb-4">
                                <Pagination
                                    currentPage={meta.currentPage}
                                    totalPages={meta.totalPages}
                                    onPageChange={setPage}
                                />
                            </div>
                        )}
                    </>
                )}
            </Card>
        </div>
    );
};

export default SuppliersOutstandingPage;
