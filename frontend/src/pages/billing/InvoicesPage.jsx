import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, SlidersHorizontal, X } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { billingApi } from '../../services/billingApi';
import InvoiceTable from '../../components/billing/InvoiceTable';
import InvoiceFilterBar from '../../components/billing/InvoiceFilterBar';
import ExtendDueDateModal from '../../components/billing/ExtendDueDateModal';
import Tabs from '../../components/ui/Tabs';
import SearchBar from '../../components/ui/SearchBar';
import Button from '../../components/ui/Button';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Pagination from '../../components/ui/Pagination';
import InlineAlert from '../../components/ui/InlineAlert';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import { usePaginatedList } from '../../hooks/usePaginatedList';
import { extractErrorMessage } from '../../utils/errorMessage';

const InvoicesPage = () => {
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';
    const navigate = useNavigate();

    const [activeTab, setActiveTab] = useState('all');
    const [searchTerm, setSearchTerm] = useState('');
    const [showFilters, setShowFilters] = useState(false);
    const [dueDateInvoice, setDueDateInvoice] = useState(null);
    const [dueDateSaving, setDueDateSaving] = useState(false);

    const [deleteTarget, setDeleteTarget] = useState(null);
    const [deleting, setDeleting] = useState(false);
    const [confirmTarget, setConfirmTarget] = useState(null);
    const [confirming, setConfirming] = useState(false);

    const fetchInvoicesPage = (params) => {
        const p = { ...params };
        if (searchTerm) p.bill_number = searchTerm;
        switch (activeTab) {
            case 'drafts': return billingApi.invoices.getDrafts(p);
            case 'confirmed': return billingApi.invoices.getConfirmed(p);
            case 'outstanding': return billingApi.invoices.getOutstanding(p);
            case 'due': return billingApi.invoices.getDue(p);
            default: return billingApi.invoices.getAll(p);
        }
    };

    const {
        data: invoices, meta, page, setPage, loading, initialLoading, error,
        filters: filterValues, setFilters: setFilterValues, refetch: fetchInvoices,
    } = usePaginatedList(fetchInvoicesPage, {}, 25, [activeTab, searchTerm]);

    const tabs = [
        { value: 'all', label: 'All Invoices' },
        { value: 'drafts', label: 'Drafts' },
        { value: 'confirmed', label: 'Confirmed' },
        { value: 'outstanding', label: 'Outstanding' },
        { value: 'due', label: 'Due Invoices' },
    ];

    const handleTabChange = (tab) => {
        setActiveTab(tab);
        setPage(1);
    };

    const handleSearch = (value) => {
        setSearchTerm(value);
        setPage(1);
    };

    const handleApplyFilters = (newFilters) => {
        setFilterValues(newFilters);
    };

    const handleResetFilters = () => {
        setFilterValues({});
        setSearchTerm('');
    };

    const handleEdit = (invoice) => {
        navigate(`/billing/invoices/${invoice.id}/edit`);
    };

    const handleDelete = (id) => {
        setDeleteTarget(id);
    };

    const confirmDelete = async () => {
        if (!deleteTarget) return;
        setDeleting(true);
        try {
            await billingApi.invoices.delete(deleteTarget);
            toast.success('Draft invoice deleted.');
            setDeleteTarget(null);
            fetchInvoices();
        } catch (err) {
            toast.error(extractErrorMessage(err, 'Failed to delete invoice.'));
        } finally {
            setDeleting(false);
        }
    };

    const handleConfirm = (id) => {
        setConfirmTarget(id);
    };

    const confirmConfirmInvoice = async () => {
        if (!confirmTarget) return;
        setConfirming(true);
        try {
            await billingApi.invoices.confirm(confirmTarget);
            toast.success('Invoice confirmed.');
            setConfirmTarget(null);
            fetchInvoices();
        } catch (err) {
            toast.error(extractErrorMessage(err, 'Failed to confirm invoice.'));
        } finally {
            setConfirming(false);
        }
    };

    const handlePrint = async (id, isDraft = false) => {
        try {
            const token = localStorage.getItem('access_token');
            if (!token) {
                toast.error('Please login again to print.');
                return;
            }

            const response = await fetch(
                `${import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000'}/api/billing/invoices/${id}/print/?is_draft=${isDraft}`,
                {
                    headers: {
                        'Authorization': `Bearer ${token}`,
                    },
                }
            );

            if (!response.ok) {
                throw new Error('Failed to print invoice');
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            window.open(url, '_blank');

            setTimeout(() => {
                window.URL.revokeObjectURL(url);
            }, 1000);
        } catch (err) {
            toast.error('Failed to print invoice. Please try again.');
        }
    };

    const handleRowClick = (invoice) => {
        navigate(`/billing/invoices/${invoice.id}`);
    };

    const handleExtendDueDate = (invoice) => {
        setDueDateInvoice(invoice);
    };

    const handleSaveDueDate = async (newDueDate) => {
        setDueDateSaving(true);
        try {
            await billingApi.invoices.updateDueDate(dueDateInvoice.id, newDueDate);
            toast.success('Due date updated.');
            setDueDateInvoice(null);
            fetchInvoices();
        } finally {
            setDueDateSaving(false);
        }
    };

    if (initialLoading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <h1 className="text-3xl font-bold text-neutral-900">Invoices</h1>
                    <p className="text-neutral-500 mt-1">Manage all invoices</p>
                </div>
                <Button
                    onClick={() => navigate('/billing/invoices/create')}
                    icon={Plus}
                >
                    Create Invoice
                </Button>
            </div>

            <div className="space-y-4">
                <div className="flex gap-4">
                    <SearchBar
                        onSearch={handleSearch}
                        placeholder="Search by bill number..."
                        className="flex-1"
                        value={searchTerm}
                    />
                    <Button
                        variant="secondary"
                        onClick={() => setShowFilters(!showFilters)}
                        icon={SlidersHorizontal}
                    >
                        {showFilters ? 'Hide Filters' : 'Show Filters'}
                    </Button>
                    {(Object.keys(filterValues).length > 0 || searchTerm) && (
                        <Button variant="secondary" onClick={handleResetFilters} icon={X}>
                            Clear All
                        </Button>
                    )}
                </div>

                {showFilters && (
                    <InvoiceFilterBar
                        onApply={handleApplyFilters}
                        onReset={handleResetFilters}
                    />
                )}

                <Tabs
                    tabs={tabs}
                    activeTab={activeTab}
                    onChange={handleTabChange}
                />
            </div>

            {error && <InlineAlert variant="error" message={error} onRetry={fetchInvoices} />}

            {loading && !initialLoading ? (
                <div className="flex items-center justify-center py-16">
                    <LoadingSpinner size="md" />
                </div>
            ) : (
                <InvoiceTable
                    invoices={invoices}
                    onRowClick={handleRowClick}
                    onEdit={handleEdit}
                    onDelete={handleDelete}
                    onConfirm={handleConfirm}
                    onPrint={handlePrint}
                    onExtendDueDate={handleExtendDueDate}
                    isAdmin={isAdmin}
                    showActions={true}
                />
            )}

            {meta.totalPages > 1 && (
                <Pagination
                    currentPage={meta.currentPage}
                    totalPages={meta.totalPages}
                    onPageChange={setPage}
                />
            )}

            <ExtendDueDateModal
                isOpen={Boolean(dueDateInvoice)}
                onClose={() => setDueDateInvoice(null)}
                onSubmit={handleSaveDueDate}
                currentDueDate={dueDateInvoice?.payment_due_date}
                loading={dueDateSaving}
            />

            <ConfirmDialog
                isOpen={Boolean(deleteTarget)}
                onClose={() => setDeleteTarget(null)}
                onConfirm={confirmDelete}
                title="Delete Draft Invoice"
                message="Are you sure you want to delete this draft invoice? This cannot be undone."
                confirmText="Delete"
                variant="danger"
                loading={deleting}
            />

            <ConfirmDialog
                isOpen={Boolean(confirmTarget)}
                onClose={() => setConfirmTarget(null)}
                onConfirm={confirmConfirmInvoice}
                title="Confirm Invoice"
                message="Are you sure you want to confirm this invoice? Stock will be deducted and it can no longer be edited."
                confirmText="Confirm"
                variant="primary"
                loading={confirming}
            />
        </div>
    );
};

export default InvoicesPage;
