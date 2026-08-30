import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
    Receipt, Trash2, FileText, User, CreditCard, Calendar, UserCircle, Clock,
    StickyNote, ArrowLeft, ExternalLink, Banknote, Smartphone, Landmark, Hash,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { billingApi } from '../../services/billingApi';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Badge from '../../components/ui/Badge';
import PaymentStatusBadge from '../../components/billing/PaymentStatusBadge';
import BackLink from '../../components/ui/BackLink';
import InlineAlert from '../../components/ui/InlineAlert';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import { useToast } from '../../context/ToastContext';
import { extractErrorMessage } from '../../utils/errorMessage';

const METHOD_META = {
    cash: { icon: Banknote, label: 'Cash', classes: 'bg-success-50 text-success-700' },
    jazzcash: { icon: Smartphone, label: 'JazzCash', classes: 'bg-warning-50 text-warning-700' },
    easypaisa: { icon: Smartphone, label: 'Easypaisa', classes: 'bg-info-50 text-info-700' },
    bank: { icon: Landmark, label: 'Bank Transfer', classes: 'bg-primary-50 text-primary-700' },
};

const MethodBadge = ({ method, display }) => {
    const meta = METHOD_META[method] || { icon: CreditCard, label: display || 'N/A', classes: 'bg-neutral-100 text-neutral-700' };
    const Icon = meta.icon;
    return (
        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${meta.classes}`}>
            <Icon className="w-3.5 h-3.5" />
            {display || meta.label}
        </span>
    );
};

// Prefer the real per-method split (`allocations`, from the new multi-account
// payment methods system) over the single derived `method`/`method_display`
// label — falls back gracefully if the API response doesn't carry it yet.
const MethodSplitDisplay = ({ payment }) => {
    if (Array.isArray(payment.allocations) && payment.allocations.length > 0) {
        return (
            <div className="flex flex-wrap gap-1.5">
                {payment.allocations.map((a) => (
                    <span
                        key={a.id}
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-primary-50 text-primary-700"
                    >
                        {a.payment_method_name}: {formatCurrency(a.amount)}
                    </span>
                ))}
            </div>
        );
    }
    return <MethodBadge method={payment.method} display={payment.method_display} />;
};

const formatCurrency = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : value;
    if (isNaN(num)) return 'PKR 0.00';
    return `PKR ${num.toLocaleString('en-PK', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

const InfoRow = ({ icon: Icon, label, children }) => (
    <div>
        <p className="flex items-center gap-1.5 text-xs font-medium text-neutral-500 uppercase tracking-wide mb-1">
            {Icon && <Icon className="w-3.5 h-3.5" />}
            {label}
        </p>
        <div className="font-medium text-neutral-800">{children}</div>
    </div>
);

const PaymentDetailPage = () => {
    const { paymentId } = useParams();
    const navigate = useNavigate();
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const [payment, setPayment] = useState(null);
    const [invoice, setInvoice] = useState(null);
    const [customer, setCustomer] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [notFound, setNotFound] = useState(false);

    const [confirmOpen, setConfirmOpen] = useState(false);
    const [deleting, setDeleting] = useState(false);

    const fetchPaymentDetails = useCallback(async () => {
        setLoading(true);
        setError(null);
        setNotFound(false);
        try {
            const foundPayment = await billingApi.payments.getById(paymentId);

            setPayment(foundPayment);

            if (foundPayment.invoice) {
                const invoiceData = await billingApi.invoices.getById(foundPayment.invoice);
                setInvoice(invoiceData);
                if (invoiceData.customer) {
                    setCustomer(invoiceData.customer);
                }
            }
        } catch (err) {
            if (err?.response?.status === 404) {
                setNotFound(true);
                setPayment(null);
                return;
            }
            setError(extractErrorMessage(err, 'Failed to load payment details.'));
            setPayment(null);
        } finally {
            setLoading(false);
        }
    }, [paymentId]);

    useEffect(() => {
        fetchPaymentDetails();
    }, [fetchPaymentDetails]);

    const handleDeletePayment = async () => {
        setDeleting(true);
        try {
            await billingApi.payments.delete(paymentId);
            toast.success('Payment deleted successfully.');
            navigate('/billing/payments');
        } catch (err) {
            toast.error(extractErrorMessage(err, 'Failed to delete payment.'));
            setDeleting(false);
            setConfirmOpen(false);
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    if (error) {
        return (
            <div className="space-y-4">
                <BackLink to="/billing/payments">Back to Payments</BackLink>
                <InlineAlert variant="error" message={error} onRetry={fetchPaymentDetails} />
            </div>
        );
    }

    if (notFound || !payment) {
        return (
            <div className="text-center py-12">
                <h2 className="text-2xl font-semibold text-neutral-900">Payment Not Found</h2>
                <p className="text-neutral-500 mt-1">The payment you're looking for doesn't exist.</p>
                <BackLink to="/billing/payments" className="mt-4">Back to Payments</BackLink>
            </div>
        );
    }

    return (
        <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
            className="space-y-6"
        >
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <BackLink to="/billing/payments">Back to Payments</BackLink>
                    <div className="flex items-center gap-3 mt-2">
                        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-600 to-accent-600 flex items-center justify-center shadow-lg shadow-primary-900/20 flex-shrink-0">
                            <Receipt className="w-5 h-5 text-white" />
                        </div>
                        <div>
                            <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900">Payment Details</h1>
                            <p className="text-neutral-500 flex items-center gap-1 text-sm">
                                <Hash className="w-3.5 h-3.5" />
                                {payment.reference_number}
                            </p>
                        </div>
                    </div>
                </div>
                {isAdmin && (
                    <Button
                        variant="danger"
                        onClick={() => setConfirmOpen(true)}
                        icon={Trash2}
                        className="min-h-[44px]"
                    >
                        Delete Payment
                    </Button>
                )}
            </div>

            {/* Payment Info */}
            <Card className="p-6">
                <h3 className="font-semibold text-neutral-900 mb-4 flex items-center gap-2">
                    <CreditCard className="w-4 h-4 text-primary-600" />
                    Payment Information
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-5">
                    <InfoRow icon={Hash} label="Reference Number">
                        {payment.reference_number}
                    </InfoRow>
                    <InfoRow label="Amount">
                        <span className="text-xl font-bold text-success-600">
                            {formatCurrency(payment.amount)}
                        </span>
                    </InfoRow>
                    <InfoRow label="Method">
                        <MethodSplitDisplay payment={payment} />
                    </InfoRow>
                    <InfoRow icon={Calendar} label="Payment Date">
                        {payment.payment_date ? new Date(payment.payment_date).toLocaleDateString() : 'N/A'}
                    </InfoRow>
                    <InfoRow icon={UserCircle} label="Created By">
                        {payment.created_by || 'N/A'}
                    </InfoRow>
                    <InfoRow icon={Clock} label="Created At">
                        {payment.created_at ? new Date(payment.created_at).toLocaleString() : 'N/A'}
                    </InfoRow>
                    {payment.note && (
                        <div className="col-span-full">
                            <InfoRow icon={StickyNote} label="Note">
                                {payment.note}
                            </InfoRow>
                        </div>
                    )}
                </div>
            </Card>

            {/* Related Invoice */}
            {invoice && (
                <Card className="p-6">
                    <h3 className="font-semibold text-neutral-900 mb-4 flex items-center gap-2">
                        <FileText className="w-4 h-4 text-primary-600" />
                        Related Invoice
                    </h3>
                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-5">
                        <InfoRow label="Bill Number">
                            <Link
                                to={`/billing/invoices/${invoice.id}`}
                                className="text-primary-600 hover:text-primary-700 hover:underline inline-flex items-center gap-1"
                            >
                                {invoice.bill_number}
                            </Link>
                        </InfoRow>
                        <InfoRow icon={User} label="Customer">
                            {customer?.name || 'N/A'}
                        </InfoRow>
                        <InfoRow label="Invoice Status">
                            <Badge variant={
                                invoice.status === 'confirmed' ? 'confirmed' :
                                    invoice.status === 'draft' ? 'draft' :
                                        'default'
                            }>
                                {invoice.status || 'N/A'}
                            </Badge>
                        </InfoRow>
                        <InfoRow label="Payment Status">
                            <PaymentStatusBadge status={invoice.payment_status} />
                        </InfoRow>
                        <InfoRow label="Grand Total">
                            {formatCurrency(invoice.grand_total)}
                        </InfoRow>
                        <InfoRow label="Credit Outstanding">
                            <span className={invoice.credit_outstanding && parseFloat(invoice.credit_outstanding) > 0 ? 'text-error-600 font-semibold' : 'text-neutral-800'}>
                                {formatCurrency(invoice.credit_outstanding)}
                            </span>
                        </InfoRow>
                        <InfoRow icon={Calendar} label="Confirmed At">
                            {invoice.confirmed_at ? new Date(invoice.confirmed_at).toLocaleDateString() : 'N/A'}
                        </InfoRow>
                    </div>
                    <div className="mt-5">
                        <Link to={`/billing/invoices/${invoice.id}`}>
                            <Button variant="secondary" size="sm" icon={ExternalLink}>
                                View Full Invoice
                            </Button>
                        </Link>
                    </div>
                </Card>
            )}

            {/* Actions */}
            <div className="flex flex-wrap gap-3 pt-4 border-t border-neutral-200">
                <Link to="/billing/payments">
                    <Button variant="secondary" icon={ArrowLeft}>
                        Back to Payments
                    </Button>
                </Link>
                {invoice && (
                    <Link to={`/billing/invoices/${invoice.id}`}>
                        <Button variant="secondary" icon={ExternalLink}>
                            View Invoice
                        </Button>
                    </Link>
                )}
            </div>

            <ConfirmDialog
                isOpen={confirmOpen}
                onClose={() => setConfirmOpen(false)}
                onConfirm={handleDeletePayment}
                title="Delete Payment"
                message={`Are you sure you want to delete payment ${payment.reference_number}? This action cannot be undone.`}
                confirmText="Delete Payment"
                cancelText="Cancel"
                variant="danger"
                loading={deleting}
            />
        </motion.div>
    );
};

export default PaymentDetailPage;
