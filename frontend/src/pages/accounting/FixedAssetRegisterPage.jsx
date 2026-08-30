import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, Building2, Printer } from 'lucide-react';
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

const columns = [
    { key: 'name', label: 'Asset' },
    { key: 'category', label: 'Category' },
    {
        key: 'acquisition_date',
        label: 'Acquired',
        render: (value) => value ? new Date(value).toLocaleDateString() : 'N/A',
    },
    { key: 'cost', label: 'Cost (PKR)', render: (value) => fmt(value) },
    {
        key: 'accumulated_depreciation',
        label: 'Accum. Depreciation (PKR)',
        render: (value) => <span className="text-warning-700">Rs. {fmt(value)}</span>,
    },
    {
        key: 'net_book_value',
        label: 'Net Book Value (PKR)',
        render: (value) => <span className="font-semibold text-neutral-900">Rs. {fmt(value)}</span>,
    },
    {
        key: 'is_disposed',
        label: 'Status',
        render: (value, row) => value
            ? <Badge variant="error">{row.disposal_type === 'sold' ? 'Sold' : 'Scrapped'}</Badge>
            : <Badge variant="success">Active</Badge>,
    },
];

const FixedAssetRegisterPage = () => {
    const { user } = useAuth();
    const navigate = useNavigate();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const [includeDisposed, setIncludeDisposed] = useState(false);
    const [printing, setPrinting] = useState(false);

    const {
        data: results, meta, extra, page, setPage, loading, error, refetch,
    } = usePaginatedList(
        accountingApi.fixedAssetRegister.get,
        { include_disposed: includeDisposed ? 'true' : undefined },
        25,
        [includeDisposed],
    );

    const summary = extra?.summary;

    const handlePrint = async () => {
        setPrinting(true);
        try {
            // Prints exactly the currently-applied "include disposed" toggle.
            await printReport('/accounting/fixed-asset-register/print/', {
                include_disposed: includeDisposed ? 'true' : undefined,
            });
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
                        This is an internal register, not a certified fixed asset audit.
                    </p>
                    <p className="text-sm text-amber-700 mt-0.5">
                        Cost and depreciation figures are pulled directly from the Assets app. Always
                        independently verify before using for tax or audit purposes.
                    </p>
                </div>
            </div>

            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-700 to-accent-600 flex items-center justify-center shadow-md shadow-primary-900/20 flex-shrink-0">
                            <Building2 className="w-5 h-5 text-white" />
                        </div>
                        <h1 className="text-3xl font-bold text-neutral-900">Fixed Asset Register</h1>
                    </div>
                    <p className="text-neutral-500 mt-1">
                        Every asset's cost, accumulated depreciation, and net book value.
                    </p>
                </div>
                <div className="flex gap-2">
                    <Button variant="secondary" onClick={() => setIncludeDisposed((v) => !v)}>
                        {includeDisposed ? 'Hide Disposed' : 'Include Disposed'}
                    </Button>
                    <Button variant="secondary" icon={Printer} onClick={handlePrint} loading={printing}>
                        Print
                    </Button>
                </div>
            </div>

            {error && <InlineAlert variant="error" message={error} onRetry={refetch} />}

            {loading ? (
                <div className="flex items-center justify-center min-h-[40vh]">
                    <LoadingSpinner size="lg" />
                </div>
            ) : (
                <>
                    {summary && (
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                            <Card className="p-4">
                                <p className="text-xs text-neutral-500 mb-1">Asset Count</p>
                                <p className="text-2xl font-bold text-neutral-900">{summary.asset_count}</p>
                            </Card>
                            <Card className="p-4">
                                <p className="text-xs text-neutral-500 mb-1">Total Cost</p>
                                <p className="text-2xl font-bold text-neutral-900">Rs. {fmt(summary.total_cost)}</p>
                            </Card>
                            <Card className="p-4">
                                <p className="text-xs text-neutral-500 mb-1">Accum. Depreciation</p>
                                <p className="text-2xl font-bold text-warning-700">Rs. {fmt(summary.total_accumulated_depreciation)}</p>
                            </Card>
                            <Card className="p-4">
                                <p className="text-xs text-neutral-500 mb-1">Net Book Value</p>
                                <p className="text-2xl font-bold text-success-600">Rs. {fmt(summary.total_net_book_value)}</p>
                            </Card>
                        </div>
                    )}

                    {results.length === 0 ? (
                        <EmptyState
                            title="No Assets Found"
                            description="Register an asset from the Assets page first."
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

export default FixedAssetRegisterPage;
