import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { billingApi } from '../../services/billingApi';
import { extractErrorMessage } from '../../utils/errorMessage';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import InlineAlert from '../../components/ui/InlineAlert';

const COMPANY_NAME = import.meta.env.VITE_APP_NAME;

// Mirrors backend/billing/pdf_service.py's grand_total_display/
// effective_price_display/line_total_display exactly: {:,.4f}, with the
// same "N/A" fallback for a draft line item that can't be priced yet
// (missing rate) — see billing/utils.py's get_invoice_print_context.
const fmtAmount = (value) => {
    if (value === null || value === undefined) return 'N/A';
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    if (isNaN(num)) return 'N/A';
    return num.toLocaleString('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 4 });
};

// Mirrors pdf_service.py's strftime("%d %b %Y") — e.g. "17 Aug 2026".
const fmtDate = (value) => {
    if (!value) return '';
    return new Date(value).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
};

const InvoicePreviewPage = () => {
    const { id } = useParams();
    const navigate = useNavigate();

    const [invoice, setInvoice] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchInvoice = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await billingApi.invoices.getById(id);
            setInvoice(data);
        } catch (err) {
            setError(extractErrorMessage(err, 'Failed to load invoice'));
            setInvoice(null);
        } finally {
            setLoading(false);
        }
    }, [id]);

    useEffect(() => {
        fetchInvoice();
    }, [fetchInvoice]);

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-neutral-100">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    if (error || !invoice) {
        return (
            <div className="min-h-screen flex flex-col items-center justify-center bg-neutral-100 p-4 gap-4">
                <InlineAlert variant="error" message={error || 'Invoice not found'} onRetry={fetchInvoice} />
                <button onClick={() => navigate(-1)} className="text-sm text-primary-600 font-medium">
                    Go back
                </button>
            </div>
        );
    }

    const isDraft = invoice.status === 'draft';
    const invoiceDate = invoice.confirmed_at || invoice.created_at;

    // Drafts don't have real stored effective_price/line_total/grand_total
    // yet (only set at confirmation) — print_preview computes the exact
    // same numbers the printed PDF would show for this draft (discount/GST/
    // WHT included), NOT draft_preview, which is a different pre-tax figure
    // meant for staff profit-margin eyeballing elsewhere in the app.
    const previewItems = isDraft ? (invoice.print_preview?.items ?? []) : (invoice.items ?? []);
    const grandTotal = isDraft ? invoice.print_preview?.grand_total : invoice.grand_total;

    return (
        <div className="min-h-screen bg-neutral-200">
            {/* Minimal chrome — no sidebar/topbar, deliberately, so a phone
                screenshot captures only the invoice itself. See App.jsx: this
                route skips <Layout> on purpose (approved exception to the
                "every route uses Layout" rule — this page is a share/screenshot
                surface, not app navigation). */}
            <div className="sticky top-0 z-10 bg-white border-b border-neutral-200 px-3 py-2.5 flex items-center gap-2 no-print">
                <button
                    onClick={() => navigate(-1)}
                    className="p-1.5 -ml-1.5 rounded-lg text-neutral-600 hover:bg-neutral-100"
                    aria-label="Back"
                >
                    <ArrowLeft className="w-5 h-5" />
                </button>
                <span className="text-sm font-medium text-neutral-700">Invoice Preview</span>
            </div>

            <div className="max-w-md mx-auto p-2.5">
                <div className="bg-white rounded-lg shadow-sm border border-neutral-200 p-3.5 relative overflow-hidden">
                    {isDraft && (
                        <div
                            className="absolute inset-0 flex items-center justify-center pointer-events-none select-none z-0"
                            style={{ transform: 'rotate(-30deg)' }}
                        >
                            <span className="text-[64px] font-black text-error-600/10 whitespace-nowrap">DRAFT</span>
                        </div>
                    )}

                    <div className="relative z-[1]">
                        {/* Header */}
                        <div className="flex items-start justify-between gap-2 border-b-2 border-neutral-900 pb-2.5 mb-3">
                            <div>
                                <img src="/logo.svg" alt={COMPANY_NAME} className="h-8 max-w-[110px] object-contain object-left" />
                            </div>
                            <div className="flex-1 text-center">
                                <p className="text-sm font-black tracking-wide text-neutral-900">{COMPANY_NAME}</p>
                                <p className="text-[10px] text-neutral-500 mt-0.5">Official Invoice</p>
                            </div>
                            <div className="text-right">
                                <h2 className={`text-lg font-bold ${isDraft ? 'text-error-600' : 'text-neutral-900'}`}>
                                    {isDraft ? 'DRAFT INVOICE' : 'INVOICE'}
                                </h2>
                                <p className="text-xs font-semibold text-neutral-900 mt-0.5">{invoice.bill_number}</p>
                                <p className="text-[10px] text-neutral-500">Date: {fmtDate(invoiceDate)}</p>
                            </div>
                        </div>

                        {/* Bill To */}
                        <div className="mb-3 text-xs leading-relaxed">
                            <span className="uppercase text-neutral-400 tracking-wide text-[10px] mr-2">Bill To:</span>
                            <span className="font-medium text-neutral-900">{invoice.customer?.name}</span>
                            <span className="text-neutral-600"> · Code: {invoice.customer?.code}</span>
                            <span className="text-neutral-600"> · Address: {invoice.customer?.address}</span>
                            {invoice.customer?.mobile && (
                                <span className="text-neutral-600"> · Mobile: {invoice.customer.mobile}</span>
                            )}
                        </div>

                        {/* Items */}
                        <table className="w-full text-xs border-collapse mb-3">
                            <thead>
                                <tr className="bg-neutral-900 text-white">
                                    <th className="py-1.5 px-1.5 text-left font-semibold uppercase text-[9px] tracking-wide">#</th>
                                    <th className="py-1.5 px-1.5 text-left font-semibold uppercase text-[9px] tracking-wide">Product</th>
                                    <th className="py-1.5 px-1.5 text-left font-semibold uppercase text-[9px] tracking-wide">Code</th>
                                    <th className="py-1.5 px-1.5 text-right font-semibold uppercase text-[9px] tracking-wide">Price</th>
                                    <th className="py-1.5 px-1.5 text-center font-semibold uppercase text-[9px] tracking-wide">Qty</th>
                                    <th className="py-1.5 px-1.5 text-right font-semibold uppercase text-[9px] tracking-wide">Total</th>
                                </tr>
                            </thead>
                            <tbody>
                                {previewItems.map((item, idx) => (
                                    <tr key={item.id ?? idx} className={`border-b border-neutral-100 ${idx % 2 === 1 ? 'bg-neutral-50' : ''}`}>
                                        <td className="py-1.5 px-1.5 text-neutral-700">{idx + 1}</td>
                                        <td className="py-1.5 px-1.5 text-neutral-900">{item.product_name}</td>
                                        <td className="py-1.5 px-1.5 text-neutral-600">{item.product_code}</td>
                                        <td className="py-1.5 px-1.5 text-right text-neutral-900">{fmtAmount(item.effective_price)}</td>
                                        <td className="py-1.5 px-1.5 text-center text-neutral-900">{item.quantity}</td>
                                        <td className="py-1.5 px-1.5 text-right text-neutral-900 font-medium">{fmtAmount(item.line_total)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>

                        {/* Grand Total only — matches the printed PDF exactly:
                            no subtotal/tax breakdown, no payment status, no
                            advance/due-date, no notes. */}
                        <div className="flex justify-end">
                            <div className="w-full max-w-[200px] rounded border border-neutral-200 overflow-hidden">
                                <div className="flex justify-between items-center bg-neutral-900 px-3 py-2">
                                    <span className="text-white text-xs font-semibold">Grand Total</span>
                                    <span className="text-white text-sm font-bold">Rs. {fmtAmount(grandTotal)}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default InvoicePreviewPage;
