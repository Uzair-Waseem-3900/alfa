import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Tag, Printer } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { reportsApi } from '../../services/reportsApi';
import { usePaginatedList } from '../../hooks/usePaginatedList';
import { printReport } from '../../utils/print';
import { extractErrorMessage } from '../../utils/errorMessage';
import Card from '../../components/ui/Card';
import Table from '../../components/ui/Table';
import Button from '../../components/ui/Button';
import BackLink from '../../components/ui/BackLink';
import SearchBar from '../../components/ui/SearchBar';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Pagination from '../../components/ui/Pagination';
import InlineAlert from '../../components/ui/InlineAlert';
import EmptyState from '../../components/ui/EmptyState';

const formatCurrency = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : value;
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const columns = [
    { key: 'product_name', label: 'Product' },
    { key: 'product_code', label: 'Code' },
    { key: 'category_name', label: 'Category' },
    { key: 'quantity_on_hand', label: 'Quantity On Hand' },
    { key: 'avg_unit_cost', label: 'Avg Unit Cost (PKR)', render: formatCurrency },
    { key: 'total_value', label: 'Total Value (PKR)', render: formatCurrency },
];

const InventoryValuationReportPage = () => {
    const { user } = useAuth();
    const navigate = useNavigate();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const [searchTerm, setSearchTerm] = useState('');
    const [printing, setPrinting] = useState(false);

    // Point-in-time snapshot — no date filters, just an optional search.
    const fetchValuationPage = (params) => {
        const p = { ...params };
        if (searchTerm) p.search = searchTerm;
        return reportsApi.inventoryValuation.get(p);
    };

    const {
        data: results, meta, extra, page, setPage, loading, error, refetch,
    } = usePaginatedList(fetchValuationPage, {}, 25, [searchTerm]);

    // Stats are computed server-side over the full filtered set (not just
    // the current page) and passed through as an extra top-level field.
    const stats = extra?.stats;

    if (!isAdmin) {
        navigate('/dashboard');
        return null;
    }

    const handleSearch = (value) => {
        setSearchTerm(value);
        setPage(1);
    };

    const handlePrint = async () => {
        setPrinting(true);
        try {
            await printReport('/reports/inventory-valuation/print/', searchTerm ? { search: searchTerm } : {});
        } catch (err) {
            toast.error(extractErrorMessage(err, 'Failed to print report'));
        } finally {
            setPrinting(false);
        }
    };

    return (
        <div className="space-y-6">
            <div>
                <BackLink to="/reports">Back to Reports</BackLink>
                <div className="flex items-center gap-3 mt-2">
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-700 to-accent-600 flex items-center justify-center shadow-md shadow-primary-900/20 flex-shrink-0">
                        <Tag className="w-5 h-5 text-white" />
                    </div>
                    <h1 className="text-3xl font-bold text-neutral-900">Inventory Valuation Report</h1>
                </div>
                <p className="text-neutral-500 mt-1">Live snapshot of current stock valued at FIFO cost — no date range, this is right now</p>
            </div>

            <div className="flex flex-col sm:flex-row gap-4 items-start">
                <SearchBar
                    onSearch={handleSearch}
                    placeholder="Search products by name or code..."
                    className="flex-1 w-full"
                />
                <Button variant="secondary" icon={Printer} onClick={handlePrint} loading={printing} className="w-full sm:w-auto">
                    Print
                </Button>
            </div>

            {error && <InlineAlert variant="error" message={error} onRetry={refetch} />}

            {loading ? (
                <div className="flex items-center justify-center min-h-[40vh]">
                    <LoadingSpinner size="lg" />
                </div>
            ) : (
                <>
                    {stats && (
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                            <Card className="p-4">
                                <p className="text-sm text-neutral-500">Total Products</p>
                                <p className="text-2xl font-bold text-neutral-900">{stats.total_products}</p>
                            </Card>
                            <Card className="p-4">
                                <p className="text-sm text-neutral-500">Total Quantity On Hand</p>
                                <p className="text-2xl font-bold text-neutral-900">{stats.total_quantity_on_hand}</p>
                            </Card>
                            <Card className="p-4">
                                <p className="text-sm text-neutral-500">Total Inventory Value (PKR)</p>
                                <p className="text-2xl font-bold text-success-600">
                                    {Number(stats.total_inventory_value || 0).toFixed(2)}
                                </p>
                            </Card>
                        </div>
                    )}

                    {results.length === 0 ? (
                        <EmptyState
                            title="No Stock Found"
                            description="Try adjusting your search"
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

export default InventoryValuationReportPage;
