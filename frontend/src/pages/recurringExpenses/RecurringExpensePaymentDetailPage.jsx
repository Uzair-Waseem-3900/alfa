import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { Trash2, Calendar, User, Clock, StickyNote, Receipt, TrendingDown } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { recurringExpensesApi } from '../../services/recurringExpensesApi';
import { extractErrorMessage } from '../../utils/errorMessage';
import BackLink from '../../components/ui/BackLink';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import InlineAlert from '../../components/ui/InlineAlert';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const InfoField = ({ icon: Icon, label, value }) => (
    <div>
        <p className="text-xs font-medium text-neutral-500 flex items-center gap-1.5 mb-1">
            {Icon && <Icon className="w-3.5 h-3.5" />}
            {label}
        </p>
        <p className="font-medium text-neutral-900">{value}</p>
    </div>
);

const RecurringExpensePaymentDetailPage = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const [payment, setPayment] = useState(null);
    const [assignment, setAssignment] = useState(null);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState(null);
    const [notFound, setNotFound] = useState(false);
    const [deleteConfirm, setDeleteConfirm] = useState(false);
    const [deleteLoading, setDeleteLoading] = useState(false);

    const backHref = payment?.assignment
        ? `/recurring-expenses/assignments/${payment.assignment}`
        : '/recurring-expenses/assignments';

    const fetchPayment = useCallback(async () => {
        setLoading(true);
        setLoadError(null);
        setNotFound(false);
        try {
            const data = await recurringExpensesApi.payments.getById(id);
            setPayment(data);
            if (data?.assignment) {
                try {
                    const a = await recurringExpensesApi.assignments.getById(data.assignment);
                    setAssignment(a);
                } catch {
                    setAssignment(null);
                }
            }
        } catch (error) {
            if (error?.response?.status === 404) {
                setNotFound(true);
            } else {
                setLoadError(extractErrorMessage(error, 'Failed to load payment'));
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
            await recurringExpensesApi.payments.delete(id);
            toast.success('Payment deleted and cash in hand restored');
            navigate(backHref);
        } catch (error) {
            toast.error(extractErrorMessage(error, 'Failed to delete payment'));
            setDeleteConfirm(false);
        } finally {
            setDeleteLoading(false);
        }
    };

    if (!isAdmin) {
        return (
            <div className="text-center py-16">
                <h2 className="text-2xl font-semibold text-neutral-900">Access Denied</h2>
                <p className="text-neutral-500 mt-2">Only admins or superusers can view this.</p>
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

    if (notFound) {
        return (
            <div className="text-center py-16">
                <h2 className="text-2xl font-semibold text-neutral-900">Payment Not Found</h2>
                <BackLink to="/recurring-expenses/assignments" className="mt-4 inline-flex">Back to Assignments</BackLink>
            </div>
        );
    }

    if (loadError || !payment) {
        return (
            <div className="space-y-4">
                <BackLink to="/recurring-expenses/assignments">Back to Assignments</BackLink>
                <InlineAlert
                    variant="error"
                    title="Couldn't load this payment"
                    message={loadError || 'Something went wrong'}
                    onRetry={fetchPayment}
                />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <BackLink to={backHref}>Back to Assignment</BackLink>
                    <div className="flex items-center gap-3 mt-2">
                        <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900">Payment Details</h1>
                    </div>
                    {assignment && (
                        <p className="text-neutral-500 text-sm sm:text-base mt-1">
                            {assignment.name_snapshot} — {assignment.period}
                        </p>
                    )}
                    <p className="mt-1 text-lg font-semibold text-success-600">
                        Rs. {fmt(payment.amount)}
                    </p>
                </div>
                <Button variant="danger" icon={Trash2} onClick={() => setDeleteConfirm(true)}>
                    Delete
                </Button>
            </div>

            <Card className="p-6">
                <h3 className="font-semibold text-neutral-900 mb-4 flex items-center gap-2">
                    <Receipt className="w-4 h-4 text-neutral-400" />
                    Payment Information
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-5">
                    <InfoField label="Amount" value={<span className="text-success-600">Rs. {fmt(payment.amount)}</span>} />
                    <InfoField icon={Calendar} label="Date" value={new Date(payment.payment_date).toLocaleDateString()} />
                    <InfoField icon={User} label="Recorded By" value={payment.created_by || 'N/A'} />
                    <InfoField icon={Clock} label="Created At" value={new Date(payment.created_at).toLocaleString()} />
                    {payment.note && (
                        <div className="col-span-full">
                            <InfoField icon={StickyNote} label="Note" value={payment.note} />
                        </div>
                    )}
                </div>
            </Card>

            {payment.allocations?.length > 0 && (
                <Card className="p-6">
                    <h3 className="font-semibold text-neutral-900 mb-4">Method Breakdown</h3>
                    <div className="space-y-2">
                        {payment.allocations.map((a) => (
                            <div key={a.id} className="flex items-center justify-between text-sm bg-neutral-50 rounded-lg px-3 py-2.5">
                                <span className="text-neutral-700">{a.payment_method_name}</span>
                                <span className={`font-medium ${a.direction === 'inflow' ? 'text-success-600' : 'text-error-600'}`}>
                                    {a.direction === 'inflow' ? '+' : '−'} Rs. {fmt(a.amount)}
                                </span>
                            </div>
                        ))}
                    </div>
                </Card>
            )}

            <Card className="p-6">
                <h3 className="font-semibold text-neutral-900 mb-3 flex items-center gap-2">
                    <TrendingDown className="w-4 h-4 text-neutral-400" />
                    Cash Impact
                </h3>
                <div className="flex items-start gap-3 p-4 bg-warning-50 rounded-xl border border-warning-100">
                    <TrendingDown className="w-5 h-5 text-warning-500 flex-shrink-0 mt-0.5" />
                    <div>
                        <p className="text-warning-700">
                            This payment reduced cash in hand by <strong>Rs. {fmt(payment.amount)}</strong>
                        </p>
                        <p className="text-sm text-warning-600 mt-1">
                            Recorded on {new Date(payment.payment_date).toLocaleDateString()}
                        </p>
                    </div>
                </div>
            </Card>

            <div className="flex gap-3 pt-4 border-t border-neutral-200">
                <Link to={backHref}>
                    <Button variant="secondary">Back to Assignment</Button>
                </Link>
                <Button variant="danger" icon={Trash2} onClick={() => setDeleteConfirm(true)}>
                    Delete Payment
                </Button>
            </div>

            <ConfirmDialog
                isOpen={deleteConfirm}
                onClose={() => setDeleteConfirm(false)}
                onConfirm={handleDelete}
                title="Delete Payment"
                message={`Are you sure you want to delete this Rs. ${fmt(payment.amount)} payment? This will restore the amount to cash in hand.`}
                loading={deleteLoading}
            />
        </div>
    );
};

export default RecurringExpensePaymentDetailPage;
