import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Calculator, Printer, SlidersHorizontal, X } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { reportsApi } from '../../services/reportsApi';
import { usePaginatedList } from '../../hooks/usePaginatedList';
import { printReport } from '../../utils/print';
import { extractErrorMessage } from '../../utils/errorMessage';
import Card from '../../components/ui/Card';
import Table from '../../components/ui/Table';
import Button from '../../components/ui/Button';
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

const inputColumns = [
    { key: 'order_number', label: 'Order #', render: (v) => <span className="font-mono text-sm font-medium text-neutral-800">{v}</span> },
    { key: 'supplier_name', label: 'Supplier' },
    { key: 'supplier_code', label: 'Code', render: (v) => <span className="font-mono text-xs text-neutral-500">{v}</span> },
    { key: 'gst_total', label: 'GST Paid (PKR)', render: (v) => <span className="font-semibold text-info-600">Rs. {fmt(v)}</span> },
    { key: 'wht_total', label: 'WHT Withheld (PKR)', render: (v) => `Rs. ${fmt(v)}` },
    { key: 'net_payable', label: 'Net Payable (PKR)', render: (v) => `Rs. ${fmt(v)}` },
    { key: 'confirmed_at', label: 'Date', render: (v) => v ? new Date(v).toLocaleDateString() : 'N/A' },
];

const outputColumns = [
    { key: 'bill_number', label: 'Bill #', render: (v) => <span className="font-mono text-sm font-medium text-neutral-800">{v}</span> },
    { key: 'customer_name', label: 'Customer' },
    { key: 'customer_code', label: 'Code', render: (v) => <span className="font-mono text-xs text-neutral-500">{v}</span> },
    { key: 'gst_total', label: 'GST Collected (PKR)', render: (v) => <span className="font-semibold text-purple-600">Rs. {fmt(v)}</span> },
    { key: 'wht_total', label: 'WHT Withheld (PKR)', render: (v) => `Rs. ${fmt(v)}` },
    { key: 'grand_total', label: 'Grand Total (PKR)', render: (v) => `Rs. ${fmt(v)}` },
    { key: 'confirmed_at', label: 'Date', render: (v) => v ? new Date(v).toLocaleDateString() : 'N/A' },
];

const SalesTaxReportPage = () => {
    const { user } = useAuth();
    const navigate = useNavigate();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const [activeTab, setActiveTab] = useState('input'); // 'input' | 'output'
    const [showFilters, setShowFilters] = useState(false);
    const [printing, setPrinting] = useState(false);

    const fetchPage = (params) =>
        activeTab === 'input' ? reportsApi.salesTaxInput.get(params) : reportsApi.salesTaxOutput.get(params);

    const {
        data: results, meta, extra, page, setPage, loading, error,
        filters, setFilters, refetch,
    } = usePaginatedList(fetchPage, {}, 25, [activeTab]);

    const stats = extra?.stats;

    if (!isAdmin) {
        navigate('/dashboard');
        return null;
    }

    const handleApplyFilters = (values) => setFilters(values);
    const handleResetFilters = () => setFilters({});
    const switchTab = (tab) => {
        setActiveTab(tab);
        setFilters({});
        setPage(1);
    };

    const handlePrint = async () => {
        setPrinting(true);
        try {
            const endpoint = activeTab === 'input' ? '/reports/sales-tax/input/print/' : '/reports/sales-tax/output/print/';
            await printReport(endpoint, filters);
        } catch (err) {
            toast.error(extractErrorMessage(err, 'Failed to print report'));
        } finally {
            setPrinting(false);
        }
    };

    const columns = activeTab === 'input' ? inputColumns : outputColumns;

    return (
        <div className="space-y-6">
            <div>
                <BackLink to="/reports">Back to Reports</BackLink>
                <div className="flex items-center gap-3 mt-2">
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-700 to-accent-600 flex items-center justify-center shadow-md shadow-primary-900/20 flex-shrink-0">
                        <Calculator className="w-5 h-5 text-white" />
                    </div>
                    <h1 className="text-3xl font-bold text-neutral-900">Sales Tax Report</h1>
                </div>
                <p className="text-neutral-500 mt-1">
                    Input Tax (GST paid to suppliers) vs Output Tax (GST charged to customers) — see{' '}
                    <Link to="/taxes" className="text-primary-600 hover:text-primary-700 font-medium">Taxes</Link> for the
                    net payable summary and to record payments.
                </p>
            </div>

            <div className="flex gap-2 border-b border-neutral-200">
                <button
                    onClick={() => switchTab('input')}
                    className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                        activeTab === 'input'
                            ? 'border-primary-600 text-primary-600'
                            : 'border-transparent text-neutral-500 hover:text-neutral-700'
                    }`}
                >
                    Input Tax (Purchases)
                </button>
                <button
                    onClick={() => switchTab('output')}
                    className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                        activeTab === 'output'
                            ? 'border-primary-600 text-primary-600'
                            : 'border-transparent text-neutral-500 hover:text-neutral-700'
                    }`}
                >
                    Output Tax (Sales)
                </button>
            </div>

            <div className="flex flex-wrap gap-3">
                <Button variant="secondary" icon={SlidersHorizontal} onClick={() => setShowFilters(!showFilters)}>
                    {showFilters ? 'Hide Filters' : 'Show Filters'}
                </Button>
                {Object.keys(filters).length > 0 && (
                    <Button variant="secondary" icon={X} onClick={handleResetFilters}>Clear Filters</Button>
                )}
                <Button variant="secondary" icon={Printer} onClick={handlePrint} loading={printing}>
                    Print
                </Button>
            </div>
            {showFilters && (
                <FilterBar filters={filterConfig} onApply={handleApplyFilters} onReset={handleResetFilters} />
            )}

            {error && <InlineAlert variant="error" message={error} onRetry={refetch} />}

            {loading ? (
                <div className="flex items-center justify-center min-h-[40vh]">
                    <LoadingSpinner size="lg" />
                </div>
            ) : (
                <>
                    {stats && activeTab === 'input' && (
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                            <Card className="p-4">
                                <p className="text-xs text-neutral-500 mb-1">Total Orders</p>
                                <p className="text-2xl font-bold text-neutral-900">{stats.total_orders ?? 0}</p>
                            </Card>
                            <Card className="p-4">
                                <p className="text-xs text-neutral-500 mb-1">Total Input Tax Paid (PKR)</p>
                                <p className="text-2xl font-bold text-info-600">Rs. {fmt(stats.total_input_tax_paid)}</p>
                            </Card>
                            <Card className="p-4">
                                <p className="text-xs text-neutral-500 mb-1">Total WHT Withheld (PKR)</p>
                                <p className="text-2xl font-bold text-orange-600">Rs. {fmt(stats.total_wht_withheld)}</p>
                            </Card>
                        </div>
                    )}
                    {stats && activeTab === 'output' && (
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                            <Card className="p-4">
                                <p className="text-xs text-neutral-500 mb-1">Total Invoices</p>
                                <p className="text-2xl font-bold text-neutral-900">{stats.total_invoices ?? 0}</p>
                            </Card>
                            <Card className="p-4">
                                <p className="text-xs text-neutral-500 mb-1">Total Output Tax Collected (PKR)</p>
                                <p className="text-2xl font-bold text-purple-600">Rs. {fmt(stats.total_output_tax_collected)}</p>
                            </Card>
                            <Card className="p-4">
                                <p className="text-xs text-neutral-500 mb-1">Total WHT Withheld (PKR)</p>
                                <p className="text-2xl font-bold text-orange-600">Rs. {fmt(stats.total_wht_withheld)}</p>
                            </Card>
                        </div>
                    )}

                    {results.length === 0 ? (
                        <EmptyState
                            title="No Records Found"
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

export default SalesTaxReportPage;
