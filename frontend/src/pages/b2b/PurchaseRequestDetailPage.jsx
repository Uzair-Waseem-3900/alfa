import { useState } from 'react';
import { Link, Navigate, useParams } from 'react-router-dom';
import { RefreshCw, XCircle } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { usePurchaseRequestDetail, usePurchaseRequestActions } from '../../hooks/useB2B';
import { extractErrorMessage } from '../../utils/errorMessage';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';
import Badge from '../../components/ui/Badge';
import BackLink from '../../components/ui/BackLink';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import InlineAlert from '../../components/ui/InlineAlert';
import { REQUEST_STATUS_BADGE } from './PurchaseRequestsPage';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const PurchaseRequestDetailPage = () => {
    const { id } = useParams();
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const { data: request, loading, error: loadError, refetch } = usePurchaseRequestDetail(id);
    const { cancel, sync, mutating } = usePurchaseRequestActions();
    const [confirmCancel, setConfirmCancel] = useState(false);

    if (!isAdmin) {
        return <Navigate to="/dashboard" replace />;
    }

    const handleCancel = async () => {
        try {
            await cancel(request.id);
            toast.success('Request cancelled');
            setConfirmCancel(false);
            await refetch({ silent: true });
        } catch (error) {
            toast.error(extractErrorMessage(error, 'Failed to cancel the request'));
            setConfirmCancel(false);
            await refetch({ silent: true });   // the partner may already have decided — show its decision
        }
    };

    const handleCheck = async () => {
        try {
            await sync();
            await refetch({ silent: true });
        } catch (error) {
            toast.error(extractErrorMessage(error, 'Failed to check for updates'));
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    if (!request) {
        return (
            <div className="space-y-4">
                {loadError && <InlineAlert variant="error" message={loadError} onRetry={refetch} />}
                <BackLink to="/b2b/purchase-requests">Back to Purchase Requests</BackLink>
            </div>
        );
    }

    const badge = REQUEST_STATUS_BADGE[request.status] || { variant: 'default', label: request.status };
    const decided = request.status === 'accepted';

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                <div>
                    <BackLink to="/b2b/purchase-requests">Back to Purchase Requests</BackLink>
                    <div className="flex items-center gap-3 flex-wrap mt-1">
                        <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900">{request.provider_name}</h1>
                        <Badge variant={badge.variant}>{badge.label}</Badge>
                        {!request.delivered && request.status === 'pending' && <Badge variant="warning">Waiting to send</Badge>}
                    </div>
                    <p className="text-sm text-neutral-500 mt-1">
                        Created {new Date(request.created_at).toLocaleString()}
                        {request.decided_at && ` · Decided ${new Date(request.decided_at).toLocaleString()}`}
                    </p>
                    {request.note && <p className="text-sm text-neutral-600 mt-2">Note: {request.note}</p>}
                    {request.order_number && (
                        <p className="text-sm mt-2">
                            Purchase order:{' '}
                            <Link to={`/purchases/orders/${request.order}`} className="font-medium text-primary-600 hover:underline">
                                {request.order_number}
                            </Link>
                        </p>
                    )}
                </div>

                <div className="flex flex-wrap gap-2">
                    {(request.status === 'pending' || (decided && !request.order)) && (
                        <Button variant="secondary" icon={RefreshCw} onClick={handleCheck} loading={mutating}>
                            Check for Updates
                        </Button>
                    )}
                    {request.status === 'pending' && (
                        <Button variant="danger" icon={XCircle} onClick={() => setConfirmCancel(true)} disabled={mutating}>
                            Cancel Request
                        </Button>
                    )}
                </div>
            </div>

            {request.status === 'denied' && (
                <InlineAlert variant="info" message="The partner did not accept this request. Nothing was ordered." />
            )}
            {decided && !request.order && (
                <InlineAlert
                    variant="warning"
                    title="Accepted — the purchase order isn't created yet"
                    message={request.import_error || 'It will be created automatically in a moment.'}
                    onRetry={handleCheck}
                    retryLabel="Try Again"
                />
            )}

            <Card className="p-0 overflow-hidden" hover={false}>
                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead>
                            <tr className="border-b border-neutral-200">
                                {['Product', 'Requested', 'Accepted', 'Price (PKR)', 'Discount', 'GST', 'WHT', 'Shelves'].map((label) => (
                                    <th key={label} className="px-4 py-3 text-left text-xs font-medium text-neutral-500 uppercase tracking-wider">{label}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-neutral-100">
                            {request.items.map((item) => (
                                <tr key={item.id}>
                                    <td className="px-4 py-3 text-sm">
                                        <span className="font-medium text-neutral-900">{item.product_name}</span>{' '}
                                        <span className="text-neutral-400">({item.product_code})</span>
                                    </td>
                                    <td className="px-4 py-3 text-sm">{item.requested_quantity}</td>
                                    <td className="px-4 py-3 text-sm font-medium">{decided ? (item.accepted_quantity ?? 0) : '—'}</td>
                                    <td className="px-4 py-3 text-sm">{item.unit_price != null ? `Rs. ${fmt(item.unit_price)}` : '—'}</td>
                                    <td className="px-4 py-3 text-sm">{fmt(item.discount)}</td>
                                    <td className="px-4 py-3 text-sm">{fmt(item.gst)}%</td>
                                    <td className="px-4 py-3 text-sm">{fmt(item.wht)}%</td>
                                    <td className="px-4 py-3 text-sm text-neutral-600">
                                        {item.shelves.map((s) => `${s.shelf_name}: ${s.quantity}`).join(', ') || '—'}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </Card>

            <ConfirmDialog
                isOpen={confirmCancel}
                onClose={() => setConfirmCancel(false)}
                onConfirm={handleCancel}
                title="Cancel Request"
                message={`Cancel this request to ${request.provider_name}? It only works if they haven't accepted it yet.`}
                confirmText="Cancel Request"
                loading={mutating}
            />
        </div>
    );
};

export default PurchaseRequestDetailPage;
