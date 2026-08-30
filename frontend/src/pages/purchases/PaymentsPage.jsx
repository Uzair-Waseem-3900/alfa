import { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { purchasesApi } from '../../services/purchasesApi';
import { extractErrorMessage } from '../../utils/errorMessage';
import { todayLocalDate } from '../../utils/helpers';
import Table from '../../components/ui/Table';
import Button from '../../components/ui/Button';
import BackLink from '../../components/ui/BackLink';
import Modal from '../../components/ui/Modal';
import Input from '../../components/ui/Input';
import SearchBar from '../../components/ui/SearchBar';
import MethodSplitPicker, { isSplitBalanced } from '../../components/paymentMethods/MethodSplitPicker';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Badge from '../../components/ui/Badge';
import Card from '../../components/ui/Card';
import Pagination from '../../components/ui/Pagination';
import InlineAlert from '../../components/ui/InlineAlert';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import EmptyState from '../../components/ui/EmptyState';
import { usePaginatedList } from '../../hooks/usePaginatedList';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { Plus, Eye, Trash2, Wallet, ArrowDownCircle, ArrowUpCircle, ScrollText } from 'lucide-react';

const PaymentsPage = () => {
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';
    const { orderId } = useParams();
    const navigate = useNavigate();

    const [showCreateModal, setShowCreateModal] = useState(false);
    const [paymentSummary, setPaymentSummary] = useState(null);
    const [orderDetails, setOrderDetails] = useState(null);
    const [summaryError, setSummaryError] = useState('');
    const [formData, setFormData] = useState({
        amount: '',
        payment_date: todayLocalDate(),
        note: '',
    });
    const [methodAllocations, setMethodAllocations] = useState([]);
    const [formLoading, setFormLoading] = useState(false);
    const [formError, setFormError] = useState('');
    const [deleteTarget, setDeleteTarget] = useState(null);
    const [deleteLoading, setDeleteLoading] = useState(false);

    const fetchPaymentsPage = (params) => {
        if (!orderId || orderId === 'undefined') {
            return Promise.resolve({ results: [], count: 0, total_pages: 1, current_page: 1, page_size: 25 });
        }
        return purchasesApi.payments.getByOrder(orderId, params);
    };

    const {
        data: payments, meta, page, setPage, loading, initialLoading, error: listError,
        filters, setFilters, refetch: fetchPayments,
    } = usePaginatedList(fetchPaymentsPage, {}, 25, [orderId]);

    useEffect(() => {
        if (orderId && orderId !== 'undefined') {
            loadSummaryAndOrder();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [orderId]);

    const loadSummaryAndOrder = async () => {
        if (!orderId || orderId === 'undefined') return;
        setSummaryError('');
        try {
            const [summary, order] = await Promise.all([
                purchasesApi.orders.getPaymentSummary(orderId),
                purchasesApi.orders.getById(orderId),
            ]);
            setPaymentSummary(summary);
            setOrderDetails(order);
        } catch (error) {
            console.error('Failed to fetch payment summary/order:', error);
            setSummaryError(extractErrorMessage(error, 'Failed to load order payment summary.'));
        }
    };

    const handleCreatePayment = async (e) => {
        e.preventDefault();
        setFormLoading(true);
        setFormError('');
        try {
            const paymentData = {
                order: parseInt(orderId),
                amount: parseFloat(formData.amount),
                method_allocations: methodAllocations,
                payment_date: formData.payment_date,
                note: formData.note || '',
            };

            await purchasesApi.payments.create(orderId, paymentData);
            setShowCreateModal(false);
            resetForm();
            fetchPayments();
            loadSummaryAndOrder();
            toast.success('Payment recorded successfully.');
        } catch (error) {
            console.error('Failed to create payment:', error);
            setFormError(extractErrorMessage(error, 'Failed to record payment.'));
        } finally {
            setFormLoading(false);
        }
    };

    const handleDeletePayment = async () => {
        if (!deleteTarget) return;
        setDeleteLoading(true);
        try {
            await purchasesApi.payments.delete(deleteTarget);
            fetchPayments();
            loadSummaryAndOrder();
            toast.success('Payment deleted.');
            setDeleteTarget(null);
        } catch (error) {
            console.error('Failed to delete payment:', error);
            toast.error(extractErrorMessage(error, 'Failed to delete payment.'));
        } finally {
            setDeleteLoading(false);
        }
    };

    const resetForm = () => {
        setFormData({
            amount: '',
            payment_date: todayLocalDate(),
            note: '',
        });
        setMethodAllocations([]);
        setFormError('');
    };

    const columns = [
        { key: 'reference_number', label: 'Reference', width: '140px' },
        {
            key: 'amount',
            label: 'Amount (PKR)',
            render: (value) => {
                const num = typeof value === 'string' ? parseFloat(value) : value;
                return <span className="font-medium tabular-nums">{isNaN(num) ? '0.00' : num.toFixed(2)}</span>;
            }
        },
        {
            key: 'method_display',
            label: 'Method',
            render: (value, row) => (
                Array.isArray(row.allocations) && row.allocations.length > 0 ? (
                    <div className="flex flex-wrap gap-1">
                        {row.allocations.map((a) => (
                            <Badge key={a.id}>{a.payment_method_name}: {parseFloat(a.amount).toFixed(2)}</Badge>
                        ))}
                    </div>
                ) : <Badge>{value || 'N/A'}</Badge>
            )
        },
        { key: 'payment_date', label: 'Date', render: (value) => value ? new Date(value).toLocaleDateString() : 'N/A' },
        { key: 'note', label: 'Note', render: (value) => value || <span className="text-neutral-400">&mdash;</span> },
        {
            key: 'actions',
            label: 'Actions',
            width: '120px',
            render: (_, row) => (
                <div className="flex items-center gap-2">
                    <Link
                        to={`/purchases/payments/ref/${row.reference_number}`}
                        className="inline-flex items-center gap-1 text-primary-600 hover:text-primary-700 text-sm font-medium"
                    >
                        <Eye className="w-4 h-4" /> View
                    </Link>
                    {isAdmin && (
                        <button
                            onClick={() => setDeleteTarget(row.id)}
                            className="inline-flex items-center gap-1 text-error-600 hover:text-error-700 text-sm font-medium min-h-[44px] sm:min-h-0"
                            aria-label="Delete payment"
                        >
                            <Trash2 className="w-4 h-4" />
                        </button>
                    )}
                </div>
            ),
        },
    ];

    // Full-page spinner only before the first fetch completes — after that,
    // the shell (header, summary, filters) stays mounted and only the table
    // area shows a lightweight loading affordance on refetch.
    if (initialLoading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    if (!orderId || orderId === 'undefined') {
        return (
            <div className="text-center py-12">
                <h2 className="text-2xl font-semibold text-neutral-900">Invalid Order</h2>
                <p className="text-neutral-500 mt-2">Please go back to the orders list.</p>
                <BackLink to="/purchases/orders" className="mt-4">Back to Orders</BackLink>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <h1 className="text-3xl font-bold text-neutral-900">Order Payments</h1>
                    <p className="text-neutral-500 mt-1">
                        Manage payments for Order #{orderDetails?.order_number || orderId}
                    </p>
                    <div className="flex flex-wrap gap-2 mt-3">
                        <BackLink to="/purchases/orders">Back to Orders</BackLink>
                        <BackLink to="/purchases/payments" direction="right">View All Payments</BackLink>
                    </div>
                </div>
                {isAdmin && (
                    <Button
                        onClick={() => {
                            resetForm();
                            setShowCreateModal(true);
                        }}
                        icon={Plus}
                    >
                        Record Payment
                    </Button>
                )}
            </div>

            {summaryError && (
                <InlineAlert variant="error" message={summaryError} onRetry={loadSummaryAndOrder} />
            )}

            {paymentSummary && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <Card className="p-4" hover={false}>
                        <div className="flex items-center gap-2 text-neutral-500 mb-1">
                            <ScrollText className="w-4 h-4" />
                            <p className="text-sm">Net Payable</p>
                        </div>
                        <p className="text-xl font-bold text-neutral-900 tabular-nums">
                            {typeof paymentSummary.net_payable === 'string'
                                ? parseFloat(paymentSummary.net_payable).toFixed(2)
                                : '0.00'}
                        </p>
                    </Card>
                    <Card className="p-4" hover={false}>
                        <div className="flex items-center gap-2 text-neutral-500 mb-1">
                            <ArrowDownCircle className="w-4 h-4" />
                            <p className="text-sm">Total Paid</p>
                        </div>
                        <p className="text-xl font-bold text-success-600 tabular-nums">
                            {typeof paymentSummary.total_paid === 'string'
                                ? parseFloat(paymentSummary.total_paid).toFixed(2)
                                : '0.00'}
                        </p>
                    </Card>
                    <Card className="p-4" hover={false}>
                        <div className="flex items-center gap-2 text-neutral-500 mb-1">
                            <ArrowUpCircle className="w-4 h-4" />
                            <p className="text-sm">Outstanding</p>
                        </div>
                        <p className="text-xl font-bold text-error-600 tabular-nums">
                            {typeof paymentSummary.payable_outstanding === 'string'
                                ? parseFloat(paymentSummary.payable_outstanding).toFixed(2)
                                : '0.00'}
                        </p>
                    </Card>
                    <Card className="p-4" hover={false}>
                        <div className="flex items-center gap-2 text-neutral-500 mb-1">
                            <Wallet className="w-4 h-4" />
                            <p className="text-sm">Payment Status</p>
                        </div>
                        <Badge variant={paymentSummary.payment_status === 'paid' ? 'paid' :
                            paymentSummary.payment_status === 'partial' ? 'partial' : 'unpaid'}>
                            {paymentSummary.payment_status_display || paymentSummary.payment_status || 'N/A'}
                        </Badge>
                    </Card>
                </div>
            )}

            <div className="flex gap-4">
                <SearchBar
                    onSearch={(value) => setFilters({ ...filters, reference: value })}
                    placeholder="Search payments by reference number..."
                    className="flex-1"
                />
            </div>

            {listError && (
                <InlineAlert variant="error" message={listError} onRetry={fetchPayments} />
            )}

            <div className={`relative transition-opacity ${loading ? 'opacity-60' : 'opacity-100'}`}>
                {loading && (
                    <div className="absolute right-2 top-2 z-10">
                        <LoadingSpinner size="sm" />
                    </div>
                )}
                {payments.length === 0 && !loading ? (
                    <EmptyState
                        title="No payments found"
                        description="Try adjusting your search, or record a new payment for this order."
                    />
                ) : (
                    <Table columns={columns} data={payments} />
                )}
            </div>

            {meta.totalPages > 1 && (
                <Pagination
                    currentPage={meta.currentPage}
                    totalPages={meta.totalPages}
                    onPageChange={setPage}
                />
            )}

            <Modal
                isOpen={showCreateModal}
                onClose={() => {
                    setShowCreateModal(false);
                    resetForm();
                }}
                title="Record Payment"
            >
                <form onSubmit={handleCreatePayment} className="space-y-4">
                    <Input
                        label="Amount (PKR)"
                        type="number"
                        step="0.01"
                        min="0.01"
                        value={formData.amount}
                        onChange={(e) => setFormData({ ...formData, amount: e.target.value })}
                        placeholder="Enter amount"
                        required
                    />

                    <div>
                        <p className="text-sm font-medium text-neutral-700 mb-2">Payment Method</p>
                        <MethodSplitPicker
                            totalAmount={parseFloat(formData.amount) || 0}
                            value={methodAllocations}
                            onChange={setMethodAllocations}
                        />
                    </div>

                    <Input
                        label="Payment Date"
                        type="date"
                        value={formData.payment_date}
                        onChange={(e) => setFormData({ ...formData, payment_date: e.target.value })}
                        required
                    />

                    <Input
                        label="Note"
                        value={formData.note}
                        onChange={(e) => setFormData({ ...formData, note: e.target.value })}
                        placeholder="Payment note (optional)"
                    />

                    {formError && <InlineAlert variant="error" message={formError} />}

                    <div className="flex justify-end gap-3 pt-4">
                        <Button
                            type="button"
                            variant="secondary"
                            onClick={() => {
                                setShowCreateModal(false);
                                resetForm();
                            }}
                        >
                            Cancel
                        </Button>
                        <Button
                            type="submit"
                            loading={formLoading}
                            icon={Wallet}
                            disabled={!isSplitBalanced(parseFloat(formData.amount) || 0, methodAllocations)}
                        >
                            Record Payment
                        </Button>
                    </div>
                </form>
            </Modal>

            <ConfirmDialog
                isOpen={!!deleteTarget}
                onClose={() => setDeleteTarget(null)}
                onConfirm={handleDeletePayment}
                title="Delete Payment"
                message="Are you sure you want to delete this payment? This action cannot be undone."
                confirmText="Delete"
                loading={deleteLoading}
            />
        </div>
    );
};

export default PaymentsPage;
