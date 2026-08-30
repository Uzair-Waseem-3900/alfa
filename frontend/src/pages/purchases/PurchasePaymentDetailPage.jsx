import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { purchasesApi } from '../../services/purchasesApi';
import { extractErrorMessage } from '../../utils/errorMessage';
import Button from '../../components/ui/Button';
import BackLink from '../../components/ui/BackLink';
import Card from '../../components/ui/Card';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Badge from '../../components/ui/Badge';
import InlineAlert from '../../components/ui/InlineAlert';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import OrderStatusBadge from '../../components/purchases/OrderStatusBadge';
import OrderPaymentStatusBadge from '../../components/purchases/OrderPaymentStatusBadge';
import { Trash2, ArrowLeft, Wallet, ExternalLink } from 'lucide-react';

const PurchasePaymentDetailPage = () => {
    const { reference } = useParams();
    const navigate = useNavigate();
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const [payment, setPayment] = useState(null);
    const [order, setOrder] = useState(null);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState('');
    const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
    const [deleteLoading, setDeleteLoading] = useState(false);

    useEffect(() => {
        fetchPaymentDetails();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [reference]);

    const fetchPaymentDetails = async () => {
        setLoading(true);
        setLoadError('');
        try {
            const paymentsRes = await purchasesApi.payments.getAll({ reference, page_size: 500 });
            const payments = paymentsRes?.results ?? paymentsRes ?? [];
            const foundPayment = payments?.[0];

            if (!foundPayment) {
                setPayment(null);
                return;
            }

            setPayment(foundPayment);

            if (foundPayment.order) {
                const orderData = await purchasesApi.orders.getById(foundPayment.order);
                setOrder(orderData);
            }
        } catch (error) {
            console.error('Failed to fetch payment details:', error);
            setPayment(null);
            setLoadError(extractErrorMessage(error, 'Failed to load payment details.'));
        } finally {
            setLoading(false);
        }
    };

    const handleDeletePayment = async () => {
        setDeleteLoading(true);
        try {
            await purchasesApi.payments.delete(payment.id);
            toast.success('Payment deleted.');
            navigate('/purchases/payments');
        } catch (error) {
            console.error('Failed to delete payment:', error);
            toast.error(extractErrorMessage(error, 'Failed to delete payment.'));
        } finally {
            setDeleteLoading(false);
            setShowDeleteConfirm(false);
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    if (loadError) {
        return (
            <div className="space-y-6">
                <BackLink to="/purchases/payments">Back to Payments</BackLink>
                <InlineAlert variant="error" message={loadError} onRetry={fetchPaymentDetails} />
            </div>
        );
    }

    if (!payment) {
        return (
            <div className="text-center py-12">
                <h2 className="text-2xl font-semibold text-neutral-900">Payment Not Found</h2>
                <p className="text-neutral-500 mt-1">The payment you're looking for doesn't exist.</p>
                <BackLink to="/purchases/payments" className="mt-4">Back to Payments</BackLink>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <BackLink to="/purchases/payments">Back to Payments</BackLink>
                    <div className="flex items-center gap-3 mt-2">
                        <div className="w-10 h-10 rounded-xl bg-primary-50 text-primary-600 flex items-center justify-center flex-shrink-0">
                            <Wallet className="w-5 h-5" />
                        </div>
                        <div>
                            <h1 className="text-3xl font-bold text-neutral-900">Payment Details</h1>
                            <p className="text-neutral-500">{payment.reference_number}</p>
                        </div>
                    </div>
                </div>
                {isAdmin && (
                    <Button variant="danger" icon={Trash2} onClick={() => setShowDeleteConfirm(true)}>
                        Delete Payment
                    </Button>
                )}
            </div>

            {/* Payment Info */}
            <Card className="p-6" hover={false}>
                <h3 className="font-semibold text-neutral-900 mb-4">Payment Information</h3>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-5">
                    <div>
                        <p className="text-sm text-neutral-500">Reference Number</p>
                        <p className="font-medium">{payment.reference_number}</p>
                    </div>
                    <div>
                        <p className="text-sm text-neutral-500">Amount (PKR)</p>
                        <p className="text-xl font-bold text-success-600 tabular-nums">
                            {typeof payment.amount === 'string'
                                ? parseFloat(payment.amount).toFixed(2)
                                : '0.00'}
                        </p>
                    </div>
                    <div>
                        <p className="text-sm text-neutral-500">Method</p>
                        {Array.isArray(payment.allocations) && payment.allocations.length > 0 ? (
                            <div className="flex flex-wrap gap-1.5">
                                {payment.allocations.map((a) => (
                                    <Badge key={a.id}>{a.payment_method_name}: {parseFloat(a.amount).toFixed(2)}</Badge>
                                ))}
                            </div>
                        ) : (
                            <Badge>{payment.method_display || payment.method || 'N/A'}</Badge>
                        )}
                    </div>
                    <div>
                        <p className="text-sm text-neutral-500">Payment Date</p>
                        <p className="font-medium">{new Date(payment.payment_date).toLocaleDateString()}</p>
                    </div>
                    <div>
                        <p className="text-sm text-neutral-500">Created By</p>
                        <p className="font-medium">{payment.created_by || 'N/A'}</p>
                    </div>
                    <div>
                        <p className="text-sm text-neutral-500">Created At</p>
                        <p className="font-medium">{new Date(payment.created_at).toLocaleString()}</p>
                    </div>
                    {payment.note && (
                        <div className="col-span-full">
                            <p className="text-sm text-neutral-500">Note</p>
                            <p className="font-medium">{payment.note}</p>
                        </div>
                    )}
                </div>
            </Card>

            {/* Related Order */}
            {order && (
                <Card className="p-6" hover={false}>
                    <h3 className="font-semibold text-neutral-900 mb-4">Related Order</h3>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-5">
                        <div>
                            <p className="text-sm text-neutral-500">Order Number</p>
                            <Link
                                to={`/purchases/orders/${order.id}`}
                                className="font-medium text-primary-600 hover:text-primary-700 hover:underline"
                            >
                                {order.order_number}
                            </Link>
                        </div>
                        <div>
                            <p className="text-sm text-neutral-500">Supplier</p>
                            <p className="font-medium">{order.supplier?.name || 'N/A'}</p>
                        </div>
                        <div>
                            <p className="text-sm text-neutral-500">Order Status</p>
                            <OrderStatusBadge status={order.status} />
                        </div>
                        <div>
                            <p className="text-sm text-neutral-500">Payment Status</p>
                            <OrderPaymentStatusBadge status={order.payment_status} />
                        </div>
                        <div>
                            <p className="text-sm text-neutral-500">Net Payable</p>
                            <p className="font-medium tabular-nums">
                                {typeof order.net_payable === 'string'
                                    ? parseFloat(order.net_payable).toFixed(2)
                                    : '0.00'}
                            </p>
                        </div>
                        <div>
                            <p className="text-sm text-neutral-500">Payable Outstanding</p>
                            <p className="font-medium text-error-600 tabular-nums">
                                {typeof order.payable_outstanding === 'string'
                                    ? parseFloat(order.payable_outstanding).toFixed(2)
                                    : '0.00'}
                            </p>
                        </div>
                        <div>
                            <p className="text-sm text-neutral-500">Confirmed At</p>
                            <p className="font-medium">
                                {order.confirmed_at ? new Date(order.confirmed_at).toLocaleDateString() : 'N/A'}
                            </p>
                        </div>
                    </div>
                    <div className="mt-4">
                        <Link to={`/purchases/orders/${order.id}`}>
                            <Button variant="secondary" size="sm" icon={ExternalLink}>
                                View Full Order
                            </Button>
                        </Link>
                    </div>
                </Card>
            )}

            {/* Actions */}
            <div className="flex flex-wrap gap-3 pt-4 border-t border-neutral-200">
                <Link to="/purchases/payments">
                    <Button variant="secondary" icon={ArrowLeft}>
                        Back to Payments
                    </Button>
                </Link>
                {order && (
                    <Link to={`/purchases/orders/${order.id}`}>
                        <Button variant="secondary" icon={ExternalLink}>
                            View Order
                        </Button>
                    </Link>
                )}
            </div>

            <ConfirmDialog
                isOpen={showDeleteConfirm}
                onClose={() => setShowDeleteConfirm(false)}
                onConfirm={handleDeletePayment}
                title="Delete Payment"
                message="Are you sure you want to delete this payment? This action cannot be undone."
                confirmText="Delete"
                loading={deleteLoading}
            />
        </div>
    );
};

export default PurchasePaymentDetailPage;
