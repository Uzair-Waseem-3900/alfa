import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
    Undo2, CheckCircle2, XCircle, Pencil, FileText,
    Package, Warehouse, Receipt, StickyNote,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { billingApi } from '../../services/billingApi';
import { purchasesApi } from '../../services/purchasesApi';
import { api } from '../../utils/api';
import { extractErrorMessage } from '../../utils/errorMessage';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Badge from '../../components/ui/Badge';
import BackLink from '../../components/ui/BackLink';
import Modal from '../../components/ui/Modal';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import InlineAlert from '../../components/ui/InlineAlert';
import InvoiceStatusBadge from '../../components/billing/InvoiceStatusBadge';
import PaymentStatusBadge from '../../components/billing/PaymentStatusBadge';
import ShelfAllocationEditor from '../../components/shared/ShelfAllocationEditor';
import ReturnForm from '../../components/billing/ReturnForm';

const ReturnDetailPage = () => {
    const { returnId } = useParams();
    const navigate = useNavigate();
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const [returnItem, setReturnItem] = useState(null);
    const [invoice, setInvoice] = useState(null);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState('');
    // Per return-item shelf allocation UI state, keyed by return item id:
    // { allocations: [{shelf_id, quantity}], saving: bool, error: string }
    const [shelfState, setShelfState] = useState({});
    const [showEditForm, setShowEditForm] = useState(false);
    const [formLoading, setFormLoading] = useState(false);
    const [showAcceptConfirm, setShowAcceptConfirm] = useState(false);
    const [acceptLoading, setAcceptLoading] = useState(false);
    const [showCancelConfirm, setShowCancelConfirm] = useState(false);
    const [cancelLoading, setCancelLoading] = useState(false);

    useEffect(() => {
        fetchReturnDetails();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [returnId]);

    const fetchReturnDetails = async () => {
        setLoading(true);
        setLoadError('');
        try {
            // Fetch the single return directly by id rather than paging
            // through the full returns list looking for a match.
            const foundReturn = await api.get(`/billing/returns/${returnId}/`);
            setReturnItem(foundReturn);

            // Fetch the full related invoice
            try {
                const invoiceData = await billingApi.invoices.getById(foundReturn.invoice);
                setInvoice(invoiceData);
            } catch (invoiceError) {
                console.error('Failed to fetch related invoice:', invoiceError);
                setInvoice(null);
            }

            // Pending returns need the shelf-allocation editor — put-away
            // is valid to any active shelf, so it searches the full shelf
            // list on demand (a large factory can have hundreds of
            // shelves, so this is a live backend search, not a preloaded
            // dropdown), seeded from whatever allocations are already saved.
            if (foundReturn.status === 'pending' && foundReturn.items?.length) {
                setShelfState((prev) => {
                    const next = {};
                    foundReturn.items.forEach((item) => {
                        next[item.id] = {
                            allocations: (item.shelf_allocations || []).map((a) => ({
                                shelf_id: a.shelf_id,
                                quantity: a.quantity,
                                shelf_name: a.shelf_name,
                            })),
                            saving: false,
                            error: prev[item.id]?.error || '',
                        };
                    });
                    return next;
                });
            } else {
                setShelfState({});
            }
        } catch (error) {
            console.error('Failed to fetch return details:', error);
            setReturnItem(null);
            setInvoice(null);
            if (error?.response?.status !== 404) {
                setLoadError(extractErrorMessage(error, 'Failed to load return details.'));
            }
        } finally {
            setLoading(false);
        }
    };

    const searchShelvesForPutAway = async (query) => {
        const res = await purchasesApi.shelves.getAll({ search: query, page_size: 25 });
        const results = res?.results ?? res ?? [];
        return results.map((s) => ({ value: s.id, label: s.name, name: s.name }));
    };

    const handleAllocationChange = (itemId, nextAllocations) => {
        setShelfState((prev) => ({
            ...prev,
            [itemId]: { ...prev[itemId], allocations: nextAllocations },
        }));
    };

    const handleSaveAllocations = async (itemId) => {
        setShelfState((prev) => ({
            ...prev,
            [itemId]: { ...prev[itemId], saving: true, error: '' },
        }));
        try {
            const allocations = (shelfState[itemId]?.allocations || [])
                .filter((a) => a.shelf_id !== '' && a.quantity !== '')
                .map((a) => ({ shelf_id: parseInt(a.shelf_id, 10), quantity: parseInt(a.quantity, 10) }));
            await billingApi.returnItems.setShelfAllocations(itemId, allocations);
            toast.success('Shelf allocations saved.');
            await fetchReturnDetails();
        } catch (error) {
            console.error('Failed to save shelf allocations:', error);
            const message = extractErrorMessage(error, 'Failed to save shelf allocations.');
            setShelfState((prev) => ({
                ...prev,
                [itemId]: { ...prev[itemId], saving: false, error: message },
            }));
        }
    };

    const handleAcceptReturn = async () => {
        setAcceptLoading(true);
        try {
            await billingApi.returns.accept(returnId);
            setShowAcceptConfirm(false);
            toast.success('Return accepted successfully.');
            await fetchReturnDetails();
        } catch (error) {
            console.error('Failed to accept return:', error);
            toast.error(extractErrorMessage(error, 'Failed to accept return.'));
        } finally {
            setAcceptLoading(false);
        }
    };

    const handleUpdateReturn = async (data) => {
        setFormLoading(true);
        try {
            await billingApi.returns.update(returnId, data);
            setShowEditForm(false);
            toast.success('Return updated successfully.');
            await fetchReturnDetails();
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
            await billingApi.returns.cancel(returnId);
            toast.success('Return cancelled.');
            navigate('/billing/returns');
        } catch (error) {
            console.error('Failed to cancel return:', error);
            toast.error(extractErrorMessage(error, 'Failed to cancel return.'));
            setShowCancelConfirm(false);
        } finally {
            setCancelLoading(false);
        }
    };

    // Resolves each return item's current line back to {invoice_item_id,
    // quantity} for the edit form, matching by product_code against the
    // related invoice's items (same pattern used to seed shelf candidates).
    const getInitialEditItems = () => {
        if (!returnItem?.items || !invoice?.items) return [];
        return returnItem.items.map((item) => {
            const invoiceItem = invoice.items.find((ii) => ii.product_code === item.product_code);
            return {
                invoice_item_id: invoiceItem?.id || '',
                quantity: item.quantity,
            };
        });
    };

    // total_return_amount on the return record itself is only computed at
    // accept_return time (by design — see the Return model's docstring);
    // each ReturnItem's line_total is already snapshotted at creation, so
    // preview the header total as their sum while pending instead of
    // showing the not-yet-computed 0.00.
    const displayReturnTotal = () => (
        returnItem.status === 'accepted'
            ? (parseFloat(returnItem.total_return_amount) || 0)
            : (returnItem.items || []).reduce((sum, item) => sum + (parseFloat(item.line_total) || 0), 0)
    );

    // cogs_per_unit/line_cogs are only present in the API response for
    // admin/superuser (stripped server-side for everyone else) — total_cogs
    // is snapshotted per item at creation, unlike total_return_amount which
    // is only computed at accept time, so this doesn't need the pending/
    // accepted branch displayReturnTotal needs.
    const displayReturnCogs = () => (
        returnItem.status === 'accepted'
            ? (parseFloat(returnItem.total_return_cogs) || 0)
            : (returnItem.items || []).reduce((sum, item) => sum + (parseFloat(item.line_cogs) || 0), 0)
    );

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

    if (!returnItem) {
        return (
            <div className="space-y-4">
                {loadError && <InlineAlert variant="error" message={loadError} onRetry={fetchReturnDetails} />}
                <div className="text-center py-12">
                    <h2 className="text-2xl font-semibold text-neutral-900">Return Not Found</h2>
                    <p className="text-neutral-500 mt-1">The return you're looking for doesn't exist.</p>
                    <BackLink to="/billing/returns" className="mt-4">Back to Returns</BackLink>
                </div>
            </div>
        );
    }

    const isPendingAdmin = returnItem.status === 'pending' && isAdmin;

    return (
        <div className="space-y-6">
            <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
                className="flex flex-col sm:flex-row sm:items-center justify-between gap-4"
            >
                <div>
                    <BackLink to="/billing/returns">Back to Returns</BackLink>
                    <div className="flex items-center gap-3 mt-2">
                        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-700 to-accent-600 flex items-center justify-center shadow-lg shadow-primary-900/20 flex-shrink-0">
                            <Undo2 className="w-5 h-5 text-white" />
                        </div>
                        <div>
                            <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900">{returnItem.reference_number}</h1>
                            <div className="flex items-center gap-2 mt-0.5">
                                {getStatusBadge(returnItem.status)}
                            </div>
                        </div>
                    </div>
                </div>
                {isPendingAdmin && (
                    <div className="flex flex-wrap gap-2">
                        <Button variant="secondary" onClick={() => setShowEditForm(true)} icon={Pencil}>
                            Edit
                        </Button>
                        <Button variant="danger" onClick={() => setShowCancelConfirm(true)} icon={XCircle}>
                            Cancel Return
                        </Button>
                        <Button variant="success" onClick={() => setShowAcceptConfirm(true)} icon={CheckCircle2}>
                            Accept Return
                        </Button>
                    </div>
                )}
            </motion.div>

            {loadError && <InlineAlert variant="error" message={loadError} onRetry={fetchReturnDetails} />}

            {/* Return Information */}
            <Card className="p-6">
                <h3 className="font-semibold text-neutral-900 mb-4 flex items-center gap-2">
                    <Receipt className="w-4 h-4 text-neutral-400" />
                    Return Information
                </h3>
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
                        <p className="text-sm text-neutral-500">Total Return Amount</p>
                        <p className="font-semibold text-primary-600">
                            {displayReturnTotal().toFixed(2)}
                        </p>
                    </div>
                    <div>
                        <p className="text-sm text-neutral-500">Created</p>
                        <p className="font-medium">{new Date(returnItem.created_at).toLocaleString()}</p>
                    </div>
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
                            <p className="text-sm text-neutral-500 flex items-center gap-1.5">
                                <StickyNote className="w-3.5 h-3.5" /> Note
                            </p>
                            <p className="font-medium">{returnItem.note}</p>
                        </div>
                    )}
                </div>
            </Card>

            {/* Return Items */}
            <Card className="p-6">
                <h3 className="font-semibold text-neutral-900 mb-4 flex items-center gap-2">
                    <Package className="w-4 h-4 text-neutral-400" />
                    Returned Items
                </h3>
                {returnItem.items && returnItem.items.length > 0 ? (
                    <div className="overflow-x-auto -mx-6 px-6">
                        <table className="w-full min-w-[520px]">
                            <thead>
                                <tr className="border-b border-neutral-200">
                                    <th className="px-3 py-2 text-left text-xs font-medium text-neutral-500 uppercase tracking-wider">Product</th>
                                    <th className="px-3 py-2 text-left text-xs font-medium text-neutral-500 uppercase tracking-wider">Quantity</th>
                                    <th className="px-3 py-2 text-left text-xs font-medium text-neutral-500 uppercase tracking-wider">Unit Price</th>
                                    <th className="px-3 py-2 text-right text-xs font-medium text-neutral-500 uppercase tracking-wider">Total</th>
                                    {isAdmin && (
                                        <>
                                            <th className="px-3 py-2 text-right text-xs font-medium text-neutral-500 uppercase tracking-wider">COGS</th>
                                            <th className="px-3 py-2 text-right text-xs font-medium text-neutral-500 uppercase tracking-wider">Profit Reversed</th>
                                        </>
                                    )}
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-neutral-100">
                                {returnItem.items.map((item, index) => (
                                    <tr key={item.id || index} className="hover:bg-neutral-50">
                                        <td className="px-3 py-2.5 text-sm">{item.product_name}</td>
                                        <td className="px-3 py-2.5 text-sm">{item.quantity}</td>
                                        <td className="px-3 py-2.5 text-sm">
                                            {parseFloat(item.selling_price || 0).toFixed(2)}
                                        </td>
                                        <td className="px-3 py-2.5 text-sm text-right font-medium">
                                            {parseFloat(item.line_total || 0).toFixed(2)}
                                        </td>
                                        {isAdmin && (
                                            <>
                                                <td className="px-3 py-2.5 text-sm text-right text-neutral-600">
                                                    {parseFloat(item.line_cogs || 0).toFixed(2)}
                                                </td>
                                                <td className="px-3 py-2.5 text-sm text-right font-medium text-error-600">
                                                    -{(parseFloat(item.line_total || 0) - parseFloat(item.line_cogs || 0)).toFixed(2)}
                                                </td>
                                            </>
                                        )}
                                    </tr>
                                ))}
                            </tbody>
                            <tfoot className="border-t border-neutral-200">
                                <tr className="text-base">
                                    <td colSpan={isAdmin ? 5 : 3} className="px-3 py-3 text-right font-bold">Total Return Amount:</td>
                                    <td className="px-3 py-3 text-right font-bold text-primary-600">
                                        {displayReturnTotal().toFixed(2)}
                                    </td>
                                </tr>
                                {isAdmin && (
                                    <>
                                        <tr>
                                            <td colSpan={5} className="px-3 py-2 text-right font-medium text-neutral-600">Total COGS:</td>
                                            <td className="px-3 py-2 text-right font-medium text-neutral-600">
                                                {displayReturnCogs().toFixed(2)}
                                            </td>
                                        </tr>
                                        <tr className="text-base">
                                            <td colSpan={5} className="px-3 py-2 text-right font-bold text-error-700">Profit Reversed:</td>
                                            <td className="px-3 py-2 text-right font-bold text-error-700">
                                                -{(displayReturnTotal() - displayReturnCogs()).toFixed(2)}
                                            </td>
                                        </tr>
                                    </>
                                )}
                            </tfoot>
                        </table>
                    </div>
                ) : (
                    <p className="text-center text-neutral-500 py-4">No items in this return</p>
                )}
            </Card>

            {/* Shelf Allocation (put-away) - editable while pending, read-only afterwards */}
            {returnItem.items && returnItem.items.length > 0 && (
                <Card className="p-6">
                    <h3 className="font-semibold text-neutral-900 mb-4 flex items-center gap-2">
                        <Warehouse className="w-4 h-4 text-neutral-400" />
                        Shelf Allocation (Put-Away)
                    </h3>
                    {returnItem.status === 'pending' ? (
                        <div className="space-y-4">
                            {returnItem.items.map((item) => {
                                const state = shelfState[item.id] || { allocations: [], saving: false, error: '' };
                                return (
                                    <div key={item.id} className="border border-neutral-200 rounded-xl p-4">
                                        <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
                                            <div>
                                                <p className="font-medium">
                                                    {item.product_name}{' '}
                                                    <span className="text-neutral-400 text-sm">({item.product_code})</span>
                                                </p>
                                                <p className="text-xs text-neutral-500">
                                                    Quantity: {item.quantity} &middot; Allocated: {item.allocated_quantity}
                                                </p>
                                            </div>
                                        </div>
                                        <ShelfAllocationEditor
                                            value={state.allocations}
                                            onChange={(next) => handleAllocationChange(item.id, next)}
                                            onSearchShelves={searchShelvesForPutAway}
                                            requiredQuantity={item.quantity}
                                            mode="putaway"
                                            disabled={state.saving}
                                        />
                                        {state.error && (
                                            <p className="text-sm text-red-600 mt-2">{state.error}</p>
                                        )}
                                        <div className="flex justify-end mt-3">
                                            <Button
                                                size="sm"
                                                onClick={() => handleSaveAllocations(item.id)}
                                                loading={state.saving}
                                            >
                                                Save Allocations
                                            </Button>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    ) : (
                        <div className="space-y-3">
                            {returnItem.items.map((item) => (
                                <div key={item.id} className="text-sm">
                                    <p className="font-medium">
                                        {item.product_name}{' '}
                                        <span className="text-neutral-400">({item.product_code})</span>
                                    </p>
                                    {item.shelf_allocations?.length > 0 ? (
                                        <ul className="list-disc list-inside text-neutral-600">
                                            {item.shelf_allocations.map((a) => (
                                                <li key={a.id}>{a.shelf_name}: {a.quantity}</li>
                                            ))}
                                        </ul>
                                    ) : (
                                        <p className="text-neutral-400">No shelf allocations recorded</p>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                </Card>
            )}

            {/* Related Invoice */}
            {invoice && (
                <Card className="p-6">
                    <h3 className="font-semibold text-neutral-900 mb-4 flex items-center gap-2">
                        <FileText className="w-4 h-4 text-neutral-400" />
                        Related Invoice
                    </h3>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div>
                            <p className="text-sm text-neutral-500">Bill Number</p>
                            <Link
                                to={`/billing/invoices/${invoice.id}`}
                                className="font-medium text-primary-600 hover:text-primary-700 hover:underline"
                            >
                                {invoice.bill_number}
                            </Link>
                        </div>
                        <div>
                            <p className="text-sm text-neutral-500">Customer</p>
                            <p className="font-medium">{invoice.customer?.name || 'N/A'}</p>
                        </div>
                        <div>
                            <p className="text-sm text-neutral-500">Invoice Status</p>
                            <InvoiceStatusBadge status={invoice.status} />
                        </div>
                        <div>
                            <p className="text-sm text-neutral-500">Payment Status</p>
                            <PaymentStatusBadge status={invoice.payment_status} />
                        </div>
                        <div>
                            <p className="text-sm text-neutral-500">Grand Total</p>
                            <p className="font-medium">
                                {typeof invoice.grand_total === 'string'
                                    ? parseFloat(invoice.grand_total).toFixed(2)
                                    : '0.00'}
                            </p>
                        </div>
                        <div>
                            <p className="text-sm text-neutral-500">Confirmed At</p>
                            <p className="font-medium">
                                {invoice.confirmed_at ? new Date(invoice.confirmed_at).toLocaleDateString() : 'N/A'}
                            </p>
                        </div>
                    </div>
                    <div className="mt-4">
                        <Link to={`/billing/invoices/${invoice.id}`}>
                            <Button variant="secondary" size="sm">
                                View Full Invoice
                            </Button>
                        </Link>
                    </div>
                </Card>
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
                    orderItems={invoice?.items || []}
                    initialItems={getInitialEditItems()}
                    initialNote={returnItem.note}
                    submitLabel="Save Changes"
                />
            </Modal>

            {/* Accept Return Confirm — irreversible: reverses FIFO cost, restores
                inventory, and credits the customer's balance. */}
            <ConfirmDialog
                isOpen={showAcceptConfirm}
                onClose={() => setShowAcceptConfirm(false)}
                onConfirm={handleAcceptReturn}
                title="Accept Return"
                message={`Accept return ${returnItem.reference_number}? This restores inventory and credits the customer's balance. This action cannot be undone.`}
                confirmText="Accept Return"
                variant="primary"
                loading={acceptLoading}
            />

            {/* Cancel Return Confirm */}
            <ConfirmDialog
                isOpen={showCancelConfirm}
                onClose={() => setShowCancelConfirm(false)}
                onConfirm={handleCancelReturn}
                title="Cancel Return"
                message={`Cancel return ${returnItem.reference_number}? This cannot be undone.`}
                confirmText="Cancel Return"
                variant="danger"
                loading={cancelLoading}
            />
        </div>
    );
};

export default ReturnDetailPage;
