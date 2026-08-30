import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { PackageX, Printer, SlidersHorizontal, X } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { reportsApi } from '../../services/reportsApi';
import { usePaginatedList } from '../../hooks/usePaginatedList';
import { printReport } from '../../utils/print';
import { extractErrorMessage } from '../../utils/errorMessage';
import Card from '../../components/ui/Card';
import Table from '../../components/ui/Table';
import Button from '../../components/ui/Button';
import Badge from '../../components/ui/Badge';
import FilterBar from '../../components/ui/FilterBar';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Pagination from '../../components/ui/Pagination';
import BackLink from '../../components/ui/BackLink';
import InlineAlert from '../../components/ui/InlineAlert';
import EmptyState from '../../components/ui/EmptyState';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const filterConfig = [
    { name: 'date',      label: 'Exact Date', type: 'date' },
    { name: 'date_from', label: 'Date From',  type: 'date' },
    { name: 'date_to',   label: 'Date To',    type: 'date' },
];

const columns = [
    {
        key: 'reference_number',
        label: 'Reference #',
        width: '150px',
        render: (value) => <span className="font-mono text-sm font-medium text-neutral-800">{value}</span>,
    },
    { key: 'product_name', label: 'Product' },
    {
        key: 'product_code',
        label: 'Code',
        render: (value) => <span className="font-mono text-xs text-neutral-500">{value}</span>,
    },
    {
        key: 'reason',
        label: 'Reason',
        render: (value) => value
            ? <Badge variant="warning" size="sm">{value}</Badge>
            : <span className="text-neutral-300">—</span>,
    },
    {
        key: 'quantity',
        label: 'Lost Qty',
        render: (value) => <span className="font-semibold text-error-600">{value}</span>,
    },
    {
        key: 'found_quantity',
        label: 'Found Qty',
        render: (value) => value > 0
            ? <span className="font-semibold text-success-600">{value}</span>
            : <span className="text-neutral-300">—</span>,
    },
    {
        key: 'unit_cost',
        label: 'Unit Cost (PKR)',
        render: (value) => fmt(value),
    },
    {
        key: 'total_cost',
        label: 'Total Lost (PKR)',
        render: (value) => (
            <span className="font-semibold text-error-600">Rs. {fmt(value)}</span>
        ),
    },
    {
        key: 'recovered_amount',
        label: 'Recovered (PKR)',
        render: (value) => parseFloat(value) > 0
            ? <span className="font-semibold text-success-600">Rs. {fmt(value)}</span>
            : <span className="text-neutral-300">—</span>,
    },
    {
        key: 'net_amount',
        label: 'Net Loss (PKR)',
        render: (value) => (
            <span className="font-semibold text-warning-700">Rs. {fmt(value)}</span>
        ),
    },
    {
        key: 'created_at',
        label: 'Date',
        render: (value) => value ? new Date(value).toLocaleDateString() : 'N/A',
    },
];

const LostInventoryReportPage = () => {
    const { user } = useAuth();
    const navigate = useNavigate();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const [showFilters, setShowFilters] = useState(false);
    const [printing, setPrinting] = useState(false);

    const {
        data: results, meta, extra, page, setPage, loading, error,
        filters, setFilters, refetch,
    } = usePaginatedList(reportsApi.lostInventory.get, {});

    const stats = extra?.stats;

    if (!isAdmin) {
        navigate('/dashboard');
        return null;
    }

    const handleApplyFilters = (filterValues) => setFilters(filterValues);
    const handleResetFilters = () => setFilters({});

    const handlePrint = async () => {
        setPrinting(true);
        try {
            await printReport('/reports/lost-inventory/print/', filters);
        } catch (err) {
            toast.error(extractErrorMessage(err, 'Failed to print report'));
        } finally {
            setPrinting(false);
        }
    };

    return (
        <div className="space-y-6">
            {/* Header */}
            <div>
                <BackLink to="/reports">Back to Reports</BackLink>
                <div className="flex items-center gap-3 mt-2">
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-700 to-accent-600 flex items-center justify-center shadow-md shadow-primary-900/20 flex-shrink-0">
                        <PackageX className="w-5 h-5 text-white" />
                    </div>
                    <h1 className="text-3xl font-bold text-neutral-900">Lost Inventory Report</h1>
                </div>
                <p className="text-neutral-500 mt-1">
                    Products marked as lost, damaged, or missing — including partial or full recoveries
                </p>
            </div>

            {/* Filters */}
            <div className="space-y-4">
                <div className="flex flex-wrap gap-3">
                    <Button
                        variant="secondary"
                        onClick={() => setShowFilters(!showFilters)}
                        icon={SlidersHorizontal}
                    >
                        {showFilters ? 'Hide Filters' : 'Show Filters'}
                    </Button>
                    {Object.keys(filters).length > 0 && (
                        <Button variant="secondary" icon={X} onClick={handleResetFilters}>
                            Clear Filters
                        </Button>
                    )}
                    <Button variant="secondary" icon={Printer} onClick={handlePrint} loading={printing}>
                        Print
                    </Button>
                </div>

                {showFilters && (
                    <FilterBar
                        filters={filterConfig}
                        onApply={handleApplyFilters}
                        onReset={handleResetFilters}
                    />
                )}
            </div>

            {error && <InlineAlert variant="error" message={error} onRetry={refetch} />}

            {loading ? (
                <div className="flex items-center justify-center min-h-[40vh]">
                    <LoadingSpinner size="lg" />
                </div>
            ) : (
                <>
                    {/* Stats cards */}
                    {stats && (
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                            <Card className="p-4">
                                <p className="text-xs text-neutral-500 mb-1">Total Lost Items</p>
                                <p className="text-2xl font-bold text-neutral-900">
                                    {stats.total_lost_items ?? 0}
                                </p>
                            </Card>
                            <Card className="p-4">
                                <p className="text-xs text-neutral-500 mb-1">Total Lost Value (PKR)</p>
                                <p className="text-2xl font-bold text-error-600">
                                    Rs. {fmt(stats.total_lost_cash)}
                                </p>
                            </Card>
                            <Card className="p-4">
                                <p className="text-xs text-neutral-500 mb-1">Recovered (PKR)</p>
                                <p className="text-2xl font-bold text-success-600">
                                    Rs. {fmt(stats.total_recovered_cash)}
                                </p>
                            </Card>
                            <Card className="p-4">
                                <p className="text-xs text-neutral-500 mb-1">Net Loss (PKR)</p>
                                <p className="text-2xl font-bold text-warning-700">
                                    Rs. {fmt(stats.net_lost_cash)}
                                </p>
                            </Card>
                        </div>
                    )}

                    {/* Table */}
                    {results.length === 0 ? (
                        <EmptyState
                            title="No Lost Inventory Found"
                            description="Try adjusting your date filters"
                        />
                    ) : (
                        <>
                            <Card className="p-0 overflow-hidden">
                                <Table columns={columns} data={results} />
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
                </>
            )}
        </div>
    );
};

export default LostInventoryReportPage;
