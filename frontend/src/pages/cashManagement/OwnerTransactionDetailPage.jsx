import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { Trash2, ArrowUpCircle, ArrowDownCircle, Calendar, User, Clock, FileText } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { cashManagementApi } from '../../services/cashManagementApi';
import { extractErrorMessage } from '../../utils/errorMessage';
import BackLink from '../../components/ui/BackLink';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';
import Badge from '../../components/ui/Badge';
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

const OwnerTransactionDetailPage = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const [txn, setTxn] = useState(null);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState(null);
    const [notFound, setNotFound] = useState(false);
    const [deleteConfirm, setDeleteConfirm] = useState(false);
    const [deleteLoading, setDeleteLoading] = useState(false);

    const fetchTxn = useCallback(async () => {
        setLoading(true);
        setLoadError(null);
        setNotFound(false);
        try {
            const data = await cashManagementApi.ownerTransactions.getById(id);
            setTxn(data);
        } catch (error) {
            if (error?.response?.status === 404) {
                setNotFound(true);
            } else {
                setLoadError(extractErrorMessage(error, 'Failed to load owner transaction'));
            }
            setTxn(null);
        } finally {
            setLoading(false);
        }
    }, [id]);

    useEffect(() => {
        fetchTxn();
    }, [fetchTxn]);

    const handleDelete = async () => {
        setDeleteLoading(true);
        try {
            await cashManagementApi.ownerTransactions.delete(id);
            toast.success('Owner transaction deleted and cash in hand adjusted');
            navigate('/cash-management/owner-transactions');
        } catch (error) {
            toast.error(extractErrorMessage(error, 'Failed to delete owner transaction'));
            setDeleteConfirm(false);
        } finally {
            setDeleteLoading(false);
        }
    };

    if (!isAdmin) {
        return (
            <div className="text-center py-16">
                <h2 className="text-2xl font-semibold text-neutral-900">Access Denied</h2>
                <p className="text-neutral-500 mt-2">Only admins or superusers can view owner transactions.</p>
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
                <h2 className="text-2xl font-semibold text-neutral-900">Owner Transaction Not Found</h2>
                <BackLink to="/cash-management/owner-transactions" className="mt-4 inline-flex">Back to Owner Transactions</BackLink>
            </div>
        );
    }

    if (loadError || !txn) {
        return (
            <div className="space-y-4">
                <BackLink to="/cash-management/owner-transactions">Back to Owner Transactions</BackLink>
                <InlineAlert
                    variant="error"
                    title="Couldn't load this owner transaction"
                    message={loadError || 'Something went wrong'}
                    onRetry={fetchTxn}
                />
            </div>
        );
    }

    const isContribution = txn.transaction_type === 'contribution';
    const ImpactIcon = isContribution ? ArrowUpCircle : ArrowDownCircle;

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <BackLink to="/cash-management/owner-transactions">Back to Owner Transactions</BackLink>
                    <div className="flex items-center gap-3 mt-2">
                        <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900">Owner Transaction Details</h1>
                        {isContribution ? <Badge variant="success">Contribution</Badge> : <Badge variant="warning">Drawing</Badge>}
                    </div>
                    <p className={`mt-1 text-lg font-semibold ${isContribution ? 'text-success-600' : 'text-warning-700'}`}>
                        Rs. {fmt(txn.amount)}
                    </p>
                </div>
                <Button variant="danger" icon={Trash2} onClick={() => setDeleteConfirm(true)}>
                    Delete
                </Button>
            </div>

            <Card className="p-6">
                <h3 className="font-semibold text-neutral-900 mb-4">Transaction Information</h3>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-5">
                    <InfoField
                        label="Amount"
                        value={<span className={isContribution ? 'text-success-600' : 'text-warning-700'}>Rs. {fmt(txn.amount)}</span>}
                    />
                    <InfoField icon={Calendar} label="Date" value={new Date(txn.transaction_date).toLocaleDateString()} />
                    <InfoField icon={User} label="Recorded By" value={txn.created_by || 'N/A'} />
                    <InfoField icon={Clock} label="Created At" value={new Date(txn.created_at).toLocaleString()} />
                    {txn.note && (
                        <div className="col-span-full">
                            <InfoField icon={FileText} label="Note" value={txn.note} />
                        </div>
                    )}
                </div>
            </Card>

            {txn.allocations?.length > 0 && (
                <Card className="p-6">
                    <h3 className="font-semibold text-neutral-900 mb-4">Method Breakdown</h3>
                    <div className="space-y-2">
                        {txn.allocations.map((a) => (
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
                <h3 className="font-semibold text-neutral-900 mb-3">Cash Impact</h3>
                <div className={`flex items-start gap-3 p-4 rounded-xl border-l-4 ${isContribution ? 'bg-success-50 border-success-500' : 'bg-warning-50 border-warning-500'}`}>
                    <ImpactIcon className={`w-5 h-5 flex-shrink-0 mt-0.5 ${isContribution ? 'text-success-500' : 'text-warning-600'}`} />
                    <div>
                        <p className={isContribution ? 'text-success-700' : 'text-warning-700'}>
                            This {isContribution ? 'increased' : 'reduced'} cash in hand by <strong>Rs. {fmt(txn.amount)}</strong>
                        </p>
                        <p className={`text-sm mt-1 ${isContribution ? 'text-success-600' : 'text-warning-600'}`}>
                            Recorded on {new Date(txn.transaction_date).toLocaleDateString()}
                        </p>
                    </div>
                </div>
            </Card>

            <div className="flex gap-3 pt-4 border-t border-neutral-200">
                <Link to="/cash-management/owner-transactions">
                    <Button variant="secondary">Back to Owner Transactions</Button>
                </Link>
                <Button variant="danger" icon={Trash2} onClick={() => setDeleteConfirm(true)}>
                    Delete Transaction
                </Button>
            </div>

            <ConfirmDialog
                isOpen={deleteConfirm}
                onClose={() => setDeleteConfirm(false)}
                onConfirm={handleDelete}
                title="Delete Owner Transaction"
                message={`Are you sure you want to delete this Rs. ${fmt(txn.amount)} ${txn.transaction_type}? This will reverse its effect on cash in hand.`}
                loading={deleteLoading}
            />
        </div>
    );
};

export default OwnerTransactionDetailPage;
