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
import Modal from '../../components/ui/Modal';
import InlineAlert from '../../components/ui/InlineAlert';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import OrderStatusBadge from '../../components/purchases/OrderStatusBadge';
import OrderPaymentStatusBadge from '../../components/purchases/OrderPaymentStatusBadge';
import ShelfAllocationEditor from '../../components/shared/ShelfAllocationEditor';
import ReturnForm from '../../components/purchases/ReturnForm';
import { Pencil, XCircle, CheckCircle2, ArrowLeft, ExternalLink, Save } from 'lucide-react';

const PurchaseReturnDetailPage = () => {
    const { returnId } = useParams();
    const navigate = useNavigate();
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const [returnItem, setReturnItem] = useState(null);
    const [order, setOrder] = useState(null);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState('');
    const [candidateShelves, setCandidateShelves] = useState({});
    const [allocationDrafts, setAllocationDrafts] = useState({});
    const [allocationError, setAllocationError] = useState('');
    // Bulk auto-allocate/save cover every item at once — one click each,
    // instead of per-item buttons. Editors stay fully editable either way.
    const [bulkAutoAllocating, setBulkAutoAllocating] = useState(false);
    const [bulkSaving, setBulkSaving] = useState(false);
    const [acceptError, setAcceptError] = useState('');
    const [showEditForm, setShowEditForm] = useState(false);
    const [formLoading, setFormLoading] = useState(false);
    const [showAcceptConfirm, setShowAcceptConfirm] = useState(false);
    const [acceptLoading, setAcceptLoading] = useState(false);
    const [showCancelConfirm, setShowCancelConfirm] = useState(false);
    const [cancelLoading, setCancelLoading] = useState(false);

    useEffect(() => {
        fetchReturnDetails();
    }, [returnId]);

    // The read serializer exposes `product` (id) directly on a return item,
    // resolved server-side from the item's own purchase_item FK — no need
    // to cross-reference the order's items by product_code, which was
    // ambiguous whenever an order had two lines for the same product code.
    useEffect(() => {
        if (!returnItem?.items) return;

        setAllocationDrafts((prev) => {
            const next = { ...prev };
            returnItem.items.forEach((item) => {
                next[item.id] = (item.shelf_allocations || []).map((a) => ({
                    shelf_id: a.shelf.id,
                    quantity: a.quantity,
                }));
            });
            return next;
        });

        if (returnItem.status !== 'pending') return;

        returnItem.items.forEach((item) => {
            if (!item.product) return;
            purchasesApi.shelves.getCandidates(item.product)
                .then((res) => {
                    const list = Array.isArray(res) ? res : (res?.results ?? []);
                    setCandidateShelves((prev) => ({ ...prev, [item.id]: list }));
                })
                .catch((error) => console.error('Failed to fetch candidate shelves:', error));
        });
    }, [returnItem]);

    const getItemProductId = (item) => item.product;

    // One click auto-allocates every item at once — fills only each item's
    // remaining gap, never touches rows already present.
    const handleAutoAllocateAll = async () => {
        if (!returnItem?.items?.length) return;
        setBulkAutoAllocating(true);
        setAllocationError('');
        let failedCount = 0;
        await Promise.all(returnItem.items.map(async (item) => {
            const productId = getItemProductId(item);
            if (!productId) return;
            const current = allocationDrafts[item.id] || [];
            const allocatedTotal = current.reduce((sum, a) => sum + (parseInt(a.quantity, 10) || 0), 0);
            const remaining = item.quantity - allocatedTotal;
            if (remaining <= 0) return;
            try {
                const excludeShelfIds = current.map((a) => a.shelf_id).filter(Boolean);
                const data = await purchasesApi.shelves.autoAllocate(productId, remaining, excludeShelfIds);
                const newRows = (data?.allocations || []).map((a) => ({
                    shelf_id: a.shelf_id, quantity: a.quantity, shelf_name: a.shelf_name || '',
                }));
                if (newRows.length > 0) {
                    setAllocationDrafts((prev) => ({ ...prev, [item.id]: [...(prev[item.id] || []), ...newRows] }));
                }
            } catch (error) {
                console.error(`Failed to auto-allocate item ${item.id}:`, error);
                failedCount += 1;
            }
        }));
        setBulkAutoAllocating(false);
        if (failedCount > 0) {
            toast.error(`Auto-allocate failed for ${failedCount} item(s) — you can still allocate them manually.`);
        } else {
            toast.success('Auto-allocated shelves for all items.');
        }
    };

    // One click saves every item's current allocation rows at once —
    // whether they came from auto-allocate, manual edits, or both.
    const handleSaveAllocationsAll = async () => {
        if (!returnItem?.items?.length) return;
        setBulkSaving(true);
        setAllocationError('');
        let failedCount = 0;
        // Sequential, not Promise.all — each save is a real DB write, and
        // firing them concurrently against SQLite (single-writer) causes
        // "database is locked" 500s. One at a time is the correct fix
        // regardless of backend, not just a SQLite workaround.
        for (const item of returnItem.items) {
            try {
                const allocations = (allocationDrafts[item.id] || [])
                    .filter((a) => a.shelf_id && a.quantity)
                    .map((a) => ({ shelf_id: parseInt(a.shelf_id, 10), quantity: parseInt(a.quantity, 10) }));
                await purchasesApi.purchaseReturnItems.setShelfAllocations(item.id, allocations);
            } catch (error) {
                console.error(`Failed to save shelf allocations for item ${item.id}:`, error);
                failedCount += 1;
            }
        }
        setBulkSaving(false);
        if (failedCount > 0) {
            setAllocationError(`Failed to save allocations for ${failedCount} item(s).`);
            toast.error(`Failed to save allocations for ${failedCount} item(s).`);
        } else {
            toast.success('All shelf allocations saved.');
        }
        await fetchReturnDetails();
    };

    const fetchReturnDetails = async () => {
        setLoading(true);
        setLoadError('');
        try {
            const returnsRes = await purchasesApi.returns.getAll({ page_size: 500 });
            const allReturns = returnsRes?.results ?? returnsRes ?? [];
            const foundReturn = allReturns.find(r => r.id === parseInt(returnId));

            if (foundReturn) {
                setReturnItem(foundReturn);

                try {
                    const orderData = await purchasesApi.orders.getById(foundReturn.order);
                    setOrder(orderData);
                } catch (orderError) {
                    console.error('Failed to fetch related order:', orderError);
                    setOrder(null);
                }
            } else {
                setReturnItem(null);
                setOrder(null);
            }
        } catch (error) {
            console.error('Failed to fetch return details:', error);
            setReturnItem(null);
            setOrder(null);
            setLoadError(extractErrorMessage(error, 'Failed to load return details.'));
        } finally {
            setLoading(false);
        }
    };

    const handleAcceptReturn = async () => {
        setAcceptLoading(true);
        setAcceptError('');
        try {
            await purchasesApi.returns.accept(returnId);
            await fetchReturnDetails();
            toast.success('Return accepted successfully.');
            setShowAcceptConfirm(false);
        } catch (error) {
            console.error('Failed to accept return:', error);
            setAcceptError(extractErrorMessage(error, 'Failed to accept return.'));
            setShowAcceptConfirm(false);
        } finally {
            setAcceptLoading(false);
        }
    };

    const handleUpdateReturn = async (data) => {
        setFormLoading(true);
        try {
            await purchasesApi.returns.update(returnId, data);
            setShowEditForm(false);
            await fetchReturnDetails();
            toast.success('Return updated successfully.');
        } catch (error) {
            console.error('Failed to update return:', error);
            toast.error(extractErrorMessage(error, 'Failed to update return.'));
        } finally {
            setFormLoading(false);
        }
    };

    const handleCancelReturn = async () => {
        setCancelLoading(true);
        try {
            await purchasesApi.returns.cancel(returnId);
            toast.success('Return cancelled.');
            navigate('/purchases/returns');
        } catch (error) {
            console.error('Failed to cancel return:', error);
            toast.error(extractErrorMessage(error, 'Failed to cancel return.'));
            setCancelLoading(false);
            setShowCancelConfirm(false);
        }
    };

    // unit_price/total_amount on a return item are only snapshotted from the
    // original purchase item when the return is ACCEPTED (by design) — a
    // pending return legitimately has 0.00 there. Preview the same total the
    // accept step will compute (gross + gst - wht, matching
    // purchases.utils.calculate_total_price) from the original order item's
    // unit_price, so a pending return doesn't display a misleading 0.00.
    const previewItemTotal = (item) => {
        if (!order?.items) return 0;
        const orderItem = order.items.find((oi) => oi.product_code === item.product_code);
        if (!orderItem) return 0;
        const unitPrice = parseFloat(orderItem.unit_price) || 0;
        const gross = unitPrice * item.quantity;
        const gstAmount = gross * ((parseFloat(item.gst) || 0) / 100);
        const whtAmount = gross * ((parseFloat(item.wht) || 0) / 100);
        return gross + gstAmount - whtAmount;
    };

    const displayItemTotal = (item) => (
        returnItem.status === 'accepted'
            ? (parseFloat(item.total_amount) || 0)
            : previewItemTotal(item)
    );

    const displayReturnTotal = () => (
        returnItem.status === 'accepted'
            ? (parseFloat(returnItem.total_return_amount) || 0)
            : (returnItem.items || []).reduce((sum, item) => sum + previewItemTotal(item), 0)
    );

    // Resolves each return item's current line back to {purchase_item_id,
    // quantity} for the edit form — same product_code -> order.items match
    // already used above to fetch candidate shelves.
    const getInitialEditItems = () => {
        if (!returnItem?.items || !order?.items) return [];
        return returnItem.items.map((item) => {
            const orderItem = order.items.find((oi) => oi.product_code === item.product_code);
            return {
                purchase_item_id: orderItem?.id || '',
                quantity: item.quantity,
            };
        });
    };

    const getStatusBadge = (status) => {
        const variants = {
            pending: 'pending',
            accepted: 'accepted',
        };
        return <Badge variant={variants[status] || 'default'}>{status}</Badge>;
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
                <BackLink to="/purchases/returns">Back to Returns</BackLink>
                <InlineAlert variant="error" message={loadError} onRetry={fetchReturnDetails} />
            </div>
        );
    }

    if (!returnItem) {
        return (
            <div className="text-center py-12">
                <h2 className="text-2xl font-semibold text-neutral-900">Return Not Found</h2>
                <p className="text-neutral-500 mt-1">The return you're looking for doesn't exist.</p>
                <BackLink to="/purchases/returns" className="mt-4">Back to Returns</BackLink>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <BackLink to="/purchases/returns">Back to Returns</BackLink>
                    <h1 className="text-3xl font-bold text-neutral-900 mt-2">Return Details</h1>
                    <div className="flex items-center gap-3 mt-1">
                        <p className="text-neutral-500">{returnItem.reference_number}</p>
                        {getStatusBadge(returnItem.status)}
                    </div>
                </div>
                <div className="flex flex-wrap gap-2">
                    {returnItem.status === 'pending' && isAdmin && (
                        <>
                            <Button variant="secondary" icon={Pencil} onClick={() => setShowEditForm(true)}>
                                Edit
                            </Button>
                            <Button variant="danger" icon={XCircle} onClick={() => setShowCancelConfirm(true)}>
                                Cancel Return
                            </Button>
                            <Button variant="success" icon={CheckCircle2} onClick={() => setShowAcceptConfirm(true)}>
                                Accept Return
                            </Button>
                        </>
                    )}
                    <Link to="/purchases/returns">
                        <Button variant="secondary" icon={ArrowLeft}>
                            Back
                        </Button>
                    </Link>
                </div>
            </div>

            {acceptError && (
                <InlineAlert variant="error" message={acceptError} />
            )}

            {/* Return Information */}
            <Card className="p-6">
                <h3 className="font-semibold text-neutral-900 mb-3">Return Information</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div>
                        <p className="text-sm text-neutral-500">Return Number</p>
                        <p className="font-medium">{returnItem.reference_number}</p>
                    </div>
                    <div>
                        <p className="text-sm text-neutral-500">Status</p>
                        {getStatusBadge(returnItem.status)}
                    </div>
                    <div>
                        <p className="text-sm text-neutral-500">Total Return Amount (PKR)</p>
                        <p className="font-medium text-primary-600">
                            {displayReturnTotal().toFixed(2)}
                        </p>
                    </div>
                    <div>
                        <p className="text-sm text-neutral-500">Created</p>
                        <p className="font-medium">{new Date(returnItem.created_at).toLocaleString()}</p>
                    </div>
                    {returnItem.total_return_gross && parseFloat(returnItem.total_return_gross) > 0 && (
                        <div>
                            <p className="text-sm text-neutral-500">Gross Amount (PKR)</p>
                            <p className="font-medium">{parseFloat(returnItem.total_return_gross).toFixed(2)}</p>
                        </div>
                    )}
                    {returnItem.total_return_gst && parseFloat(returnItem.total_return_gst) > 0 && (
                        <div>
                            <p className="text-sm text-neutral-500">GST Amount (PKR)</p>
                            <p className="font-medium">{parseFloat(returnItem.total_return_gst).toFixed(2)}</p>
                        </div>
                    )}
                    {returnItem.total_return_wht && parseFloat(returnItem.total_return_wht) > 0 && (
                        <div>
                            <p className="text-sm text-neutral-500">WHT Amount (PKR)</p>
                            <p className="font-medium">{parseFloat(returnItem.total_return_wht).toFixed(2)}</p>
                        </div>
                    )}
                    {returnItem.accepted_at && (
                        <div>
                            <p className="text-sm text-neutral-500">Accepted</p>
                            <p className="font-medium">{new Date(returnItem.accepted_at).toLocaleString()}</p>
                        </div>
                    )}
                    {returnItem.accepted_by && (
                        <div>
                            <p className="text-sm text-neutral-500">Accepted By</p>
                            <p className="font-medium">{returnItem.accepted_by}</p>
                        </div>
                    )}
                    {returnItem.note && (
                        <div className="col-span-full">
                            <p className="text-sm text-neutral-500">Note</p>
                            <p className="font-medium">{returnItem.note}</p>
                        </div>
                    )}
                </div>
            </Card>

            {/* Return Items */}
            <Card className="p-6">
                <h3 className="font-semibold text-neutral-900 mb-3">Returned Items</h3>
                {returnItem.items && returnItem.items.length > 0 ? (
                    <div className="overflow-x-auto">
                        <table className="w-full">
                            <thead>
                                <tr className="border-b border-neutral-200">
                                    <th className="px-3 py-2 text-left text-xs font-medium text-neutral-500">Product</th>
                                    <th className="px-3 py-2 text-left text-xs font-medium text-neutral-500">Quantity</th>
                                    <th className="px-3 py-2 text-left text-xs font-medium text-neutral-500">Unit Price</th>
                                    <th className="px-3 py-2 text-left text-xs font-medium text-neutral-500">GST%</th>
                                    <th className="px-3 py-2 text-left text-xs font-medium text-neutral-500">WHT%</th>
                                    <th className="px-3 py-2 text-right text-xs font-medium text-neutral-500">Total</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-neutral-100">
                                {returnItem.items.map((item, index) => (
                                    <tr key={item.id || index} className="hover:bg-neutral-50">
                                        <td className="px-3 py-2 text-sm">
                                            {item.product_name}
                                            {item.shelf_allocations?.length > 0 && (
                                                <ul className="mt-1 text-xs text-neutral-500 space-y-0.5">
                                                    {item.shelf_allocations.map((a) => (
                                                        <li key={a.id}>{a.shelf.name}: {a.quantity}</li>
                                                    ))}
                                                </ul>
                                            )}
                                        </td>
                                        <td className="px-3 py-2 text-sm">{item.quantity}</td>
                                        <td className="px-3 py-2 text-sm">
                                            {typeof item.unit_price === 'string'
                                                ? parseFloat(item.unit_price).toFixed(2)
                                                : '0.00'}
                                        </td>
                                        <td className="px-3 py-2 text-sm">{item.gst || 0}%</td>
                                        <td className="px-3 py-2 text-sm">{item.wht || 0}%</td>
                                        <td className="px-3 py-2 text-sm text-right font-medium">
                                            {displayItemTotal(item).toFixed(2)}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                            <tfoot className="border-t border-neutral-200">
                                <tr className="text-lg">
                                    <td colSpan="5" className="px-3 py-2 text-right font-bold">Total Return Amount:</td>
                                    <td className="px-3 py-2 text-right font-bold text-primary-600">
                                        {displayReturnTotal().toFixed(2)}
                                    </td>
                                </tr>
                            </tfoot>
                        </table>
                    </div>
                ) : (
                    <p className="text-center text-neutral-500 py-4">No items in this return</p>
                )}
            </Card>

            {/* Shelf Allocation — pending returns only, required before accept */}
            {returnItem.status === 'pending' && (
                <Card className="p-6" hover={false}>
                    <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                        <h3 className="font-semibold text-neutral-900">Shelf Allocation</h3>
                        <div className="flex gap-2">
                            <Button
                                size="sm"
                                variant="secondary"
                                onClick={handleAutoAllocateAll}
                                loading={bulkAutoAllocating}
                                disabled={bulkSaving}
                            >
                                Auto-Allocate All
                            </Button>
                            <Button
                                size="sm"
                                icon={Save}
                                onClick={handleSaveAllocationsAll}
                                loading={bulkSaving}
                                disabled={bulkAutoAllocating}
                            >
                                Save All Allocations
                            </Button>
                        </div>
                    </div>
                    <p className="text-sm text-neutral-500 mb-4">
                        Select which shelf(s) each returned item is being pulled from before accepting this return.
                    </p>
                    {allocationError && (
                        <InlineAlert variant="error" message={allocationError} className="mb-4" />
                    )}
                    <div className="space-y-6">
                        {returnItem.items?.map((item) => (
                            <div key={item.id} className="p-4 bg-neutral-50 rounded-xl border border-neutral-200">
                                <div className="mb-3">
                                    <p className="font-medium">{item.product_name} {item.product_code ? `(${item.product_code})` : ''}</p>
                                    <p className="text-sm text-neutral-500">Quantity: {item.quantity}</p>
                                </div>
                                <ShelfAllocationEditor
                                    value={allocationDrafts[item.id] || []}
                                    onChange={(next) => setAllocationDrafts((prev) => ({ ...prev, [item.id]: next }))}
                                    shelves={candidateShelves[item.id] || []}
                                    requiredQuantity={item.quantity}
                                    mode="consumption"
                                    disabled={bulkSaving || bulkAutoAllocating}
                                    productId={getItemProductId(item)}
                                    autoAllocateApi={purchasesApi.shelves.autoAllocate}
                                />
                            </div>
                        ))}
                    </div>
                </Card>
            )}

            {/* Related Order */}
            {order && (
                <Card className="p-6">
                    <h3 className="font-semibold text-neutral-900 mb-3">Related Order</h3>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
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
                            <p className="font-medium">
                                {typeof order.net_payable === 'string'
                                    ? parseFloat(order.net_payable).toFixed(2)
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
            {returnItem.status === 'pending' && isAdmin && (
                <div className="flex flex-wrap gap-3 pt-4 border-t border-neutral-200">
                    <Button variant="secondary" icon={Pencil} onClick={() => setShowEditForm(true)}>
                        Edit
                    </Button>
                    <Button variant="danger" icon={XCircle} onClick={() => setShowCancelConfirm(true)}>
                        Cancel Return
                    </Button>
                    <Button variant="success" icon={CheckCircle2} onClick={() => setShowAcceptConfirm(true)}>
                        Accept Return
                    </Button>
                </div>
            )}

            {/* Edit Return Modal */}
            <Modal
                isOpen={showEditForm}
                onClose={() => setShowEditForm(false)}
                title="Edit Return"
                size="lg"
            >
                <ReturnForm
                    onSubmit={handleUpdateReturn}
                    onCancel={() => setShowEditForm(false)}
                    loading={formLoading}
                    orderItems={order?.items || []}
                    initialItems={getInitialEditItems()}
                    initialNote={returnItem.note}
                    submitLabel="Save Changes"
                />
            </Modal>

            <ConfirmDialog
                isOpen={showAcceptConfirm}
                onClose={() => setShowAcceptConfirm(false)}
                onConfirm={handleAcceptReturn}
                title="Accept Return"
                message="Are you sure you want to accept this return? This action cannot be undone."
                confirmText="Accept"
                variant="primary"
                loading={acceptLoading}
            />

            <ConfirmDialog
                isOpen={showCancelConfirm}
                onClose={() => setShowCancelConfirm(false)}
                onConfirm={handleCancelReturn}
                title="Cancel Return"
                message="Cancel this return? This cannot be undone."
                confirmText="Cancel Return"
                variant="danger"
                loading={cancelLoading}
            />
        </div>
    );
};

export default PurchaseReturnDetailPage;
