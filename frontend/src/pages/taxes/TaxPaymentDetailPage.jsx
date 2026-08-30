import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { AlertTriangle, Trash2, Receipt, Calendar, User, Clock, StickyNote, Wallet } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { taxesApi } from '../../services/taxesApi';
import { extractErrorMessage } from '../../utils/errorMessage';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import BackLink from '../../components/ui/BackLink';
import InlineAlert from '../../components/ui/InlineAlert';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const DetailRow = ({ icon: Icon, label, children }) => (
    <div>
        <p className="text-xs font-medium text-neutral-500 uppercase tracking-wide flex items-center gap-1.5">
            {Icon && <Icon className="w-3.5 h-3.5" />}
            {label}
        </p>
        <div className="font-medium text-neutral-900 mt-1">{children}</div>
    </div>
);

const TaxPaymentDetailPage = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const [payment, setPayment] = useState(null);
    const [loading, setLoading] = useState(true);
    const [notFound, setNotFound] = useState(false);
    const [error, setError] = useState('');
    const [deleteConfirm, setDeleteConfirm] = useState(false);
    const [deleteLoading, setDeleteLoading] = useState(false);

    const fetchPayment = useCallback(async () => {
        setLoading(true);
        setError('');
        setNotFound(false);
        try {
            const data = await taxesApi.payments.getById(id);
            setPayment(data);
        } catch (err) {
            if (err?.response?.status === 404) {
                setNotFound(true);
            } else {
                setError(extractErrorMessage(err, 'Failed to load tax payment'));
            }
            setPayment(null);
        } finally {
            setLoading(false);
        }
    }, [id]);

    useEffect(() => {
        fetchPayment();
    }, [fetchPayment]);

    const handleDelete = async () => {
        setDeleteLoading(true);
        try {
            await taxesApi.payments.delete(id);
            toast.success('Tax payment deleted and cash in hand restored');
            navigate('/taxes/payments');
        } catch (err) {
            toast.error(extractErrorMessage(err, 'Failed to delete tax payment'));
            setDeleteLoading(false);
            setDeleteConfirm(false);
        }
    };

    if (!isAdmin) {
        return (
            <div className="flex flex-col items-center justify-center text-center py-20">
                <div className="w-14 h-14 rounded-full bg-error-50 flex items-center justify-center mb-4">
                    <AlertTriangle className="w-7 h-7 text-error-500" />
                </div>
                <h2 className="text-2xl font-semibold text-neutral-900">Access Denied</h2>
                <p className="text-neutral-500 mt-2 max-w-sm">Only admins or superusers can view tax payments.</p>
            </div>
        );
    }

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
                <BackLink to="/taxes/payments">Back to Tax Payments</BackLink>
                <InlineAlert variant="error" message={error} onRetry={fetchPayment} />
            </div>
        );
    }

    if (notFound || !payment) {
        return (
            <div className="text-center py-12">
                <h2 className="text-2xl font-semibold text-neutral-900">Tax Payment Not Found</h2>
                <p className="text-neutral-500 mt-1">The tax payment you're looking for doesn't exist.</p>
                <BackLink to="/taxes/payments" className="mt-4">Back to Tax Payments</BackLink>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <BackLink to="/taxes/payments">Back to Tax Payments</BackLink>
                    <h1 className="text-3xl font-bold text-neutral-900 mt-2 flex items-center gap-2.5">
                        <Receipt className="w-7 h-7 text-primary-600" />
                        Tax Payment Details
                    </h1>
                    <p className="text-neutral-500 mt-1">Rs. {fmt(payment.amount)} paid to FBR</p>
                </div>
                <Button variant="danger" onClick={() => setDeleteConfirm(true)} icon={Trash2}>
                    Delete
                </Button>
            </div>

            {/* Payment Information */}
            <Card className="p-6">
                <h3 className="font-semibold text-neutral-900 mb-4">Payment Information</h3>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-5">
                    <DetailRow icon={Wallet} label="Amount">
                        <span className="text-xl font-bold text-error-600">Rs. {fmt(payment.amount)}</span>
                    </DetailRow>
                    <DetailRow icon={Calendar} label="Payment Date">
                        {new Date(payment.payment_date).toLocaleDateString()}
                    </DetailRow>
                    <DetailRow icon={User} label="Recorded By">
                        {payment.created_by || 'N/A'}
                    </DetailRow>
                    <DetailRow icon={Clock} label="Created At">
                        {new Date(payment.created_at).toLocaleString()}
                    </DetailRow>
                    {payment.updated_by && (
                        <DetailRow icon={User} label="Updated By">
                            {payment.updated_by}
                        </DetailRow>
                    )}
                    {payment.updated_at && payment.updated_at !== payment.created_at && (
                        <DetailRow icon={Clock} label="Updated At">
                            {new Date(payment.updated_at).toLocaleString()}
                        </DetailRow>
                    )}
                    {payment.note && (
                        <div className="col-span-full">
                            <DetailRow icon={StickyNote} label="Note">
                                {payment.note}
                            </DetailRow>
                        </div>
                    )}
                </div>
            </Card>

            {/* Cash Impact */}
            <Card className="p-6">
                <h3 className="font-semibold text-neutral-900 mb-3">Cash Impact</h3>
                <div className="p-4 bg-amber-50 rounded-lg flex items-start gap-3">
                    <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                    <div>
                        <p className="text-amber-700">
                            This payment reduced cash in hand by <strong>Rs. {fmt(payment.amount)}</strong>
                        </p>
                        <p className="text-sm text-amber-600 mt-1">
                            Paid on {new Date(payment.payment_date).toLocaleDateString()}
                        </p>
                    </div>
                </div>
            </Card>

            {/* Actions */}
            <div className="flex gap-3 pt-4 border-t border-neutral-200">
                <BackLink to="/taxes/payments">Back to Tax Payments</BackLink>
                <Button variant="danger" onClick={() => setDeleteConfirm(true)} icon={Trash2}>
                    Delete Tax Payment
                </Button>
            </div>

            <ConfirmDialog
                isOpen={deleteConfirm}
                onClose={() => setDeleteConfirm(false)}
                onConfirm={handleDelete}
                title="Delete Tax Payment"
                message={`Are you sure you want to delete this Rs. ${fmt(payment.amount)} tax payment? This will restore the amount to cash in hand.`}
                loading={deleteLoading}
            />
        </div>
    );
};

export default TaxPaymentDetailPage;
