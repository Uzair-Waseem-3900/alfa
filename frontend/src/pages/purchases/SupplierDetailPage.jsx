import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Truck, Wallet, CheckCircle2, FileText } from 'lucide-react';
import { purchasesApi } from '../../services/purchasesApi';
import BackLink from '../../components/ui/BackLink';
import Card from '../../components/ui/Card';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Table from '../../components/ui/Table';
import Badge from '../../components/ui/Badge';
import Pagination from '../../components/ui/Pagination';
import InlineAlert from '../../components/ui/InlineAlert';
import EmptyState from '../../components/ui/EmptyState';
import { usePaginatedList } from '../../hooks/usePaginatedList';
import OrderStatusBadge from '../../components/purchases/OrderStatusBadge';
import OrderPaymentStatusBadge from '../../components/purchases/OrderPaymentStatusBadge';
import { extractErrorMessage } from '../../utils/errorMessage';

const formatCurrency = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : value;
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const SupplierDetailPage = () => {
    const { id } = useParams();

    const [supplier, setSupplier] = useState(null);
    const [payableSummary, setPayableSummary] = useState(null);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState('');

    useEffect(() => {
        fetchData();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [id]);

    const fetchData = async () => {
        setLoading(true);
        setLoadError('');
        try {
            const [supplierData, summaryData] = await Promise.all([
                purchasesApi.suppliers.getById(id),
                purchasesApi.suppliers.getPayableSummary(id),
            ]);

            setSupplier(supplierData);
            setPayableSummary(summaryData);
        } catch (err) {
            setSupplier(null);
            setLoadError(extractErrorMessage(err, 'Failed to load supplier details.'));
        } finally {
            setLoading(false);
        }
    };

    const fetchOrdersPage = (params) => {
        if (!supplier?.code) {
            return Promise.resolve({ results: [], count: 0, total_pages: 1, current_page: 1, page_size: 25 });
        }
        return purchasesApi.orders.getAll({ ...params, supplier_code: supplier.code });
    };

    const { data: orders, meta, page, setPage, loading: ordersLoading, error: ordersError, refetch: refetchOrders } =
        usePaginatedList(fetchOrdersPage, {}, 25, [supplier?.code]);

    const columns = [
        { key: 'order_number', label: 'Order #', width: '120px' },
        {
            key: 'net_payable',
            label: 'Net Payable (PKR)',
            render: (value) => formatCurrency(value),
        },
        {
            key: 'payable_outstanding',
            label: 'Outstanding (PKR)',
            render: (value) => formatCurrency(value),
        },
        {
            key: 'payment_status',
            label: 'Payment Status',
            render: (value) => <OrderPaymentStatusBadge status={value} />
        },
        {
            key: 'status',
            label: 'Order Status',
            render: (value) => <OrderStatusBadge status={value} />
        },
        {
            key: 'confirmed_at',
            label: 'Confirmed',
            render: (value) => value ? new Date(value).toLocaleDateString() : 'N/A'
        },
        {
            key: 'id',
            label: 'Actions',
            width: '100px',
            render: (_, row) => (
                <Link
                    to={`/purchases/orders/${row.id}`}
                    className="text-primary-600 hover:text-primary-700 text-sm font-medium"
                >
                    View
                </Link>
            ),
        },
    ];

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    if (!supplier) {
        return (
            <div className="space-y-4">
                <BackLink to="/purchases/suppliers">Back to Suppliers</BackLink>
                {loadError ? (
                    <InlineAlert variant="error" message={loadError} onRetry={fetchData} />
                ) : (
                    <div className="text-center py-12">
                        <h2 className="text-2xl font-semibold text-neutral-900">Supplier Not Found</h2>
                    </div>
                )}
            </div>
        );
    }

    const activeOrders = orders.filter(o => o.status !== 'draft');
    const draftOrders = orders.filter(o => o.status === 'draft');
    const outstanding = parseFloat(payableSummary?.total_payable_outstanding || 0);

    return (
        <div className="space-y-6">
            <div>
                <BackLink to="/purchases/suppliers">Back to Suppliers</BackLink>
                <div className="flex items-center gap-3 mt-3">
                    <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-primary-600 to-accent-600 flex items-center justify-center shadow-lg shadow-primary-900/20 flex-shrink-0">
                        <Truck className="w-5 h-5 text-white" />
                    </div>
                    <div>
                        <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900">{supplier.name}</h1>
                        <p className="text-neutral-500 text-sm sm:text-base">Code: {supplier.code}</p>
                    </div>
                </div>
            </div>

            {/* Supplier Info */}
            <Card className="p-4 sm:p-6" hover={false}>
                <h3 className="font-semibold text-neutral-900 mb-3">Supplier Information</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div>
                        <p className="text-sm text-neutral-500">Name</p>
                        <p className="font-medium text-neutral-900">{supplier.name}</p>
                    </div>
                    <div>
                        <p className="text-sm text-neutral-500">Code</p>
                        <p className="font-medium text-neutral-900">{supplier.code}</p>
                    </div>
                    <div>
                        <p className="text-sm text-neutral-500">Created</p>
                        <p className="font-medium text-neutral-900">{new Date(supplier.created_at).toLocaleDateString()}</p>
                    </div>
                    <div>
                        <p className="text-sm text-neutral-500">Status</p>
                        <Badge variant={supplier.is_deleted ? 'error' : 'success'}>
                            {supplier.is_deleted ? 'Deleted' : 'Active'}
                        </Badge>
                    </div>
                </div>
            </Card>

            {/* Payable Summary */}
            {payableSummary && Object.keys(payableSummary).length > 0 && (
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
                    <Card className="p-4" hover={false}>
                        <div className="flex items-center gap-2 mb-1">
                            <FileText className="w-4 h-4 text-neutral-400" />
                            <p className="text-sm text-neutral-500">Total Net Payable</p>
                        </div>
                        <p className="text-xl font-bold text-neutral-900">
                            Rs. {formatCurrency(payableSummary.total_net_payable)}
                        </p>
                    </Card>
                    <Card className="p-4" hover={false}>
                        <div className="flex items-center gap-2 mb-1">
                            <CheckCircle2 className="w-4 h-4 text-success-500" />
                            <p className="text-sm text-neutral-500">Total Paid</p>
                        </div>
                        <p className="text-xl font-bold text-success-600">
                            Rs. {formatCurrency(payableSummary.total_paid)}
                        </p>
                    </Card>
                    <Card className="p-4" hover={false}>
                        <div className="flex items-center gap-2 mb-1">
                            <Wallet className="w-4 h-4 text-error-500" />
                            <p className="text-sm text-neutral-500">Outstanding</p>
                        </div>
                        <p className="text-xl font-bold text-error-600">
                            Rs. {formatCurrency(payableSummary.total_payable_outstanding)}
                        </p>
                    </Card>
                    <Card className="p-4" hover={false}>
                        <p className="text-sm text-neutral-500 mb-1.5">Payment Status</p>
                        <Badge variant={outstanding > 0 ? 'unpaid' : 'paid'}>
                            {outstanding > 0 ? 'Outstanding' : 'Settled'}
                        </Badge>
                    </Card>
                </div>
            )}

            {ordersError && (
                <InlineAlert variant="error" message={ordersError} onRetry={refetchOrders} />
            )}

            {/* Order History */}
            <Card className="p-4 sm:p-6" hover={false}>
                <h3 className="font-semibold text-neutral-900 mb-3">Order History</h3>
                {ordersLoading ? (
                    <div className="flex items-center justify-center py-8">
                        <LoadingSpinner size="md" />
                    </div>
                ) : activeOrders.length === 0 ? (
                    <EmptyState
                        title="No confirmed orders"
                        description="This supplier has no confirmed orders yet."
                    />
                ) : (
                    <Table
                        columns={columns}
                        data={activeOrders}
                    />
                )}
            </Card>

            {/* Draft Orders */}
            {draftOrders.length > 0 && (
                <Card className="p-4 sm:p-6" hover={false}>
                    <h3 className="font-semibold text-neutral-900 mb-3">Draft Orders</h3>
                    <Table
                        columns={columns}
                        data={draftOrders}
                    />
                </Card>
            )}

            {meta.totalPages > 1 && (
                <Pagination
                    currentPage={meta.currentPage}
                    totalPages={meta.totalPages}
                    onPageChange={setPage}
                />
            )}
        </div>
    );
};

export default SupplierDetailPage;
