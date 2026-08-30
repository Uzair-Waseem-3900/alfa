import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { extractErrorMessage } from '../../utils/errorMessage';
import { ledgerApi } from '../../services/ledgerApi';
import { useLedgerDetail, useSavedPDFs } from '../../hooks/useLedger';
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
import InlineAlert from '../../components/ui/InlineAlert';

const LedgerBySupplierPage = () => {
    const { supplierId } = useParams();
    const navigate = useNavigate();
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const [ledgerId, setLedgerId] = useState(null);
    const [loading, setLoading] = useState(true);

    const {
        ledger,
        entries,
        closingBalance,
        loading: ledgerLoading,
        error,
        filters,
        setFilters,
        refetch,
        meta,
        page,
        setPage
    } = useLedgerDetail(ledgerId);

    const {
        data: savedPDFs,
        loading: pdfsLoading,
        deletePDF: deleteSavedPDF,
        refetch: refetchPDFs
    } = useSavedPDFs(ledgerId);

    const [showSavePDFModal, setShowSavePDFModal] = useState(false);
    const [showSavedPDFs, setShowSavedPDFs] = useState(false);
    const [pdfLoading, setPdfLoading] = useState(false);

    // Fetch ledger by supplier ID — must stay above the isAdmin early return
    // below (React hooks must run unconditionally on every render).
    useEffect(() => {
        const fetchLedgerId = async () => {
            setLoading(true);
            try {
                const data = await ledgerApi.getBySupplierId(supplierId);
                setLedgerId(data.ledger?.id);
            } catch (error) {
                console.error('Failed to fetch ledger:', error);
                toast.error(extractErrorMessage(error, 'Failed to fetch ledger'));
            } finally {
                setLoading(false);
            }
        };
        fetchLedgerId();
    }, [supplierId, toast]);

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

            const response = await ledgerApi.print(ledgerId, params);
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

            await ledgerApi.savePDF(ledgerId, payload);
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

    if (loading || ledgerLoading) {
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
                <p className="text-neutral-500 mt-1">This supplier does not have a ledger yet.</p>
                <BackLink to="/ledger" className="mt-4">Back to Ledgers</BackLink>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header with Actions */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <BackLink to="/ledger">Back to Ledgers</BackLink>
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
                </div>
            </div>

            {error && <InlineAlert variant="error" message={error} onRetry={refetch} />}

            {/* Ledger Header */}
            <LedgerHeader ledger={ledger} closingBalance={closingBalance} />

            {/* Filter Bar */}
            <LedgerFilterBar
                filters={filters}
                onFilterChange={handleFilterChange}
                onClear={handleClearFilters}
            />

            {/* Entries Table */}
            <div className="bg-white rounded-xl shadow-card overflow-hidden border border-neutral-200">
                <LedgerTable entries={entries} loading={ledgerLoading} />

                {/* Closing Balance Summary */}
                {entries.length > 0 && (
                    <ClosingBalanceSummary entries={entries} />
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
                defaultFileName={`Ledger_${ledger.supplier_code}`}
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
        </div>
    );
};

export default LedgerBySupplierPage;