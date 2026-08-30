import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { Calendar, User, Clock, Receipt, TrendingDown, TrendingUp, StickyNote, Package } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { assetsApi } from '../../services/assetsApi';
import { extractErrorMessage } from '../../utils/errorMessage';
import BackLink from '../../components/ui/BackLink';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';
import Badge from '../../components/ui/Badge';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
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

const AssetPaymentDetailPage = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const { user } = useAuth();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const [payment, setPayment] = useState(null);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState(null);
    const [notFound, setNotFound] = useState(false);

    const fetchPayment = useCallback(async () => {
        setLoading(true);
        setLoadError(null);
        setNotFound(false);
        try {
            const data = await assetsApi.payments.getById(id);
            setPayment(data);
        } catch (error) {
            if (error?.response?.status === 404) {
                setNotFound(true);
            } else {
                setLoadError(extractErrorMessage(error, 'Failed to load asset payment'));
            }
            setPayment(null);
        } finally {
            setLoading(false);
        }
    }, [id]);

    useEffect(() => {
        fetchPayment();
    }, [fetchPayment]);

    if (!isAdmin) {
        return (
            <div className="text-center py-16">
                <h2 className="text-2xl font-semibold text-neutral-900">Access Denied</h2>
                <p className="text-neutral-500 mt-2">Only admins or superusers can view asset payments.</p>
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
                <BackLink to="/assets/payments" className="mt-4 inline-flex">Back to Asset Payments</BackLink>
            </div>
        );
    }

    if (loadError || !payment) {
        return (
            <div className="space-y-4">
                <BackLink to="/assets/payments">Back to Asset Payments</BackLink>
                <InlineAlert
                    variant="error"
                    title="Couldn't load this payment"
                    message={loadError || 'Something went wrong'}
                    onRetry={fetchPayment}
                />
            </div>
        );
    }

    const isSale = payment.payment_type === 'sale';

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <BackLink to="/assets/payments">Back to Asset Payments</BackLink>
                    <div className="flex items-center gap-3 mt-2">
                        <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900">Asset Payment Details</h1>
                        {isSale ? <Badge variant="info">Sale</Badge> : <Badge variant="success">Purchase</Badge>}
                    </div>
                    <p className="text-neutral-500 text-sm sm:text-base mt-1">
                        <Link to={`/assets/items/${payment.asset}`} className="text-primary-600 hover:text-primary-700">
                            {payment.asset_name}
                        </Link>
                        {' — '}{payment.category_name}
                    </p>
                    <p className={`mt-1 text-lg font-semibold ${isSale ? 'text-success-600' : 'text-error-600'}`}>
                        Rs. {fmt(payment.amount)}
                    </p>
                </div>
            </div>

            <Card className="p-6">
                <h3 className="font-semibold text-neutral-900 mb-4 flex items-center gap-2">
                    <Receipt className="w-4 h-4 text-neutral-400" />
                    Payment Information
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-5">
                    <InfoField label="Amount" value={<span className={isSale ? 'text-success-600' : 'text-error-600'}>Rs. {fmt(payment.amount)}</span>} />
                    <InfoField icon={Package} label="Asset" value={payment.asset_name} />
                    <InfoField label="Category" value={payment.category_name} />
                    <InfoField icon={Calendar} label="Date" value={new Date(payment.date).toLocaleDateString()} />
                    <InfoField icon={User} label="Recorded By" value={payment.created_by || 'N/A'} />
                    <InfoField icon={Clock} label="Created At" value={new Date(payment.created_at).toLocaleString()} />
                    {isSale && payment.gain_loss != null && (
                        <InfoField
                            label="Gain / Loss"
                            value={
                                <span className={parseFloat(payment.gain_loss) >= 0 ? 'text-success-600' : 'text-error-600'}>
                                    {parseFloat(payment.gain_loss) >= 0 ? '+' : ''}Rs. {fmt(payment.gain_loss)}
                                </span>
                            }
                        />
                    )}
                    {isSale && payment.reason && (
                        <div className="col-span-full">
                            <InfoField icon={StickyNote} label="Reason" value={payment.reason} />
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
                    {isSale ? <TrendingUp className="w-4 h-4 text-neutral-400" /> : <TrendingDown className="w-4 h-4 text-neutral-400" />}
                    Cash Impact
                </h3>
                <div className={`flex items-start gap-3 p-4 rounded-xl border-l-4 ${isSale ? 'bg-success-50 border-success-500' : 'bg-warning-50 border-warning-500'}`}>
                    {isSale ? (
                        <TrendingUp className="w-5 h-5 flex-shrink-0 mt-0.5 text-success-500" />
                    ) : (
                        <TrendingDown className="w-5 h-5 flex-shrink-0 mt-0.5 text-warning-600" />
                    )}
                    <div>
                        <p className={isSale ? 'text-success-700' : 'text-warning-700'}>
                            This {isSale ? 'increased' : 'reduced'} cash in hand by <strong>Rs. {fmt(payment.amount)}</strong>
                        </p>
                        <p className={`text-sm mt-1 ${isSale ? 'text-success-600' : 'text-warning-600'}`}>
                            Recorded on {new Date(payment.date).toLocaleDateString()}
                        </p>
                    </div>
                </div>
            </Card>

            <div className="flex gap-3 pt-4 border-t border-neutral-200">
                <Link to="/assets/payments">
                    <Button variant="secondary">Back to Asset Payments</Button>
                </Link>
                <Link to={`/assets/items/${payment.asset}`}>
                    <Button variant="secondary">View Asset</Button>
                </Link>
            </div>
        </div>
    );
};

export default AssetPaymentDetailPage;
