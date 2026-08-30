import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { extractErrorMessage } from '../../utils/errorMessage';
import { useLedgerDetail, useSavedPDFs } from '../../hooks/useLedger';
import { customerLedgerApi } from '../../services/ledgerApi';
import LedgerHeader from '../../components/ledger/LedgerHeader';
import LedgerFilterBar from '../../components/ledger/LedgerFilterBar';
import LedgerTable from '../../components/ledger/LedgerTable';
import ClosingBalanceSummary from '../../components/ledger/ClosingBalanceSummary';
import SavePDFModal from '../../components/ledger/SavePDFModal';
import SavedPDFDrawer from '../../components/ledger/SavedPDFDrawer';
import BackLink from '../../components/ui/BackLink';
import Button from '../../components/ui/Button';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Pagination from '../../components/ui/Pagination';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import InlineAlert from '../../components/ui/InlineAlert';

// Customer entry types — the customer side uses 'sale' where the supplier
// side uses 'purchase', and adds 'opening_balance'.
const CUSTOMER_ENTRY_TYPE_OPTIONS = [
    { value: '', label: 'All Types' },
    { value: 'sale', label: 'Sale' },
    { value: 'payment', label: 'Payment' },
    { value: 'return', label: 'Return' },
    { value: 'advance', label: 'Advance' },
    { value: 'opening_balance', label: 'Opening Balance' },
];

// Debit = customer owes us more (a sale). Credit = customer owes us less
// (payment, return, or advance) — the opposite direction from the supplier
// ledger, so the balance wording is receivable-flavored, not payable.
const getCustomerBalanceMessage = (balance) => {
    const num = typeof balance === 'string' ? parseFloat(balance) : balance;
    if (isNaN(num)) return 'Account Settled';
    if (num === 0) return 'Account Settled';
    if (num > 0) return `Amount Receivable: Rs. ${num.toFixed(2)} — Customer owes you this amount`;
    return `Customer Credit: Rs. ${Math.abs(num).toFixed(2)} — You owe customer this amount`;
};

const CustomerLedgerDetailPage = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const {
        ledger,
        entries,
        closingBalance,
        loading,
        error,
        filters,
        setFilters,
        refetch,
        meta,
        page,
        setPage
    } = useLedgerDetail(id, {}, 25, customerLedgerApi);

    const {
        data: savedPDFs,
        loading: pdfsLoading,
        deletePDF: deleteSavedPDF,
        refetch: refetchPDFs
    } = useSavedPDFs(id, customerLedgerApi);

    const [showSavePDFModal, setShowSavePDFModal] = useState(false);
    const [showSavedPDFs, setShowSavedPDFs] = useState(false);
    const [pdfLoading, setPdfLoading] = useState(false);
    const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
    const [deleteLoading, setDeleteLoading] = useState(false);
    const [deleteError, setDeleteError] = useState(null);

    // Redirect normal users
    if (!isAdmin) {
        navigate('/dashboard');
        return null;
    }

    const handleFilterChange = (newFilters) => {
        setFilters(newFilters);
    };

    const handleClearFilters = () => {
        setFilters({
            date_from: '',
            date_to: '',
            entry_type: '',
            reference: '',
            min_amount: '',
            max_amount: '',
        });
    };

    const handlePrint = async () => {
        try {
            const params = {};
            if (filters.date_from) params.date_from = filters.date_from;
            if (filters.date_to) params.date_to = filters.date_to;

            const response = await customerLedgerApi.print(id, params);
            const blob = new Blob([response], { type: 'application/pdf' });
            const url = window.URL.createObjectURL(blob);
            window.open(url, '_blank');
            setTimeout(() => window.URL.revokeObjectURL(url), 1000);
        } catch (error) {
            console.error('Failed to print ledger:', error);
            toast.error(extractErrorMessage(error, 'Failed to print ledger'));
        }
    };

    const handleSavePDF = async (data) => {
        setPdfLoading(true);
        try {
            const payload = {};
            if (data.file_name) payload.file_name = data.file_name;
            if (data.date_from) payload.date_from = data.date_from;
            if (data.date_to) payload.date_to = data.date_to;

            await customerLedgerApi.savePDF(id, payload);
            setShowSavePDFModal(false);
            refetchPDFs();
            toast.success('PDF saved successfully');
        } catch (error) {
            console.error('Failed to save PDF:', error);
            toast.error(extractErrorMessage(error, 'Failed to save PDF'));
        } finally {
            setPdfLoading(false);
        }
    };

    // Confirmation now lives in SavedPDFDrawer's own ConfirmDialog — no
    // second native window.confirm() prompt.
    const handleDeletePDF = async (pdfId) => {
        try {
            await deleteSavedPDF(pdfId);
            toast.success('PDF deleted successfully');
        } catch (error) {
            console.error('Failed to delete PDF:', error);
            toast.error(extractErrorMessage(error, 'Failed to delete PDF'));
        }
    };

    const handleDeleteLedger = async () => {
        setDeleteLoading(true);
        setDeleteError(null);
        try {
            await customerLedgerApi.delete(id);
            navigate('/ledger/customers');
        } catch (error) {
            console.error('Failed to delete ledger:', error);
            setDeleteError(extractErrorMessage(error, 'Failed to delete ledger. Please try again.'));
            setShowDeleteConfirm(false);
        } finally {
            setDeleteLoading(false);
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    if (!ledger) {
        return (
            <div className="text-center py-12">
                <h2 className="text-2xl font-semibold text-neutral-900">Ledger Not Found</h2>
                <p className="text-neutral-500 mt-1">The ledger you're looking for doesn't exist.</p>
                <BackLink to="/ledger/customers" className="mt-4">Back to Ledgers</BackLink>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header with Actions */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <BackLink to="/ledger/customers">Back to Ledgers</BackLink>
                <div className="flex gap-2 flex-wrap">
                    <Button variant="secondary" onClick={handlePrint}>
                        Print
                    </Button>
                    <Button variant="secondary" onClick={() => setShowSavePDFModal(true)}>
                        Save PDF
                    </Button>
                    <Button variant="secondary" onClick={() => setShowSavedPDFs(true)}>
                        Saved PDFs
                    </Button>
                    <Button
                        variant="danger"
                        disabled={!ledger.customer_is_deleted}
                        title={
                            ledger.customer_is_deleted
                                ? undefined
                                : 'Delete the customer first before deleting their ledger.'
                        }
                        onClick={() => {
                            setDeleteError(null);
                            setShowDeleteConfirm(true);
                        }}
                    >
                        Delete Ledger
                    </Button>
                </div>
            </div>

            {!ledger.customer_is_deleted && (
                <p className="text-sm text-neutral-500">
                    This ledger can only be deleted after its customer has been deleted.
                </p>
            )}

            {deleteError && <InlineAlert variant="error" message={deleteError} />}
            {error && <InlineAlert variant="error" message={error} onRetry={refetch} />}

            {/* Ledger Header */}
            <LedgerHeader
                ledger={ledger}
                closingBalance={closingBalance}
                nameKey="customer_name"
                codeKey="customer_code"
                positiveLabel="Receivable"
                negativeLabel="Credit"
            />

            {/* Filter Bar */}
            <LedgerFilterBar
                filters={filters}
                onFilterChange={handleFilterChange}
                onClear={handleClearFilters}
                entryTypeOptions={CUSTOMER_ENTRY_TYPE_OPTIONS}
            />

            {/* Entries Table */}
            <div className="bg-white rounded-xl shadow-card overflow-hidden border border-neutral-200">
                <LedgerTable entries={entries} loading={loading} />

                {/* Closing Balance Summary */}
                {entries.length > 0 && (
                    <ClosingBalanceSummary entries={entries} getBalanceMessage={getCustomerBalanceMessage} />
                )}
            </div>

            {meta.totalPages > 1 && (
                <Pagination
                    currentPage={meta.currentPage}
                    totalPages={meta.totalPages}
                    onPageChange={setPage}
                />
            )}

            {/* Save PDF Modal */}
            <SavePDFModal
                isOpen={showSavePDFModal}
                onClose={() => setShowSavePDFModal(false)}
                onSubmit={handleSavePDF}
                loading={pdfLoading}
                defaultFileName={`Ledger_${ledger.customer_code}`}
                dateFrom={filters.date_from}
                dateTo={filters.date_to}
            />

            {/* Saved PDFs Drawer */}
            <SavedPDFDrawer
                isOpen={showSavedPDFs}
                onClose={() => setShowSavedPDFs(false)}
                pdfs={savedPDFs}
                onDelete={handleDeletePDF}
                loading={pdfsLoading}
            />

            {/* Delete Ledger Confirm */}
            <ConfirmDialog
                isOpen={showDeleteConfirm}
                onClose={() => setShowDeleteConfirm(false)}
                onConfirm={handleDeleteLedger}
                title="Delete Ledger"
                message={`Are you sure you want to delete the ledger for "${ledger.customer_name}" (${ledger.customer_code})? This action cannot be undone.`}
                loading={deleteLoading}
            />
        </div>
    );
};

export default CustomerLedgerDetailPage;
