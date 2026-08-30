import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Printer, FileDown, CreditCard, Undo2, Pencil, CheckCircle2, Trash2, FileText } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { purchasesApi } from '../../services/purchasesApi';
import Button from '../../components/ui/Button';
import BackLink from '../../components/ui/BackLink';
import Card from '../../components/ui/Card';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Badge from '../../components/ui/Badge';
import Modal from '../../components/ui/Modal';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import InlineAlert from '../../components/ui/InlineAlert';
import Tabs from '../../components/ui/Tabs';
import EmptyState from '../../components/ui/EmptyState';
import OrderStatusBadge from '../../components/purchases/OrderStatusBadge';
import OrderPaymentStatusBadge from '../../components/purchases/OrderPaymentStatusBadge';
import OrderSummaryCard from '../../components/purchases/OrderSummaryCard';
import PaymentHistoryList from '../../components/purchases/PaymentHistoryList';
import PaymentForm from '../../components/purchases/PaymentForm';
import ReturnList from '../../components/purchases/ReturnList';
import ReturnForm from '../../components/purchases/ReturnForm';
import SavePDFModal from '../../components/purchases/SavePDFModal';
import PurchaseOrderFormModal from '../../components/purchases/PurchaseOrderFormModal';
import ShelfAllocationEditor from '../../components/shared/ShelfAllocationEditor';
import { useToast } from '../../context/ToastContext';
import { extractErrorMessage } from '../../utils/errorMessage';

const PurchaseOrderDetailPage = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const { user } = useAuth();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';
    const { toast } = useToast();

    const [order, setOrder] = useState(null);
    const [paymentSummary, setPaymentSummary] = useState(null);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState('');
    const [showPaymentForm, setShowPaymentForm] = useState(false);
    const [showReturnForm, setShowReturnForm] = useState(false);
    const [showSavePDFModal, setShowSavePDFModal] = useState(false);
    const [formLoading, setFormLoading] = useState(false);
    const [pdfs, setPdfs] = useState([]);
    const [returns, setReturns] = useState([]);
    const [payments, setPayments] = useState([]);
    const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
    const [deletingOrder, setDeletingOrder] = useState(false);
    const [hasPendingReturn, setHasPendingReturn] = useState(false);
    const [showEditModal, setShowEditModal] = useState(false);
    const [allocationDrafts, setAllocationDrafts] = useState({});
    const [savingAllocationFor, setSavingAllocationFor] = useState(null);
    const [confirmError, setConfirmError] = useState('');
    const [confirmOrderOpen, setConfirmOrderOpen] = useState(false);
    const [confirmingOrder, setConfirmingOrder] = useState(false);
    const [pdfToDelete, setPdfToDelete] = useState(null);
    const [deletingPdf, setDeletingPdf] = useState(false);
    const [paymentToDelete, setPaymentToDelete] = useState(null);
    const [deletingPayment, setDeletingPayment] = useState(false);
    const [returnToAccept, setReturnToAccept] = useState(null);
    const [acceptingReturn, setAcceptingReturn] = useState(false);
    const [activeTab, setActiveTab] = useState('items');

    useEffect(() => {
        fetchData();
    }, [id]);

    // Keep per-item allocation drafts in sync with the order's saved state
    // (initial load and after every refetch following a save/confirm).
    useEffect(() => {
        if (!order?.items) return;
        setAllocationDrafts((prev) => {
            const next = { ...prev };
            order.items.forEach((item) => {
                next[item.id] = (item.shelf_allocations || []).map((a) => ({
                    shelf_id: a.shelf.id,
                    quantity: a.quantity,
                    shelf_name: a.shelf.name,
                }));
            });
            return next;
        });
    }, [order]);

    // Put-away — any shelf is valid, so this searches the full shelf list by
    // name (a large factory can have hundreds of shelves, so this is a live
    // backend search, not a preloaded dropdown).
    const searchShelvesForPutAway = async (query) => {
        const res = await purchasesApi.shelves.getAll({ search: query, page_size: 25 });
        const results = res?.results ?? res ?? [];
        return results.map((s) => ({ value: s.id, label: s.name, name: s.name }));
    };

    const fetchData = async () => {
        setLoading(true);
        setLoadError('');
        try {
            const [orderData, summaryData] = await Promise.all([
                purchasesApi.orders.getById(id),
                purchasesApi.orders.getPaymentSummary(id),
            ]);
            setOrder(orderData);
            setPaymentSummary(summaryData);

            const [paymentsRes, returnsRes, pdfsData] = await Promise.all([
                purchasesApi.payments.getByOrder(id).catch(() => []),
                purchasesApi.returns.getByOrder(id).catch(() => []),
                orderData?.status === 'confirmed'
                    ? purchasesApi.orders.getPDFs(id).catch(() => [])
                    : Promise.resolve([]),
            ]);
            // payments/returns endpoints now return paginated {results: [...]} objects
            // instead of plain arrays; unwrap both shapes.
            const paymentsData = Array.isArray(paymentsRes) ? paymentsRes : (paymentsRes?.results || []);
            const returnsData = Array.isArray(returnsRes) ? returnsRes : (returnsRes?.results || []);
            setPayments(paymentsData);
            setReturns(returnsData);
            setPdfs(Array.isArray(pdfsData) ? pdfsData : (pdfsData?.results || []));

            const hasPending = returnsData.some(r => r.status === 'pending');
            setHasPendingReturn(hasPending);
        } catch (error) {
            console.error('Failed to fetch order details:', error);
            setLoadError(extractErrorMessage(error, 'Failed to load order details'));
        } finally {
            setLoading(false);
        }
    };

    const handlePrint = async () => {
        try {
            const isDraft = order?.status === 'draft';
            const data = await purchasesApi.orders.print(id, isDraft);
            const blob = new Blob([data], { type: 'application/pdf' });
            const url = window.URL.createObjectURL(blob);
            window.open(url, '_blank');
            setTimeout(() => {
                window.URL.revokeObjectURL(url);
            }, 1000);
        } catch (error) {
            console.error('Failed to print order:', error);
            toast.error(extractErrorMessage(error, 'Failed to print order. Please try again.'));
        }
    };

    const handleSavePDF = async (fileName) => {
        setFormLoading(true);
        try {
            await purchasesApi.orders.savePDF(id, { file_name: fileName });
            setShowSavePDFModal(false);
            toast.success('PDF saved successfully');
            await fetchData();
        } catch (error) {
            console.error('Failed to save PDF:', error);
            toast.error(extractErrorMessage(error, 'Failed to save PDF'));
        } finally {
            setFormLoading(false);
        }
    };

    const confirmDeletePDF = async () => {
        if (!pdfToDelete) return;
        setDeletingPdf(true);
        try {
            await purchasesApi.orders.deletePDF(pdfToDelete.id);
            toast.success('PDF deleted');
            await fetchData();
        } catch (error) {
            console.error('Failed to delete PDF:', error);
            toast.error(extractErrorMessage(error, 'Failed to delete PDF'));
        } finally {
            setDeletingPdf(false);
            setPdfToDelete(null);
        }
    };

    const handleRecordPayment = async (data) => {
        setFormLoading(true);
        try {
            await purchasesApi.payments.create(id, data);
            setShowPaymentForm(false);
            toast.success('Payment recorded successfully');
            await fetchData();
        } catch (error) {
            console.error('Failed to record payment:', error);
            toast.error(extractErrorMessage(error, 'Failed to record payment'));
        } finally {
            setFormLoading(false);
        }
    };

    const confirmDeletePayment = async () => {
        if (!paymentToDelete) return;
        setDeletingPayment(true);
        try {
            await purchasesApi.payments.delete(paymentToDelete);
            toast.success('Payment deleted');
            await fetchData();
        } catch (error) {
            console.error('Failed to delete payment:', error);
            toast.error(extractErrorMessage(error, 'Failed to delete payment'));
        } finally {
            setDeletingPayment(false);
            setPaymentToDelete(null);
        }
    };

    const handleCreateReturn = async (data) => {
        setFormLoading(true);
        try {
            await purchasesApi.returns.create(id, data);
            setShowReturnForm(false);
            toast.success('Return created successfully');
            await fetchData();
        } catch (error) {
            console.error('Failed to create return:', error);
            toast.error(extractErrorMessage(error, 'Failed to create return'));
        } finally {
            setFormLoading(false);
        }
    };

    const confirmAcceptReturn = async () => {
        if (!returnToAccept) return;
        setAcceptingReturn(true);
        try {
            await purchasesApi.returns.accept(returnToAccept);
            toast.success('Return accepted');
            await fetchData();
        } catch (error) {
            console.error('Failed to accept return:', error);
            toast.error(extractErrorMessage(error, 'Failed to accept return'));
        } finally {
            setAcceptingReturn(false);
            setReturnToAccept(null);
        }
    };

    const confirmOrderAction = async () => {
        setConfirmError('');
        setConfirmingOrder(true);
        try {
            await purchasesApi.orders.confirm(id);
            toast.success('Order confirmed');
            await fetchData();
            setConfirmOrderOpen(false);
        } catch (error) {
            console.error('Failed to confirm order:', error);
            const errorMsg = extractErrorMessage(error, 'Failed to confirm order');
            setConfirmError(errorMsg);
            toast.error(errorMsg);
            setConfirmOrderOpen(false);
        } finally {
            setConfirmingOrder(false);
        }
    };

    const handleSaveAllocations = async (itemId) => {
        const allocations = (allocationDrafts[itemId] || [])
            .filter((a) => a.shelf_id && a.quantity)
            .map((a) => ({ shelf_id: parseInt(a.shelf_id, 10), quantity: parseInt(a.quantity, 10) }));
        setSavingAllocationFor(itemId);
        try {
            await purchasesApi.purchaseItems.setShelfAllocations(itemId, allocations);
            toast.success('Shelf allocations saved');
            await fetchData();
        } catch (error) {
            console.error('Failed to save shelf allocations:', error);
            toast.error(extractErrorMessage(error, 'Failed to save shelf allocations'));
        } finally {
            setSavingAllocationFor(null);
        }
    };

    const handleOpenEdit = () => {
        setShowEditModal(true);
    };

    const searchProducts = async (query) => {
        const res = await purchasesApi.products.getAll({ search: query, page_size: 25 });
        const results = res?.results ?? res ?? [];
        return results.map(p => ({ value: p.id, label: `${p.code} - ${p.name}` }));
    };

    // Supplier is disabled/read-only on edit (see PurchaseOrderFormModal), so
    // this only exists to satisfy the shared modal's required prop.
    const searchSuppliers = async (query) => {
        const res = await purchasesApi.suppliers.getAll({ search: query });
        const results = res?.results ?? res ?? [];
        return results.map(s => ({ value: s.id, label: `${s.name} (${s.code})` }));
    };

    const handleUpdateOrder = async (payload) => {
        await purchasesApi.orders.update(id, payload);
        setShowEditModal(false);
        await fetchData();
    };

    const handleDeleteOrder = async () => {
        setDeletingOrder(true);
        try {
            await purchasesApi.orders.delete(id);
            toast.success('Purchase order deleted');
            navigate('/purchases/orders');
        } catch (error) {
            console.error('Failed to delete order:', error);
            toast.error(extractErrorMessage(error, 'Failed to delete order'));
            setDeletingOrder(false);
            setShowDeleteConfirm(false);
        }
    };

    const itemsTable = order && (
        <>
            <div className="overflow-x-auto">
                <table className="w-full">
                    <thead>
                        <tr className="border-b border-neutral-200">
                            <th className="px-3 py-2 text-left text-xs font-medium text-neutral-500">Product</th>
                            <th className="px-3 py-2 text-left text-xs font-medium text-neutral-500">Qty</th>
                            <th className="px-3 py-2 text-left text-xs font-medium text-neutral-500">Unit Price</th>
                            <th className="px-3 py-2 text-left text-xs font-medium text-neutral-500">GST%</th>
                            <th className="px-3 py-2 text-left text-xs font-medium text-neutral-500">WHT%</th>
                            <th className="px-3 py-2 text-right text-xs font-medium text-neutral-500">Total</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-neutral-100">
                        {order.items?.map((item, index) => (
                            <tr key={item.id || index} className="hover:bg-neutral-50">
                                <td className="px-3 py-2 text-sm">
                                    {item.product_name || 'N/A'}
                                    {order.status !== 'draft' && item.shelf_allocations?.length > 0 && (
                                        <ul className="mt-1 text-xs text-neutral-500 space-y-0.5">
                                            {item.shelf_allocations.map((a) => (
                                                <li key={a.id}>{a.shelf.name}: {a.quantity}</li>
                                            ))}
                                        </ul>
                                    )}
                                </td>
                                <td className="px-3 py-2 text-sm">{item.quantity}</td>
                                <td className="px-3 py-2 text-sm">
                                    {typeof item.unit_price === 'string' ? parseFloat(item.unit_price).toFixed(2) : '0.00'}
                                </td>
                                <td className="px-3 py-2 text-sm">{item.gst || 0}%</td>
                                <td className="px-3 py-2 text-sm">{item.wht || 0}%</td>
                                <td className="px-3 py-2 text-sm text-right font-medium">
                                    {item.total_price ? parseFloat(item.total_price).toFixed(2) : '0.00'}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                    <tfoot className="border-t border-neutral-200">
                        <tr>
                            <td colSpan="5" className="px-3 py-2 text-right font-medium">Gross Amount:</td>
                            <td className="px-3 py-2 text-right font-medium">
                                {order.gross_amount ? parseFloat(order.gross_amount).toFixed(2) : '0.00'}
                            </td>
                        </tr>
                        {order.gst_total && parseFloat(order.gst_total) > 0 && (
                            <tr>
                                <td colSpan="5" className="px-3 py-2 text-right font-medium">GST Total:</td>
                                <td className="px-3 py-2 text-right font-medium">
                                    {parseFloat(order.gst_total).toFixed(2)}
                                </td>
                            </tr>
                        )}
                        {order.wht_total && parseFloat(order.wht_total) > 0 && (
                            <tr>
                                <td colSpan="5" className="px-3 py-2 text-right font-medium">WHT Total:</td>
                                <td className="px-3 py-2 text-right font-medium">
                                    {parseFloat(order.wht_total).toFixed(2)}
                                </td>
                            </tr>
                        )}
                        <tr className="text-lg">
                            <td colSpan="5" className="px-3 py-2 text-right font-bold">Net Payable:</td>
                            <td className="px-3 py-2 text-right font-bold text-primary-600">
                                {order.net_payable ? parseFloat(order.net_payable).toFixed(2) : '0.00'}
                            </td>
                        </tr>
                    </tfoot>
                </table>
            </div>

            {order.description && (
                <div className="mt-4 pt-4 border-t border-neutral-200">
                    <p className="text-sm text-neutral-500">Description</p>
                    <p className="font-medium">{order.description}</p>
                </div>
            )}
        </>
    );

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    if (!order) {
        return (
            <div className="text-center py-12">
                {loadError ? (
                    <div className="max-w-md mx-auto text-left">
                        <InlineAlert variant="error" message={loadError} onRetry={fetchData} />
                    </div>
                ) : (
                    <h2 className="text-2xl font-semibold text-neutral-900">Order Not Found</h2>
                )}
                <BackLink to="/purchases/orders" className="mt-4">Back to Orders</BackLink>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <BackLink to="/purchases/orders">Back to Orders</BackLink>
                    <h1 className="text-3xl font-bold text-neutral-900 mt-1">{order.order_number}</h1>
                    <div className="flex gap-2 mt-1 flex-wrap">
                        <OrderStatusBadge status={order.status} />
                        <OrderPaymentStatusBadge status={order.payment_status} />
                    </div>
                </div>
                <div className="flex gap-2 flex-wrap items-center">
                    {/* Print button hidden while order is draft */}
                    {order.status !== 'draft' && (
                        <Button variant="secondary" onClick={handlePrint} icon={Printer}>
                            Print
                        </Button>
                    )}

                    {order.status === 'confirmed' && (
                        <>
                            {isAdmin && (
                                <Button variant="secondary" onClick={() => setShowSavePDFModal(true)} icon={FileDown}>
                                    Save PDF
                                </Button>
                            )}
                            <Button variant="secondary" onClick={() => setShowPaymentForm(true)} icon={CreditCard}>
                                Record Payment
                            </Button>
                            {!hasPendingReturn && (
                                <Button variant="secondary" onClick={() => setShowReturnForm(true)} icon={Undo2}>
                                    Create Return
                                </Button>
                            )}
                            {hasPendingReturn && (
                                <Badge variant="warning" className="ml-2">
                                    Return Pending
                                </Badge>
                            )}
                        </>
                    )}

                    {order.status === 'draft' && isAdmin && (
                        <>
                            <Button variant="secondary" onClick={handleOpenEdit} icon={Pencil}>
                                Edit
                            </Button>
                            <Button variant="success" onClick={() => setConfirmOrderOpen(true)} icon={CheckCircle2}>
                                Confirm
                            </Button>
                            <Button variant="danger" onClick={() => setShowDeleteConfirm(true)} icon={Trash2}>
                                Delete
                            </Button>
                        </>
                    )}
                </div>
            </div>

            {confirmError && (
                <InlineAlert variant="error" message={confirmError} />
            )}

            {/* Supplier Info */}
            <Card className="p-6">
                <h3 className="font-semibold text-neutral-900 mb-3">Supplier Information</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div>
                        <p className="text-sm text-neutral-500">Name</p>
                        <p className="font-medium">{order.supplier?.name || 'N/A'}</p>
                    </div>
                    <div>
                        <p className="text-sm text-neutral-500">Code</p>
                        <p className="font-medium">{order.supplier?.code || 'N/A'}</p>
                    </div>
                    <div>
                        <p className="text-sm text-neutral-500">Payment Type</p>
                        <p className="font-medium capitalize">{order.payment_type?.replace('_', ' ') || 'N/A'}</p>
                    </div>
                    {order.advance_amount && parseFloat(order.advance_amount) > 0 && (
                        <div>
                            <p className="text-sm text-neutral-500">Advance Amount (PKR)</p>
                            <p className="font-medium">
                                {typeof order.advance_amount === 'string'
                                    ? parseFloat(order.advance_amount).toFixed(2)
                                    : '0.00'}
                            </p>
                        </div>
                    )}
                </div>
            </Card>

            {/* Payment Summary */}
            {paymentSummary && order.status !== 'draft' && (
                <OrderSummaryCard summary={paymentSummary} />
            )}

            {order.status === 'draft' ? (
                <>
                    {/* Order Items */}
                    <Card className="p-6">
                        <h3 className="font-semibold text-neutral-900 mb-3">Items</h3>
                        {itemsTable}
                    </Card>

                    {/* Put-Away — shelf allocation for draft orders, required before confirm */}
                    <Card className="p-6">
                        <h3 className="font-semibold text-neutral-900 mb-3">Put-Away (Shelf Allocation)</h3>
                        <p className="text-sm text-neutral-500 mb-4">
                            Allocate each item's full quantity to shelves before confirming this order.
                        </p>
                        <div className="space-y-6">
                            {order.items?.map((item) => (
                                <div key={item.id} className="p-4 bg-neutral-50 rounded-lg border border-neutral-200">
                                    <div className="flex items-center justify-between mb-3">
                                        <div>
                                            <p className="font-medium">{item.product_name} {item.product_code ? `(${item.product_code})` : ''}</p>
                                            <p className="text-sm text-neutral-500">Quantity: {item.quantity}</p>
                                        </div>
                                    </div>
                                    <ShelfAllocationEditor
                                        value={allocationDrafts[item.id] || []}
                                        onChange={(next) => setAllocationDrafts((prev) => ({ ...prev, [item.id]: next }))}
                                        onSearchShelves={searchShelvesForPutAway}
                                        requiredQuantity={item.quantity}
                                        mode="putaway"
                                        disabled={savingAllocationFor === item.id}
                                    />
                                    <div className="flex justify-end mt-3">
                                        <Button
                                            size="sm"
                                            onClick={() => handleSaveAllocations(item.id)}
                                            loading={savingAllocationFor === item.id}
                                        >
                                            Save Allocations
                                        </Button>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </Card>
                </>
            ) : (
                <Card className="p-0 overflow-hidden" hover={false}>
                    <div className="px-4 sm:px-6 pt-4">
                        <Tabs
                            tabs={[
                                { value: 'items', label: 'Items', count: order.items?.length ?? 0 },
                                { value: 'payments', label: 'Payments', count: payments.length },
                                { value: 'returns', label: 'Returns', count: returns.length },
                                { value: 'pdfs', label: 'Saved PDFs', count: pdfs.length },
                            ]}
                            activeTab={activeTab}
                            onChange={setActiveTab}
                        />
                    </div>
                    <div className="p-4 sm:p-6">
                        <AnimatePresence mode="wait">
                            <motion.div
                                key={activeTab}
                                initial={{ opacity: 0, y: 8 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0, y: -8 }}
                                transition={{ duration: 0.18 }}
                            >
                                {activeTab === 'items' && itemsTable}

                                {activeTab === 'payments' && (
                                    <PaymentHistoryList
                                        payments={payments}
                                        onDelete={(paymentId) => setPaymentToDelete(paymentId)}
                                        isAdmin={isAdmin}
                                    />
                                )}

                                {activeTab === 'returns' && (
                                    <ReturnList
                                        returns={returns}
                                        onAccept={(returnId) => setReturnToAccept(returnId)}
                                        isAdmin={isAdmin}
                                        orderItems={order.items || []}
                                    />
                                )}

                                {activeTab === 'pdfs' && (
                                    pdfs.length === 0 ? (
                                        <EmptyState
                                            icon={<FileText className="w-10 h-10 text-neutral-300" />}
                                            title="No saved PDFs yet"
                                            description="PDFs you save for this order will appear here."
                                        />
                                    ) : (
                                        <div className="space-y-2">
                                            {pdfs.map((pdf) => (
                                                <div key={pdf.id} className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-3 p-3 bg-neutral-50 rounded-lg hover:bg-neutral-100 transition-colors">
                                                    <div className="flex items-start gap-3 min-w-0">
                                                        <FileText className="w-5 h-5 text-neutral-400 flex-shrink-0 mt-0.5" />
                                                        <div className="min-w-0">
                                                            <a
                                                                href={pdf.file_url}
                                                                target="_blank"
                                                                rel="noopener noreferrer"
                                                                className="font-medium text-primary-600 hover:text-primary-700 hover:underline break-all"
                                                            >
                                                                {pdf.file_name}
                                                            </a>
                                                            <p className="text-xs text-neutral-500">
                                                                Saved: {new Date(pdf.created_at).toLocaleString()}
                                                            </p>
                                                        </div>
                                                    </div>
                                                    <Button
                                                        size="sm"
                                                        variant="danger"
                                                        icon={Trash2}
                                                        onClick={() => setPdfToDelete(pdf)}
                                                        className="self-start sm:self-auto"
                                                    >
                                                        Delete
                                                    </Button>
                                                </div>
                                            ))}
                                        </div>
                                    )
                                )}
                            </motion.div>
                        </AnimatePresence>
                    </div>
                </Card>
            )}

            {/* Edit Order Modal — draft orders only */}
            {order.status === 'draft' && (
                <PurchaseOrderFormModal
                    isOpen={showEditModal}
                    onClose={() => setShowEditModal(false)}
                    onSubmit={handleUpdateOrder}
                    onSearchProducts={searchProducts}
                    onSearchSuppliers={searchSuppliers}
                    title="Edit Purchase Order"
                    submitLabel="Save Changes"
                    initialData={{
                        supplier: order.supplier?.id || '',
                        supplier_label: order.supplier?.code ? `${order.supplier.name} (${order.supplier.code})` : order.supplier?.name,
                        payment_type: order.payment_type,
                        advance_amount: order.advance_amount || '',
                        description: order.description || '',
                        items: (order.items || []).map((item) => ({
                            product: item.product,
                            product_label: item.product_code ? `${item.product_code} - ${item.product_name}` : item.product_name,
                            quantity: item.quantity,
                            unit_price: item.unit_price,
                            gst: item.gst,
                            wht: item.wht,
                            description: item.description || '',
                        })),
                    }}
                />
            )}

            {/* Payment Form Modal */}
            <Modal
                isOpen={showPaymentForm}
                onClose={() => setShowPaymentForm(false)}
                title="Record Payment"
            >
                <PaymentForm
                    onSubmit={handleRecordPayment}
                    onCancel={() => setShowPaymentForm(false)}
                    loading={formLoading}
                    maxAmount={paymentSummary?.payable_outstanding ? parseFloat(paymentSummary.payable_outstanding) : undefined}
                />
            </Modal>

            {/* Return Form Modal */}
            <Modal
                isOpen={showReturnForm}
                onClose={() => setShowReturnForm(false)}
                title="Create Return"
                size="lg"
            >
                <ReturnForm
                    onSubmit={handleCreateReturn}
                    onCancel={() => setShowReturnForm(false)}
                    loading={formLoading}
                    orderItems={order.items || []}
                />
            </Modal>

            {/* Save PDF Modal */}
            <SavePDFModal
                isOpen={showSavePDFModal}
                onClose={() => setShowSavePDFModal(false)}
                onSubmit={handleSavePDF}
                loading={formLoading}
                defaultFileName={order.order_number}
            />

            {/* Delete Order Confirmation */}
            <ConfirmDialog
                isOpen={showDeleteConfirm}
                onClose={() => setShowDeleteConfirm(false)}
                onConfirm={handleDeleteOrder}
                title="Delete Order"
                message="Are you sure you want to delete this draft order? This action cannot be undone."
                confirmText="Delete Order"
                loading={deletingOrder}
            />

            {/* Confirm Order Confirmation */}
            <ConfirmDialog
                isOpen={confirmOrderOpen}
                onClose={() => setConfirmOrderOpen(false)}
                onConfirm={confirmOrderAction}
                title="Confirm Order"
                message="Are you sure you want to confirm this order? Stock will be reserved and it can no longer be edited."
                confirmText="Confirm Order"
                variant="primary"
                loading={confirmingOrder}
            />

            {/* Delete PDF Confirmation */}
            <ConfirmDialog
                isOpen={!!pdfToDelete}
                onClose={() => setPdfToDelete(null)}
                onConfirm={confirmDeletePDF}
                title="Delete PDF"
                message={`Are you sure you want to delete "${pdfToDelete?.file_name}"?`}
                confirmText="Delete"
                loading={deletingPdf}
            />

            {/* Delete Payment Confirmation */}
            <ConfirmDialog
                isOpen={!!paymentToDelete}
                onClose={() => setPaymentToDelete(null)}
                onConfirm={confirmDeletePayment}
                title="Delete Payment"
                message="Are you sure you want to delete this payment? This action cannot be undone."
                confirmText="Delete"
                loading={deletingPayment}
            />

            {/* Accept Return Confirmation */}
            <ConfirmDialog
                isOpen={!!returnToAccept}
                onClose={() => setReturnToAccept(null)}
                onConfirm={confirmAcceptReturn}
                title="Accept Return"
                message="Are you sure you want to accept this return? This will adjust stock and payable amounts."
                confirmText="Accept"
                variant="primary"
                loading={acceptingReturn}
            />
        </div>
    );
};

export default PurchaseOrderDetailPage;
