import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { Trash2, Calendar, User, Clock, StickyNote, HandCoins, TrendingDown, Repeat } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { profitsApi } from '../../services/profitsApi';
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

const formatMonthLabel = (period) => {
    if (!period) return '';
    const [year, m] = period.split('-');
    const date = new Date(Number(year), Number(m) - 1, 1);
    return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
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

const InvestorPayoutDetailPage = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const [payout, setPayout] = useState(null);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState(null);
    const [notFound, setNotFound] = useState(false);
    const [deleteConfirm, setDeleteConfirm] = useState(false);
    const [deleteLoading, setDeleteLoading] = useState(false);

    const fetchPayout = useCallback(async () => {
        setLoading(true);
        setLoadError(null);
        setNotFound(false);
        try {
            const data = await profitsApi.payouts.getById(id);
            setPayout(data);
        } catch (error) {
            if (error?.response?.status === 404) {
                setNotFound(true);
            } else {
                setLoadError(extractErrorMessage(error, 'Failed to load payout'));
            }
            setPayout(null);
        } finally {
            setLoading(false);
        }
    }, [id]);

    useEffect(() => {
        fetchPayout();
    }, [fetchPayout]);

    const handleDelete = async () => {
        setDeleteLoading(true);
        try {
            await profitsApi.payouts.delete(id);
            toast.success('Payout reversed and cash in hand restored');
            navigate('/profits/payouts');
        } catch (error) {
            toast.error(extractErrorMessage(error, 'Failed to delete payout'));
            setDeleteConfirm(false);
        } finally {
            setDeleteLoading(false);
        }
    };

    if (!isAdmin) {
        return (
            <div className="text-center py-16">
                <h2 className="text-2xl font-semibold text-neutral-900">Access Denied</h2>
                <p className="text-neutral-500 mt-2">Only admins or superusers can view investor payments.</p>
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
                <h2 className="text-2xl font-semibold text-neutral-900">Payout Not Found</h2>
                <BackLink to="/profits/payouts" className="mt-4 inline-flex">Back to Investor Payments</BackLink>
            </div>
        );
    }

    if (loadError || !payout) {
        return (
            <div className="space-y-4">
                <BackLink to="/profits/payouts">Back to Investor Payments</BackLink>
                <InlineAlert
                    variant="error"
                    title="Couldn't load this payout"
                    message={loadError || 'Something went wrong'}
                    onRetry={fetchPayout}
                />
            </div>
        );
    }

    const isReinvest = payout.action_type === 'reinvest';

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <BackLink to="/profits/payouts">Back to Investor Payments</BackLink>
                    <div className="flex items-center gap-3 mt-2">
                        <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900">Investor Payout Details</h1>
                        {isReinvest ? <Badge variant="info">Reinvest</Badge> : <Badge variant="success">Payout</Badge>}
                    </div>
                    <p className="text-neutral-500 text-sm sm:text-base mt-1">
                        {payout.investor_name} — {formatMonthLabel(payout.period)}
                    </p>
                    <p className="mt-1 text-lg font-semibold text-neutral-900">
                        Rs. {fmt(payout.amount)}
                    </p>
                </div>
                <Button variant="danger" icon={Trash2} onClick={() => setDeleteConfirm(true)}>
                    Delete
                </Button>
            </div>

            <Card className="p-6">
                <h3 className="font-semibold text-neutral-900 mb-4 flex items-center gap-2">
                    <HandCoins className="w-4 h-4 text-neutral-400" />
                    Payout Information
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-5">
                    <InfoField label="Amount" value={<span>Rs. {fmt(payout.amount)}</span>} />
                    <InfoField label="Investor" value={payout.investor_name} />
                    <InfoField label="For Month" value={formatMonthLabel(payout.period)} />
                    <InfoField icon={Calendar} label="Date" value={new Date(payout.payout_date).toLocaleDateString()} />
                    <InfoField icon={User} label="Recorded By" value={payout.created_by || 'N/A'} />
                    <InfoField icon={Clock} label="Created At" value={new Date(payout.created_at).toLocaleString()} />
                    {payout.note && (
                        <div className="col-span-full">
                            <InfoField icon={StickyNote} label="Note" value={payout.note} />
                        </div>
                    )}
                </div>
            </Card>

            {payout.allocations?.length > 0 && (
                <Card className="p-6">
                    <h3 className="font-semibold text-neutral-900 mb-4">Method Breakdown</h3>
                    <div className="space-y-2">
                        {payout.allocations.map((a) => (
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
                    {isReinvest ? <Repeat className="w-4 h-4 text-neutral-400" /> : <TrendingDown className="w-4 h-4 text-neutral-400" />}
                    Cash Impact
                </h3>
                {isReinvest ? (
                    <div className="flex items-start gap-3 p-4 rounded-xl border-l-4 bg-info-50 border-info-500">
                        <Repeat className="w-5 h-5 flex-shrink-0 mt-0.5 text-info-500" />
                        <div>
                            <p className="text-info-700">
                                Rs. {fmt(payout.amount)} left cash in hand as this settlement, then came straight back in as new investor capital — net effect on cash in hand is Rs. 0.
                            </p>
                            {payout.linked_investor_transaction ? (
                                <Link
                                    to={`/cash-management/investor-transactions/${payout.linked_investor_transaction}`}
                                    className="text-sm mt-2 inline-flex items-center gap-1 text-info-700 hover:text-info-800 font-medium underline"
                                >
                                    View the resulting investment transaction
                                </Link>
                            ) : (
                                <p className="text-sm mt-1 text-info-600">
                                    Recorded on {new Date(payout.payout_date).toLocaleDateString()}
                                </p>
                            )}
                        </div>
                    </div>
                ) : (
                    <div className="flex items-start gap-3 p-4 rounded-xl border-l-4 bg-warning-50 border-warning-500">
                        <TrendingDown className="w-5 h-5 flex-shrink-0 mt-0.5 text-warning-600" />
                        <div>
                            <p className="text-warning-700">
                                This reduced cash in hand by <strong>Rs. {fmt(payout.amount)}</strong>
                            </p>
                            <p className="text-sm mt-1 text-warning-600">
                                Recorded on {new Date(payout.payout_date).toLocaleDateString()}
                            </p>
                        </div>
                    </div>
                )}
            </Card>

            <div className="flex gap-3 pt-4 border-t border-neutral-200">
                <Link to="/profits/payouts">
                    <Button variant="secondary">Back to Investor Payments</Button>
                </Link>
                <Button variant="danger" icon={Trash2} onClick={() => setDeleteConfirm(true)}>
                    Delete Payout
                </Button>
            </div>

            <ConfirmDialog
                isOpen={deleteConfirm}
                onClose={() => setDeleteConfirm(false)}
                onConfirm={handleDelete}
                title="Delete Payout"
                message={`Are you sure you want to delete this Rs. ${fmt(payout.amount)} ${payout.action_type}? This will reverse its effect on cash in hand${isReinvest ? ' and the linked investment' : ''}.`}
                loading={deleteLoading}
            />
        </div>
    );
};

export default InvestorPayoutDetailPage;
