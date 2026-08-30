import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useAuth } from '../../context/AuthContext';
import { billingApi } from '../../services/billingApi';
import { useInvoiceDetail } from '../../hooks/useBilling';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Badge from '../../components/ui/Badge';
import InvoiceStatusBadge from '../../components/billing/InvoiceStatusBadge';
import PaymentStatusBadge from '../../components/billing/PaymentStatusBadge';
import PaymentSummaryCard from '../../components/billing/PaymentSummaryCard';
import PaymentHistoryList from '../../components/billing/PaymentHistoryList';
import PaymentForm from '../../components/billing/PaymentForm';
import ReturnList from '../../components/billing/ReturnList';
import ReturnForm from '../../components/billing/ReturnForm';
import SavePDFModal from '../../components/billing/SavePDFModal';
import Modal from '../../components/ui/Modal';

const InvoiceDetailPage = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const { user } = useAuth();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const { invoice, paymentSummary, loading, refetch } = useInvoiceDetail(id);

    const [showPaymentForm, setShowPaymentForm] = useState(false);
    const [showReturnForm, setShowReturnForm] = useState(false);
    const [showSavePDFModal, setShowSavePDFModal] = useState(false);
    const [formLoading, setFormLoading] = useState(false);
    const [pdfs, setPdfs] = useState([]);
    const [returns, setReturns] = useState([]);
    const [payments, setPayments] = useState([]);

    useEffect(() => {
        if (invoice) {
            fetchAdditionalData();
        }
    }, [invoice]);

    const fetchAdditionalData = async () => {
        try {
            const [paymentsData, returnsData, pdfsData] = await Promise.all([
                billingApi.payments.getByInvoice(id, { page_size: 500 }),
                billingApi.returns.getByInvoice(id, { page_size: 500 }),
                invoice.status === 'confirmed' ? billingApi.invoices.getPDFs(id) : Promise.resolve([]),
            ]);
            setPayments(paymentsData?.results ?? paymentsData ?? []);
            setReturns(returnsData?.results ?? returnsData ?? []);
            setPdfs(pdfsData || []);
        } catch (error) {
            console.error('Failed to fetch additional data:', error);
        }
    };

    const handlePrint = () => {
        const isDraft = invoice?.status === 'draft';
        window.open(`/api/billing/invoices/${id}/print/?is_draft=${isDraft}`, '_blank');
    };

    const handleSavePDF = async (fileName) => {
        setFormLoading(true);
        try {
            await billingApi.invoices.savePDF(id, { file_name: fileName });
            setShowSavePDFModal(false);
            await fetchAdditionalData();
        } catch (error) {
            console.error('Failed to save PDF:', error);
        } finally {
            setFormLoading(false);
        }
    };

    const handleDeletePDF = async (pdfId) => {
        if (!window.confirm('Are you sure you want to delete this PDF?')) return;
        try {
            await billingApi.invoices.deletePDF(pdfId);
            await fetchAdditionalData();
        } catch (error) {
            console.error('Failed to delete PDF:', error);
        }
    };

    const handleRecordPayment = async (data) => {
        setFormLoading(true);
        try {
            await billingApi.payments.create(id, data);
            setShowPaymentForm(false);
            await refetch();
            await fetchAdditionalData();
        } catch (error) {
            console.error('Failed to record payment:', error);
            alert(error.response?.data?.detail || 'Failed to record payment');
        } finally {
            setFormLoading(false);
        }
    };

    const handleDeletePayment = async (paymentId) => {
        if (!window.confirm('Are you sure you want to delete this payment?')) return;
        try {
            await billingApi.payments.delete(paymentId);
            await refetch();
            await fetchAdditionalData();
        } catch (error) {
            console.error('Failed to delete payment:', error);
        }
    };

    const handleCreateReturn = async (data) => {
        setFormLoading(true);
        try {
            await billingApi.returns.create(id, data);
            setShowReturnForm(false);
            await fetchAdditionalData();
        } catch (error) {
            console.error('Failed to create return:', error);
            alert(error.response?.data?.detail || 'Failed to create return');
        } finally {
            setFormLoading(false);
        }
    };

    const handleAcceptReturn = async (returnId) => {
        if (!window.confirm('Are you sure you want to accept this return?')) return;
        try {
            await billingApi.returns.accept(returnId);
            await refetch();
            await fetchAdditionalData();
        } catch (error) {
            console.error('Failed to accept return:', error);
        }
    };

    const handleConfirmInvoice = async () => {
        if (!window.confirm('Are you sure you want to confirm this invoice?')) return;
        try {
            await billingApi.invoices.confirm(id);
            await refetch();
            await fetchAdditionalData();
        } catch (error) {
            console.error('Failed to confirm invoice:', error);
        }
    };

    const handleDeleteInvoice = async () => {
        if (!window.confirm('Are you sure you want to delete this draft invoice?')) return;
        try {
            await billingApi.invoices.delete(id);
            navigate('/billing/invoices');
        } catch (error) {
            console.error('Failed to delete invoice:', error);
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    if (!invoice) {
        return (
            <div className="text-center py-12">
                <h2 className="text-2xl font-semibold text-neutral-900">Invoice Not Found</h2>
                <Link to="/billing/invoices" className="text-primary-600 hover:text-primary-700 mt-4 inline-block">
                    ← Back to Invoices
                </Link>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <Link to="/billing/invoices" className="text-sm text-primary-600 hover:text-primary-700">
                        ← Back to Invoices
                    </Link>
                    <h1 className="text-3xl font-bold text-neutral-900 mt-1">{invoice.bill_number}</h1>
                    <div className="flex gap-2 mt-1">
                        <InvoiceStatusBadge status={invoice.status} />
                        <PaymentStatusBadge status={invoice.payment_status} />
                    </div>
                </div>
                <div className="flex gap-2 flex-wrap">
                    <Button variant="secondary" onClick={handlePrint}>
                        Print
                    </Button>

                    {invoice.status === 'confirmed' && isAdmin && (
                        <>
                            <Button variant="secondary" onClick={() => setShowSavePDFModal(true)}>
                                Save PDF
                            </Button>
                            <Button variant="secondary" onClick={() => setShowPaymentForm(true)}>
                                Record Payment
                            </Button>
                            <Button variant="secondary" onClick={() => setShowReturnForm(true)}>
                                Create Return
                            </Button>
                        </>
                    )}

                    {invoice.status === 'draft' && (
                        <>
                            <Button variant="secondary" onClick={() => navigate(`/billing/invoices/${id}/edit`)}>
                                Edit
                            </Button>
                            {isAdmin && (
                                <Button variant="success" onClick={handleConfirmInvoice}>
                                    Confirm
                                </Button>
                            )}
                            <Button variant="danger" onClick={handleDeleteInvoice}>
                                Delete
                            </Button>
                        </>
                    )}
                </div>
            </div>

            {/* Customer Info */}
            <Card className="p-6">
                <h3 className="font-semibold text-neutral-900 mb-3">Customer Information</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div>
                        <p className="text-sm text-neutral-500">Name</p>
                        <p className="font-medium">{invoice.customer?.name}</p>
                    </div>
                    <div>
                        <p className="text-sm text-neutral-500">Code</p>
                        <p className="font-medium">{invoice.customer?.code}</p>
                    </div>
                    <div>
                        <p className="text-sm text-neutral-500">Address</p>
                        <p className="font-medium">{invoice.customer?.address}</p>
                    </div>
                    <div>
                        <p className="text-sm text-neutral-500">Mobile</p>
                        <p className="font-medium">{invoice.customer?.mobile || 'N/A'}</p>
                    </div>
                </div>
            </Card>

            {/* Payment Summary */}
            {paymentSummary && (
                <PaymentSummaryCard summary={paymentSummary} />
            )}

            {/* Invoice Items */}
            <Card className="p-6">
                <h3 className="font-semibold text-neutral-900 mb-3">Items</h3>
                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead>
                            <tr className="border-b border-neutral-200">
                                <th className="px-3 py-2 text-left text-xs font-medium text-neutral-500">Product</th>
                                <th className="px-3 py-2 text-left text-xs font-medium text-neutral-500">Qty</th>
                                <th className="px-3 py-2 text-left text-xs font-medium text-neutral-500">Discount</th>
                                <th className="px-3 py-2 text-left text-xs font-medium text-neutral-500">GST%</th>
                                <th className="px-3 py-2 text-left text-xs font-medium text-neutral-500">WHT%</th>
                                <th className="px-3 py-2 text-right text-xs font-medium text-neutral-500">Effective Price</th>
                                <th className="px-3 py-2 text-right text-xs font-medium text-neutral-500">Total</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-neutral-100">
                            {invoice.items?.map((item, index) => (
                                <tr key={index} className="hover:bg-neutral-50">
                                    <td className="px-3 py-2 text-sm">{item.product_name}</td>
                                    <td className="px-3 py-2 text-sm">{item.quantity}</td>
                                    <td className="px-3 py-2 text-sm">{item.discount || 0}</td>
                                    <td className="px-3 py-2 text-sm">{item.gst || 0}%</td>
                                    <td className="px-3 py-2 text-sm">{item.wht || 0}%</td>
                                    <td className="px-3 py-2 text-sm text-right">
                                        {item.effective_price ? parseFloat(item.effective_price).toFixed(2) : '0.00'}
                                    </td>
                                    <td className="px-3 py-2 text-sm text-right font-medium">
                                        {item.line_total ? parseFloat(item.line_total).toFixed(2) : '0.00'}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                        <tfoot className="border-t border-neutral-200">
                            <tr>
                                <td colSpan="6" className="px-3 py-2 text-right font-medium">Subtotal:</td>
                                <td className="px-3 py-2 text-right font-medium">
                                    {invoice.subtotal ? parseFloat(invoice.subtotal).toFixed(2) : '0.00'}
                                </td>
                            </tr>
                            <tr>
                                <td colSpan="6" className="px-3 py-2 text-right font-medium">GST Total:</td>
                                <td className="px-3 py-2 text-right font-medium">
                                    {invoice.gst_total ? parseFloat(invoice.gst_total).toFixed(2) : '0.00'}
                                </td>
                            </tr>
                            <tr>
                                <td colSpan="6" className="px-3 py-2 text-right font-medium">WHT Total:</td>
                                <td className="px-3 py-2 text-right font-medium">
                                    {invoice.wht_total ? parseFloat(invoice.wht_total).toFixed(2) : '0.00'}
                                </td>
                            </tr>
                            <tr className="text-lg">
                                <td colSpan="6" className="px-3 py-2 text-right font-bold">Grand Total:</td>
                                <td className="px-3 py-2 text-right font-bold text-primary-600">
                                    {invoice.grand_total ? parseFloat(invoice.grand_total).toFixed(2) : '0.00'}
                                </td>
                            </tr>
                        </tfoot>
                    </table>
                </div>
            </Card>

            {/* Payments Section */}
            {invoice.status === 'confirmed' && (
                <Card className="p-6">
                    <h3 className="font-semibold text-neutral-900 mb-3">Payment History</h3>
                    <PaymentHistoryList
                        payments={payments}
                        onDelete={handleDeletePayment}
                        isAdmin={isAdmin}
                    />
                </Card>
            )}

            {/* Returns Section */}
            {invoice.status === 'confirmed' && (
                <Card className="p-6">
                    <h3 className="font-semibold text-neutral-900 mb-3">Returns</h3>
                    <ReturnList
                        returns={returns}
                        onAccept={handleAcceptReturn}
                        isAdmin={isAdmin}
                    />
                </Card>
            )}

            {/* Saved PDFs */}
            {invoice.status === 'confirmed' && pdfs.length > 0 && (
                <Card className="p-6">
                    <h3 className="font-semibold text-neutral-900 mb-3">Saved PDFs</h3>
                    <div className="space-y-2">
                        {pdfs.map((pdf) => (
                            <div key={pdf.id} className="flex justify-between items-center p-3 bg-neutral-50 rounded-lg">
                                <div>
                                    <p className="font-medium">{pdf.file_name}</p>
                                    <p className="text-xs text-neutral-500">
                                        Saved: {new Date(pdf.created_at).toLocaleString()}
                                    </p>
                                </div>
                                <Button
                                    size="sm"
                                    variant="danger"
                                    onClick={() => handleDeletePDF(pdf.id)}
                                >
                                    Delete
                                </Button>
                            </div>
                        ))}
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
            />
        </div>
    );
};

export default InvoiceDetailPage;