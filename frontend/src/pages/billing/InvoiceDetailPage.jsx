import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Printer, Save, CreditCard, RotateCcw, CalendarClock, Pencil,
    CheckCircle2, Trash2, FileText, Package, ExternalLink, Smartphone,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { extractErrorMessage } from '../../utils/errorMessage';
import { creditScoreColorClass } from '../../utils/helpers';
import { billingApi } from '../../services/billingApi';
import BackLink from '../../components/ui/BackLink';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Badge from '../../components/ui/Badge';
import Tabs from '../../components/ui/Tabs';
import InlineAlert from '../../components/ui/InlineAlert';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import EmptyState from '../../components/ui/EmptyState';
import InvoiceStatusBadge from '../../components/billing/InvoiceStatusBadge';
import PaymentStatusBadge from '../../components/billing/PaymentStatusBadge';
import PaymentSummaryCard from '../../components/billing/PaymentSummaryCard';
import PaymentHistoryList from '../../components/billing/PaymentHistoryList';
import PaymentForm from '../../components/billing/PaymentForm';
import ReturnList from '../../components/billing/ReturnList';
import ReturnForm from '../../components/billing/ReturnForm';
import SavePDFModal from '../../components/billing/SavePDFModal';
import DraftPreviewPanel from '../../components/billing/DraftPreviewPanel';
import ExtendDueDateModal from '../../components/billing/ExtendDueDateModal';
import Modal from '../../components/ui/Modal';
import ShelfAllocationEditor from '../../components/shared/ShelfAllocationEditor';

// Configuration for every action that needs a serious "are you sure?" step.
// Keeping this as a lookup keyed by a single `confirmAction.type` state means
// one ConfirmDialog instance can serve every destructive/high-stakes action
// on this page instead of a scattered pile of booleans + native confirm().
const CONFIRM_CONFIG = {
    deleteInvoice: {
        title: 'Delete Draft Invoice',
        confirmText: 'Delete Invoice',
        variant: 'danger',
    },
    confirmInvoice: {
        title: 'Confirm Invoice',
        confirmText: 'Confirm Invoice',
        variant: 'primary',
    },
    deletePayment: {
        title: 'Delete Payment',
        message: "Are you sure you want to delete this payment? This will adjust the invoice's outstanding balance.",
        confirmText: 'Delete Payment',
        variant: 'danger',
    },
    deletePDF: {
        title: 'Delete Saved PDF',
        message: 'Are you sure you want to delete this saved PDF? This cannot be undone.',
        confirmText: 'Delete PDF',
        variant: 'danger',
    },
    acceptReturn: {
        title: 'Accept Return',
        message: "Accepting this return will restore stock and reduce the customer's outstanding credit accordingly.",
        confirmText: 'Accept Return',
        variant: 'primary',
    },
};

const amount = (value) => {
    const n = typeof value === 'string' ? parseFloat(value) : Number(value);
    return Number.isFinite(n) ? n : 0;
};

const InvoiceDetailPage = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const [invoice, setInvoice] = useState(null);
    const [paymentSummary, setPaymentSummary] = useState(null);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState(null);

    // Payments/returns/PDFs are fetched right after the invoice core so the
    // header, totals and items table can paint immediately instead of
    // waiting on every side list.
    const [secondaryLoading, setSecondaryLoading] = useState(true);
    const [payments, setPayments] = useState([]);
    const [returns, setReturns] = useState([]);
    const [pdfs, setPdfs] = useState([]);
    const [hasPendingReturn, setHasPendingReturn] = useState(false);

    const [activeTab, setActiveTab] = useState('items');

    const [showPaymentForm, setShowPaymentForm] = useState(false);
    const [showReturnForm, setShowReturnForm] = useState(false);
    const [showSavePDFModal, setShowSavePDFModal] = useState(false);
    const [showExtendDueDate, setShowExtendDueDate] = useState(false);
    const [formLoading, setFormLoading] = useState(false);
    const [dueDateSaving, setDueDateSaving] = useState(false);

    const [paymentApiError, setPaymentApiError] = useState(null);
    const [paymentFieldErrors, setPaymentFieldErrors] = useState({});
    const [pdfApiError, setPdfApiError] = useState(null);

    // Single confirm-dialog state, tagged with which action triggered it
    // (plus the target id for row-scoped actions like delete payment/PDF or
    // accept return) so one dialog instance can drive every confirmation.
    const [confirmAction, setConfirmAction] = useState(null);
    const [actionLoading, setActionLoading] = useState(false);

    // Per invoice-item shelf allocation UI state, keyed by invoice item id:
    // { candidates: [{id, name, available_quantity}], allocations: [{shelf_id, quantity}], error: string }
    const [shelfState, setShelfState] = useState({});
    // Bulk auto-allocate/save cover every item at once — one click each,
    // instead of per-item buttons. Editors stay fully editable either way.
    const [bulkAutoAllocating, setBulkAutoAllocating] = useState(false);
    const [bulkSaving, setBulkSaving] = useState(false);

    const fetchInvoiceCore = useCallback(async () => {
        const [invoiceData, summaryData] = await Promise.all([
            billingApi.invoices.getById(id),
            billingApi.invoices.getPaymentSummary(id),
        ]);
        setInvoice(invoiceData);
        setPaymentSummary(summaryData);

        if (invoiceData?.status === 'draft' && invoiceData.items?.length) {
            const entries = await Promise.all(invoiceData.items.map(async (item) => {
                try {
                    const candidates = await billingApi.shelves.getCandidates(item.product);
                    return [item.id, candidates?.results ?? candidates ?? []];
                } catch (err) {
                    console.error(`Failed to fetch candidate shelves for item ${item.id}:`, err);
                    return [item.id, []];
                }
            }));
            const candidatesByItemId = Object.fromEntries(entries);
            setShelfState((prev) => {
                const next = {};
                invoiceData.items.forEach((item) => {
                    next[item.id] = {
                        candidates: candidatesByItemId[item.id] || [],
                        allocations: (item.shelf_allocations || []).map((a) => ({
                            shelf_id: a.shelf_id,
                            quantity: a.quantity,
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
        return invoiceData;
    }, [id]);

    const refetchPayments = useCallback(async () => {
        try {
            const data = await billingApi.payments.getByInvoice(id, { page_size: 500 });
            setPayments(data?.results ?? data ?? []);
        } catch (err) {
            console.error('Failed to refresh payments:', err);
        }
    }, [id]);

    const refetchReturns = useCallback(async () => {
        try {
            const data = await billingApi.returns.getByInvoice(id, { page_size: 500 });
            const list = data?.results ?? data ?? [];
            setReturns(list);
            setHasPendingReturn(list.some((r) => r.status === 'pending'));
        } catch (err) {
            console.error('Failed to refresh returns:', err);
        }
    }, [id]);

    const refetchPDFs = useCallback(async (statusHint) => {
        const status = statusHint ?? invoice?.status;
        if (status === 'draft') return;
        try {
            const data = await billingApi.invoices.getPDFs(id);
            setPdfs(data?.results ?? data ?? []);
        } catch (err) {
            console.error('Failed to refresh saved PDFs:', err);
        }
    }, [id, invoice?.status]);

    const fetchSecondary = useCallback(async (invoiceData) => {
        setSecondaryLoading(true);
        try {
            await Promise.all([
                refetchPayments(),
                refetchReturns(),
                refetchPDFs(invoiceData?.status),
            ]);
        } finally {
            setSecondaryLoading(false);
        }
    }, [refetchPayments, refetchReturns, refetchPDFs]);

    const loadAll = useCallback(async () => {
        setLoading(true);
        setLoadError(null);
        try {
            const invoiceData = await fetchInvoiceCore();
            setLoading(false);
            await fetchSecondary(invoiceData);
        } catch (error) {
            console.error('Failed to fetch invoice details:', error);
            setLoadError(extractErrorMessage(error, 'Failed to load this invoice.'));
            setLoading(false);
        }
    }, [fetchInvoiceCore, fetchSecondary]);

    useEffect(() => {
        loadAll();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [id]);

    const handleAllocationChange = (itemId, nextAllocations) => {
        setShelfState((prev) => ({
            ...prev,
            [itemId]: { ...prev[itemId], allocations: nextAllocations },
        }));
    };

    // One click auto-allocates every item at once — fills only each item's
    // remaining gap, never touches rows already present (same rule
    // ShelfAllocationEditor's own per-item button follows).
    const handleAutoAllocateAll = async () => {
        if (!invoice?.items?.length) return;
        setBulkAutoAllocating(true);
        let failedCount = 0;
        await Promise.all(invoice.items.map(async (item) => {
            const state = shelfState[item.id] || { allocations: [] };
            const allocatedTotal = state.allocations.reduce((sum, a) => sum + (parseInt(a.quantity, 10) || 0), 0);
            const remaining = item.quantity - allocatedTotal;
            if (remaining <= 0) return;
            try {
                const excludeShelfIds = state.allocations.map((a) => a.shelf_id).filter(Boolean);
                const data = await billingApi.shelves.autoAllocate(item.product, remaining, excludeShelfIds);
                const newRows = (data?.allocations || []).map((a) => ({
                    shelf_id: a.shelf_id, quantity: a.quantity, shelf_name: a.shelf_name || '',
                }));
                if (newRows.length > 0) {
                    setShelfState((prev) => ({
                        ...prev,
                        [item.id]: { ...prev[item.id], allocations: [...(prev[item.id]?.allocations || []), ...newRows] },
                    }));
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
        if (!invoice?.items?.length) return;
        setBulkSaving(true);
        setShelfState((prev) => {
            const next = {};
            Object.keys(prev).forEach((id) => { next[id] = { ...prev[id], error: '' }; });
            return next;
        });
        let failedCount = 0;
        // Sequential, not Promise.all — each save is a real DB write, and
        // firing them concurrently against SQLite (single-writer) causes
        // "database is locked" 500s. One at a time is the correct fix
        // regardless of backend, not just a SQLite workaround.
        for (const item of invoice.items) {
            try {
                const allocations = (shelfState[item.id]?.allocations || [])
                    .filter((a) => a.shelf_id !== '' && a.quantity !== '')
                    .map((a) => ({ shelf_id: parseInt(a.shelf_id, 10), quantity: parseInt(a.quantity, 10) }));
                await billingApi.invoiceItems.setShelfAllocations(item.id, allocations);
            } catch (error) {
                console.error(`Failed to save shelf allocations for item ${item.id}:`, error);
                failedCount += 1;
                const message = extractErrorMessage(error, 'Failed to save shelf allocations.');
                setShelfState((prev) => ({
                    ...prev,
                    [item.id]: { ...prev[item.id], error: message },
                }));
            }
        }
        setBulkSaving(false);
        if (failedCount > 0) {
            toast.error(`Failed to save allocations for ${failedCount} item(s) — see details below.`);
        } else {
            toast.success('All shelf allocations saved.');
        }
        await fetchInvoiceCore();
    };

    const handlePrint = async () => {
        try {
            const isDraft = invoice?.status === 'draft';
            const blob = await billingApi.invoices.print(id, isDraft);
            const url = window.URL.createObjectURL(new Blob([blob], { type: 'application/pdf' }));
            const pdfWindow = window.open(url, '_blank');

            // Revoke only once the opened tab is closed — revoking on a fixed
            // short timeout breaks "Save As" inside the PDF viewer if the user
            // hasn't clicked it yet by then (the blob URL is already dead).
            if (pdfWindow) {
                const checkClosed = setInterval(() => {
                    if (pdfWindow.closed) {
                        clearInterval(checkClosed);
                        window.URL.revokeObjectURL(url);
                    }
                }, 1000);
            } else {
                window.URL.revokeObjectURL(url);
            }
        } catch (error) {
            console.error('Failed to print:', error);
            toast.error(extractErrorMessage(error, 'Failed to print invoice. Please try again.'));
        }
    };

    const handleSavePDF = async (fileName) => {
        setFormLoading(true);
        setPdfApiError(null);
        try {
            await billingApi.invoices.savePDF(id, { file_name: fileName });
            setShowSavePDFModal(false);
            toast.success('PDF saved successfully.');
            await refetchPDFs();
        } catch (error) {
            console.error('Failed to save PDF:', error);
            setPdfApiError(extractErrorMessage(error, 'Failed to save PDF.'));
        } finally {
            setFormLoading(false);
        }
    };

    const handleDeletePDF = async (pdfId) => {
        setActionLoading(true);
        try {
            await billingApi.invoices.deletePDF(pdfId);
            setConfirmAction(null);
            toast.success('PDF deleted.');
            await refetchPDFs();
        } catch (error) {
            console.error('Failed to delete PDF:', error);
            toast.error(extractErrorMessage(error, 'Failed to delete PDF.'));
        } finally {
            setActionLoading(false);
        }
    };

    const handleRecordPayment = async (data) => {
        setFormLoading(true);
        setPaymentApiError(null);
        setPaymentFieldErrors({});
        try {
            await billingApi.payments.create(id, data);
            setShowPaymentForm(false);
            toast.success('Payment recorded successfully.');
            await Promise.all([fetchInvoiceCore(), refetchPayments()]);
        } catch (error) {
            console.error('Failed to record payment:', error);
            const errData = error?.response?.data;
            const asMsg = (v) => (Array.isArray(v) ? v[0] : v);
            if (errData && typeof errData === 'object' && (errData.amount || errData.method_allocations || errData.splits)) {
                setPaymentFieldErrors({
                    amount: asMsg(errData.amount),
                    method_allocations: asMsg(errData.method_allocations || errData.splits),
                });
            } else {
                setPaymentApiError(extractErrorMessage(error, 'Failed to record payment.'));
            }
        } finally {
            setFormLoading(false);
        }
    };

    const handleDeletePayment = async (paymentId) => {
        setActionLoading(true);
        try {
            await billingApi.payments.delete(paymentId);
            setConfirmAction(null);
            toast.success('Payment deleted.');
            await Promise.all([fetchInvoiceCore(), refetchPayments()]);
        } catch (error) {
            console.error('Failed to delete payment:', error);
            toast.error(extractErrorMessage(error, 'Failed to delete payment.'));
        } finally {
            setActionLoading(false);
        }
    };

    const handleCreateReturn = async (data) => {
        setFormLoading(true);
        try {
            await billingApi.returns.create(id, data);
            setShowReturnForm(false);
            toast.success('Return created successfully.');
            await Promise.all([fetchInvoiceCore(), refetchReturns()]);
        } catch (error) {
            console.error('Failed to create return:', error);
            toast.error(extractErrorMessage(error, 'Failed to create return.'));
        } finally {
            setFormLoading(false);
        }
    };

    const handleAcceptReturn = async (returnId) => {
        setActionLoading(true);
        try {
            await billingApi.returns.accept(returnId);
            setConfirmAction(null);
            toast.success('Return accepted.');
            await Promise.all([fetchInvoiceCore(), refetchReturns()]);
        } catch (error) {
            console.error('Failed to accept return:', error);
            // Shelf put-away can only be edited on the return's own detail
            // page (ReturnList here is a compact summary widget with no
            // room for the allocator UI), so point the user there when
            // acceptance is blocked on incomplete allocations.
            toast.error(
                `${extractErrorMessage(error, 'Failed to accept return.')} Open the return's detail page to allocate shelves.`
            );
        } finally {
            setActionLoading(false);
        }
    };

    const handleConfirmInvoice = async () => {
        setActionLoading(true);
        try {
            await billingApi.invoices.confirm(id);
            setConfirmAction(null);
            toast.success('Invoice confirmed successfully.');
            await fetchInvoiceCore();
        } catch (error) {
            console.error('Failed to confirm invoice:', error);
            toast.error(extractErrorMessage(error, 'Failed to confirm invoice.'));
        } finally {
            setActionLoading(false);
        }
    };

    const handleDeleteInvoice = async () => {
        setActionLoading(true);
        try {
            await billingApi.invoices.delete(id);
            toast.success('Draft invoice deleted.');
            navigate('/billing/invoices');
        } catch (error) {
            console.error('Failed to delete invoice:', error);
            toast.error(extractErrorMessage(error, 'Failed to delete invoice.'));
            setActionLoading(false);
        }
    };

    const handleSaveDueDate = async (newDueDate) => {
        setDueDateSaving(true);
        try {
            await billingApi.invoices.updateDueDate(id, newDueDate);
            setShowExtendDueDate(false);
            toast.success('Due date updated.');
            await fetchInvoiceCore();
        } finally {
            setDueDateSaving(false);
        }
    };

    const runConfirmedAction = () => {
        if (!confirmAction) return;
        switch (confirmAction.type) {
            case 'deleteInvoice': return handleDeleteInvoice();
            case 'confirmInvoice': return handleConfirmInvoice();
            case 'deletePayment': return handleDeletePayment(confirmAction.id);
            case 'deletePDF': return handleDeletePDF(confirmAction.id);
            case 'acceptReturn': return handleAcceptReturn(confirmAction.id);
            default: return undefined;
        }
    };

    const deleteInvoiceMessage = invoice?.payment_type === 'advance' && amount(invoice?.advance_amount) > 0
        ? `Delete draft invoice ${invoice.bill_number}? This invoice has an advance payment of PKR ${amount(invoice.advance_amount).toFixed(2)} — deleting it will refund this amount by removing it from cash-in-hand. This action cannot be undone.`
        : `Delete draft invoice ${invoice?.bill_number}? This action cannot be undone.`;

    const confirmDialogProps = confirmAction ? {
        ...CONFIRM_CONFIG[confirmAction.type],
        message: confirmAction.type === 'deleteInvoice'
            ? deleteInvoiceMessage
            : confirmAction.type === 'confirmInvoice'
                ? `Confirm invoice ${invoice?.bill_number}? This finalises pricing, reserves stock, and cannot be undone.`
                : CONFIRM_CONFIG[confirmAction.type].message,
    } : {};

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    if (!invoice) {
        return (
            <div className="text-center py-12 space-y-4">
                <h2 className="text-2xl font-semibold text-neutral-900">Invoice Not Found</h2>
                {loadError && (
                    <div className="max-w-md mx-auto">
                        <InlineAlert variant="error" message={loadError} onRetry={loadAll} />
                    </div>
                )}
                <BackLink to="/billing/invoices" className="mt-4">Back to Invoices</BackLink>
            </div>
        );
    }

    const isDraft = invoice.status === 'draft';
    const canManage = !isDraft && isAdmin;

    const tabs = [
        { value: 'items', label: 'Items', count: invoice.items?.length ?? 0 },
        ...(isAdmin ? [{ value: 'payments', label: 'Payments', count: payments.length }] : []),
        { value: 'returns', label: 'Returns', count: returns.length },
        ...(isAdmin ? [{ value: 'pdfs', label: 'Saved PDFs', count: pdfs.length }] : []),
    ];

    const itemsTable = (
        <div className="overflow-x-auto -mx-4 sm:mx-0">
            <table className="w-full min-w-[640px]">
                <thead>
                    <tr className="border-b border-neutral-200">
                        <th className="px-3 py-2 text-left text-xs font-medium text-neutral-500">Product</th>
                        <th className="px-3 py-2 text-left text-xs font-medium text-neutral-500">Qty</th>
                        <th className="px-3 py-2 text-left text-xs font-medium text-neutral-500">Discount</th>
                        <th className="px-3 py-2 text-left text-xs font-medium text-neutral-500">GST%</th>
                        <th className="px-3 py-2 text-left text-xs font-medium text-neutral-500">WHT%</th>
                        <th className="px-3 py-2 text-right text-xs font-medium text-neutral-500">Effective Price</th>
                        <th className="px-3 py-2 text-right text-xs font-medium text-neutral-500">Total</th>
                        {/* Cost/profit — admin & superuser only, and only meaningful once
                            confirmed (these are computed at confirmation, still 0 on a draft). */}
                        {isAdmin && !isDraft && (
                            <>
                                <th className="px-3 py-2 text-right text-xs font-medium text-neutral-500">COGS</th>
                                <th className="px-3 py-2 text-right text-xs font-medium text-neutral-500">Profit</th>
                            </>
                        )}
                    </tr>
                </thead>
                <tbody className="divide-y divide-neutral-100">
                    {invoice.items?.map((item, index) => (
                        <tr key={item.id || index} className="hover:bg-neutral-50">
                            <td className="px-3 py-2 text-sm">
                                <p>{item.product_name || 'N/A'}</p>
                                {item.shelf_allocations?.length > 0 ? (
                                    <p className="text-xs text-neutral-500 mt-0.5">
                                        Shelf: {item.shelf_allocations.map((a) => `${a.shelf_name} (${a.quantity})`).join(', ')}
                                    </p>
                                ) : !isDraft && (
                                    <p className="text-xs text-neutral-400 mt-0.5 italic">No shelf allocation</p>
                                )}
                            </td>
                            <td className="px-3 py-2 text-sm">{item.quantity}</td>
                            <td className="px-3 py-2 text-sm">{item.discount || 0}</td>
                            <td className="px-3 py-2 text-sm">{item.gst || 0}%</td>
                            <td className="px-3 py-2 text-sm">{item.wht || 0}%</td>
                            <td className="px-3 py-2 text-sm text-right tabular-nums">
                                {item.effective_price ? parseFloat(item.effective_price).toFixed(2) : '0.00'}
                            </td>
                            <td className="px-3 py-2 text-sm text-right font-medium tabular-nums">
                                {item.line_total ? parseFloat(item.line_total).toFixed(2) : '0.00'}
                            </td>
                            {isAdmin && !isDraft && (
                                <>
                                    <td className="px-3 py-2 text-sm text-right tabular-nums text-neutral-600">
                                        {item.line_cogs ? parseFloat(item.line_cogs).toFixed(2) : '0.00'}
                                    </td>
                                    <td className="px-3 py-2 text-sm text-right font-medium tabular-nums text-success-600">
                                        {item.line_profit ? parseFloat(item.line_profit).toFixed(2) : '0.00'}
                                    </td>
                                </>
                            )}
                        </tr>
                    ))}
                </tbody>
                <tfoot className="border-t border-neutral-200">
                    <tr>
                        <td colSpan={isAdmin && !isDraft ? 8 : 6} className="px-3 py-2 text-right font-medium">Subtotal:</td>
                        <td className="px-3 py-2 text-right font-medium tabular-nums">
                            {invoice.subtotal ? parseFloat(invoice.subtotal).toFixed(2) : '0.00'}
                        </td>
                    </tr>
                    <tr>
                        <td colSpan={isAdmin && !isDraft ? 8 : 6} className="px-3 py-2 text-right font-medium">GST Total:</td>
                        <td className="px-3 py-2 text-right font-medium tabular-nums">
                            {invoice.gst_total ? parseFloat(invoice.gst_total).toFixed(2) : '0.00'}
                        </td>
                    </tr>
                    <tr>
                        <td colSpan={isAdmin && !isDraft ? 8 : 6} className="px-3 py-2 text-right font-medium">WHT Total:</td>
                        <td className="px-3 py-2 text-right font-medium tabular-nums">
                            {invoice.wht_total ? parseFloat(invoice.wht_total).toFixed(2) : '0.00'}
                        </td>
                    </tr>
                    <tr className="text-lg">
                        <td colSpan={isAdmin && !isDraft ? 8 : 6} className="px-3 py-2 text-right font-bold">Grand Total:</td>
                        <td className="px-3 py-2 text-right font-bold text-primary-600 tabular-nums">
                            {invoice.grand_total ? parseFloat(invoice.grand_total).toFixed(2) : '0.00'}
                        </td>
                    </tr>
                    {isAdmin && !isDraft && (
                        <>
                            <tr>
                                <td colSpan={8} className="px-3 py-2 text-right font-medium text-neutral-600">Total COGS:</td>
                                <td className="px-3 py-2 text-right font-medium tabular-nums text-neutral-600">
                                    {invoice.total_cogs ? parseFloat(invoice.total_cogs).toFixed(2) : '0.00'}
                                </td>
                            </tr>
                            <tr className="text-lg">
                                <td colSpan={8} className="px-3 py-2 text-right font-bold text-success-700">Gross Profit:</td>
                                <td className="px-3 py-2 text-right font-bold text-success-700 tabular-nums">
                                    {invoice.gross_profit ? parseFloat(invoice.gross_profit).toFixed(2) : '0.00'}
                                </td>
                            </tr>
                        </>
                    )}
                </tfoot>
            </table>
        </div>
    );

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                <div>
                    <BackLink to="/billing/invoices">Back to Invoices</BackLink>
                    <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900 mt-2">{invoice.bill_number}</h1>
                    <p className="text-sm text-neutral-500 mt-0.5">{invoice.customer?.name || 'N/A'}</p>
                    <div className="flex gap-2 mt-2 flex-wrap">
                        <InvoiceStatusBadge status={invoice.status} />
                        <PaymentStatusBadge status={invoice.payment_status} />
                        {hasPendingReturn && <Badge variant="warning">Return Pending</Badge>}
                    </div>
                </div>
                <div className="flex gap-2 flex-wrap sm:justify-end">
                    {!isDraft && (
                        <Button variant="secondary" icon={Printer} onClick={handlePrint}>
                            Print
                        </Button>
                    )}
                    <Button variant="secondary" icon={Smartphone} onClick={() => navigate(`/billing/invoices/${id}/preview`)}>
                        Preview
                    </Button>

                    {canManage && (
                        <>
                            <Button variant="secondary" icon={Save} onClick={() => { setPdfApiError(null); setShowSavePDFModal(true); }}>
                                Save PDF
                            </Button>
                            <Button variant="secondary" icon={CreditCard} onClick={() => { setPaymentApiError(null); setPaymentFieldErrors({}); setShowPaymentForm(true); }}>
                                Record Payment
                            </Button>
                            {!hasPendingReturn && invoice.status !== 'returned' && (
                                <Button variant="secondary" icon={RotateCcw} onClick={() => setShowReturnForm(true)}>
                                    Create Return
                                </Button>
                            )}
                        </>
                    )}

                    {!isDraft && invoice.payment_status !== 'paid' && isAdmin && (
                        <Button variant="secondary" icon={CalendarClock} onClick={() => setShowExtendDueDate(true)}>
                            Extend Due Date
                        </Button>
                    )}

                    {isDraft && (
                        <>
                            <Button variant="secondary" icon={Pencil} onClick={() => navigate(`/billing/invoices/${id}/edit`)}>
                                Edit
                            </Button>
                            {isAdmin && (
                                <Button variant="success" icon={CheckCircle2} onClick={() => setConfirmAction({ type: 'confirmInvoice' })}>
                                    Confirm
                                </Button>
                            )}
                            <Button variant="danger" icon={Trash2} onClick={() => setConfirmAction({ type: 'deleteInvoice' })}>
                                Delete
                            </Button>
                        </>
                    )}
                </div>
            </div>

            {/* Key details */}
            <Card className="p-6">
                <h3 className="font-semibold text-neutral-900 mb-3 flex items-center gap-2">
                    <Package className="w-4 h-4 text-neutral-400" />
                    Customer Information
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div>
                        <p className="text-sm text-neutral-500">Name</p>
                        <p className="font-medium">{invoice.customer?.name || 'N/A'}</p>
                    </div>
                    <div>
                        <p className="text-sm text-neutral-500">Code</p>
                        <p className="font-medium">{invoice.customer?.code || 'N/A'}</p>
                    </div>
                    <div>
                        <p className="text-sm text-neutral-500">Address</p>
                        <p className="font-medium">{invoice.customer?.address || 'N/A'}</p>
                    </div>
                    <div>
                        <p className="text-sm text-neutral-500">Mobile</p>
                        <p className="font-medium">{invoice.customer?.mobile || 'N/A'}</p>
                    </div>
                    {invoice.customer?.credit_score != null && (
                        <div>
                            <p className="text-sm text-neutral-500">Credit Score</p>
                            <p className={`font-medium ${creditScoreColorClass(invoice.customer.credit_tier)}`}>
                                {invoice.customer.credit_score}
                            </p>
                        </div>
                    )}
                    {invoice.payment_type === 'advance' && amount(invoice.advance_amount) > 0 && (
                        <div>
                            <p className="text-sm text-neutral-500">Advance Amount (PKR)</p>
                            <p className="font-medium">{amount(invoice.advance_amount).toFixed(2)}</p>
                        </div>
                    )}
                    {invoice.payment_due_date && (
                        <div>
                            <p className="text-sm text-neutral-500">Due Date</p>
                            <p className="font-medium">{new Date(invoice.payment_due_date).toLocaleDateString()}</p>
                        </div>
                    )}
                </div>
            </Card>

            {/* Payment Summary */}
            {paymentSummary && !isDraft && (
                <PaymentSummaryCard summary={paymentSummary} />
            )}

            {isDraft ? (
                <>
                    {/* Items */}
                    <Card className="p-6">
                        <h3 className="font-semibold text-neutral-900 mb-3">Items</h3>
                        {itemsTable}
                    </Card>

                    {/* Shelf Allocation - editable while draft */}
                    <Card className="p-6">
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
                                    onClick={handleSaveAllocationsAll}
                                    loading={bulkSaving}
                                    disabled={bulkAutoAllocating}
                                >
                                    Save All Allocations
                                </Button>
                            </div>
                        </div>
                        <div className="space-y-4">
                            {invoice.items?.map((item) => {
                                const state = shelfState[item.id] || {
                                    candidates: [], allocations: [], error: '',
                                };
                                return (
                                    <div key={item.id} className="border border-neutral-200 rounded-xl p-4">
                                        <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
                                            <div>
                                                <p className="font-medium">
                                                    {item.product_name}{' '}
                                                    <span className="text-neutral-400 text-sm">({item.product_code})</span>
                                                </p>
                                                <p className="text-xs text-neutral-500">
                                                    Quantity: {item.quantity} • Allocated: {item.allocated_quantity}
                                                </p>
                                            </div>
                                        </div>
                                        <ShelfAllocationEditor
                                            value={state.allocations}
                                            onChange={(next) => handleAllocationChange(item.id, next)}
                                            shelves={state.candidates}
                                            requiredQuantity={item.quantity}
                                            mode="consumption"
                                            disabled={bulkSaving || bulkAutoAllocating}
                                            productId={item.product}
                                            autoAllocateApi={billingApi.shelves.autoAllocate}
                                        />
                                        {state.error && (
                                            <p className="text-sm text-error-600 mt-2">{state.error}</p>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    </Card>

                    {/* Draft Preview */}
                    {invoice.draft_preview && <DraftPreviewPanel preview={invoice.draft_preview} />}
                </>
            ) : (
                <Card className="p-0 overflow-hidden" hover={false}>
                    <div className="px-4 sm:px-6 pt-4">
                        <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />
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

                                {activeTab === 'payments' && isAdmin && (
                                    secondaryLoading
                                        ? <LoadingSpinner />
                                        : (
                                            <PaymentHistoryList
                                                payments={payments}
                                                onDelete={(paymentId) => setConfirmAction({ type: 'deletePayment', id: paymentId })}
                                                isAdmin={isAdmin}
                                            />
                                        )
                                )}

                                {activeTab === 'returns' && (
                                    secondaryLoading
                                        ? <LoadingSpinner />
                                        : (
                                            <ReturnList
                                                returns={returns}
                                                onAccept={(returnId) => setConfirmAction({ type: 'acceptReturn', id: returnId })}
                                                isAdmin={isAdmin}
                                            />
                                        )
                                )}

                                {activeTab === 'pdfs' && isAdmin && (
                                    secondaryLoading ? (
                                        <LoadingSpinner />
                                    ) : pdfs.length === 0 ? (
                                        <EmptyState
                                            icon={<FileText className="w-10 h-10 text-neutral-300" />}
                                            title="No saved PDFs yet"
                                            description="PDFs you save for this invoice will appear here."
                                        />
                                    ) : (
                                        <div className="space-y-2">
                                            {pdfs.map((pdf) => (
                                                <div key={pdf.id} className="flex justify-between items-center gap-3 p-3 bg-neutral-50 rounded-xl hover:bg-neutral-100 transition-colors">
                                                    <div className="min-w-0">
                                                        <a
                                                            href={pdf.file_url}
                                                            target="_blank"
                                                            rel="noopener noreferrer"
                                                            className="font-medium text-primary-600 hover:text-primary-700 hover:underline inline-flex items-center gap-1.5 break-all"
                                                        >
                                                            {pdf.file_name}
                                                            <ExternalLink className="w-3.5 h-3.5 flex-shrink-0" />
                                                        </a>
                                                        <p className="text-xs text-neutral-500">
                                                            Saved: {new Date(pdf.created_at).toLocaleString()}
                                                        </p>
                                                    </div>
                                                    <Button
                                                        size="sm"
                                                        variant="danger"
                                                        icon={Trash2}
                                                        onClick={() => setConfirmAction({ type: 'deletePDF', id: pdf.id })}
                                                    >
                                                        <span className="hidden sm:inline">Delete</span>
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
                    maxAmount={paymentSummary?.credit_outstanding ? parseFloat(paymentSummary.credit_outstanding) : undefined}
                    apiError={paymentApiError}
                    apiErrors={paymentFieldErrors}
                    onDismissApiError={() => { setPaymentApiError(null); setPaymentFieldErrors({}); }}
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
                    orderItems={invoice.items || []}
                />
            </Modal>

            {/* Save PDF Modal */}
            <SavePDFModal
                isOpen={showSavePDFModal}
                onClose={() => setShowSavePDFModal(false)}
                onSubmit={handleSavePDF}
                loading={formLoading}
                defaultFileName={invoice.bill_number}
                error={pdfApiError}
            />

            {/* Extend Due Date Modal */}
            <ExtendDueDateModal
                isOpen={showExtendDueDate}
                onClose={() => setShowExtendDueDate(false)}
                onSubmit={handleSaveDueDate}
                currentDueDate={invoice.payment_due_date}
                loading={dueDateSaving}
            />

            {/* Shared confirmation dialog for every destructive/high-stakes action */}
            <ConfirmDialog
                isOpen={!!confirmAction}
                onClose={() => { if (!actionLoading) setConfirmAction(null); }}
                onConfirm={runConfirmedAction}
                loading={actionLoading}
                {...confirmDialogProps}
            />
        </div>
    );
};

export default InvoiceDetailPage;
