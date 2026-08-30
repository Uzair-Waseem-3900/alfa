import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, TrendingDown, Printer } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { accountingApi } from '../../services/accountingApi';
import { usePaginatedList } from '../../hooks/usePaginatedList';
import { printReport } from '../../utils/print';
import { extractErrorMessage } from '../../utils/errorMessage';
import Card from '../../components/ui/Card';
import Table from '../../components/ui/Table';
import Badge from '../../components/ui/Badge';
import Button from '../../components/ui/Button';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Pagination from '../../components/ui/Pagination';
import InlineAlert from '../../components/ui/InlineAlert';
import EmptyState from '../../components/ui/EmptyState';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const BUCKET_LABELS = {
    current: 'Current',
    '1_30': '1–30 Days',
    '31_60': '31–60 Days',
    '61_90': '61–90 Days',
    over_90: 'Over 90 Days',
};

const BUCKET_VARIANTS = {
    current: 'success',
    '1_30': 'info',
    '31_60': 'warning',
    '61_90': 'warning',
    over_90: 'error',
};

const columns = [
    {
        key: 'order_number',
        label: 'Order #',
        render: (value) => <span className="font-mono text-sm font-medium text-neutral-800">{value}</span>,
    },
    { key: 'supplier_name', label: 'Supplier' },
    {
        key: 'supplier_code',
        label: 'Code',
        render: (value) => <span className="font-mono text-xs text-neutral-500">{value}</span>,
    },
    {
        key: 'confirmed_date',
        label: 'Confirmed On',
        render: (value) => value ? new Date(value).toLocaleDateString() : 'N/A',
    },
    {
        key: 'days_overdue',
        label: 'Days Since Confirmed',
        render: (value) => <span className="font-semibold text-neutral-700">{value}</span>,
    },
    {
        key: 'bucket',
        label: 'Aging Bucket',
        render: (value) => (
            <Badge variant={BUCKET_VARIANTS[value] || 'default'}>{BUCKET_LABELS[value] || value}</Badge>
        ),
    },
    {
        key: 'outstanding',
        label: 'Outstanding (PKR)',
        render: (value) => <span className="font-semibold text-neutral-900">Rs. {fmt(value)}</span>,
    },
];

const APAgingPage = () => {
    const { user } = useAuth();
    const navigate = useNavigate();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const {
        data: results, meta, extra, page, setPage, loading, error, filters, setFilters, refetch,
    } = usePaginatedList(accountingApi.apAging.get, {});

    const summary = extra?.summary;
    const activeBucket = filters.bucket;
    const [printing, setPrinting] = useState(false);

    const handleBucketClick = (key) => {
        setFilters(activeBucket === key ? {} : { bucket: key });
    };

    const handlePrint = async () => {
        setPrinting(true);
        try {
            await printReport('/accounting/ap-aging/print/', filters);
        } catch (err) {
            toast.error(extractErrorMessage(err, 'Failed to print report'));
        } finally {
            setPrinting(false);
        }
    };

    if (!isAdmin) {
        navigate('/dashboard');
        return null;
    }

    return (
        <div className="space-y-6">
            <div className="p-4 bg-amber-50 border-l-4 border-amber-500 rounded-r-xl flex gap-3">
                <AlertTriangle className="w-5 h-5 flex-shrink-0 mt-0.5 text-amber-600" />
                <div>
                    <p className="text-sm font-semibold text-amber-800">
                        This is an internal aging estimate, not a certified financial statement.
                    </p>
                    <p className="text-sm text-amber-700 mt-0.5">
                        Suppliers here have no tracked due date, so buckets are based on days since the
                        purchase order was confirmed, not a formal credit term. Always independently verify.
                    </p>
                </div>
            </div>

            <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
                <div>
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-700 to-accent-600 flex items-center justify-center shadow-md shadow-primary-900/20 flex-shrink-0">
                            <TrendingDown className="w-5 h-5 text-white" />
                        </div>
                        <h1 className="text-3xl font-bold text-neutral-900">A/P Aging Report</h1>
                    </div>
                    <p className="text-neutral-500 mt-1">
                        Outstanding supplier purchase orders, bucketed by age since confirmation.
                    </p>
                </div>
                <Button variant="secondary" icon={Printer} onClick={handlePrint} loading={printing}>
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
                    {summary && (
                        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                            {Object.entries(BUCKET_LABELS).map(([key, label]) => (
                                <Card
                                    key={key}
                                    onClick={() => handleBucketClick(key)}
                                    className={`p-4 cursor-pointer transition-shadow hover:shadow-md ${
                                        activeBucket === key ? 'ring-2 ring-primary-500' : ''
                                    }`}
                                >
                                    <p className="text-xs text-neutral-500 mb-1">{label}</p>
                                    <p className="text-lg font-bold text-neutral-900">
                                        Rs. {fmt(summary.buckets?.[key]?.total ?? 0)}
                                    </p>
                                    <p className="text-xs text-neutral-400 mt-0.5">
                                        {summary.buckets?.[key]?.count ?? 0} order(s)
                                    </p>
                                </Card>
                            ))}
                        </div>
                    )}

                    {activeBucket && (
                        <div className="flex items-center gap-2 text-sm text-neutral-600">
                            Showing only <Badge variant={BUCKET_VARIANTS[activeBucket]}>{BUCKET_LABELS[activeBucket]}</Badge>
                            <button
                                type="button"
                                onClick={() => setFilters({})}
                                className="text-primary-600 hover:text-primary-700 font-medium"
                            >
                                Clear filter
                            </button>
                        </div>
                    )}

                    {results.length === 0 ? (
                        <EmptyState
                            title={activeBucket ? 'No Orders In This Bucket' : 'No Outstanding Payables'}
                            description={activeBucket ? 'Try a different bucket or clear the filter.' : 'Every confirmed purchase order is fully paid.'}
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

export default APAgingPage;
