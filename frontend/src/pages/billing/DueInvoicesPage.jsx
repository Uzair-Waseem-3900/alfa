import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SlidersHorizontal, X, CalendarCheck } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { billingApi } from '../../services/billingApi';
import InvoiceTable from '../../components/billing/InvoiceTable';
import InvoiceFilterBar from '../../components/billing/InvoiceFilterBar';
import ExtendDueDateModal from '../../components/billing/ExtendDueDateModal';
import SearchBar from '../../components/ui/SearchBar';
import Button from '../../components/ui/Button';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Pagination from '../../components/ui/Pagination';
import InlineAlert from '../../components/ui/InlineAlert';
import EmptyState from '../../components/ui/EmptyState';
import { usePaginatedList } from '../../hooks/usePaginatedList';

const DueInvoicesPage = () => {
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';
    const navigate = useNavigate();

    const [searchTerm, setSearchTerm] = useState('');
    const [showFilters, setShowFilters] = useState(false);
    const [dueDateInvoice, setDueDateInvoice] = useState(null);
    const [dueDateSaving, setDueDateSaving] = useState(false);

    const fetchDueInvoicesPage = (params) => {
        const p = { ...params };
        if (searchTerm) p.bill_number = searchTerm;
        return billingApi.invoices.getDue(p);
    };

    const {
        data: invoices, meta, page, setPage, loading, initialLoading, error,
        filters: filterValues, setFilters: setFilterValues, refetch: fetchInvoices,
    } = usePaginatedList(fetchDueInvoicesPage, {}, 25, [searchTerm]);

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

    const handleRowClick = (invoice) => {
        navigate(`/billing/invoices/${invoice.id}`);
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
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            if (!response.ok) throw new Error('Failed to print invoice');
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            window.open(url, '_blank');
            setTimeout(() => window.URL.revokeObjectURL(url), 1000);
        } catch (err) {
            toast.error('Failed to print invoice. Please try again.');
        }
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
            <div>
                <h1 className="text-3xl font-bold text-neutral-900">Due Invoices</h1>
                <p className="text-neutral-500 mt-1">
                    Confirmed invoices whose due date has passed and still carry a balance
                </p>
                <p className="text-sm text-neutral-400 mt-1">
                    {meta.count} invoice{meta.count !== 1 ? 's' : ''} past due
                </p>
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
            </div>

            {error && <InlineAlert variant="error" message={error} onRetry={fetchInvoices} />}

            {loading && !initialLoading ? (
                <div className="flex items-center justify-center py-16">
                    <LoadingSpinner size="md" />
                </div>
            ) : invoices.length === 0 ? (
                <EmptyState
                    title="No Due Invoices"
                    description="Nothing is past its due date right now."
                    icon={<CalendarCheck className="w-8 h-8 text-success-500" />}
                />
            ) : (
                <>
                    <InvoiceTable
                        invoices={invoices}
                        onRowClick={handleRowClick}
                        onPrint={handlePrint}
                        onExtendDueDate={handleExtendDueDate}
                        isAdmin={isAdmin}
                        showActions={true}
                    />

                    {meta.totalPages > 1 && (
                        <Pagination
                            currentPage={meta.currentPage}
                            totalPages={meta.totalPages}
                            onPageChange={setPage}
                        />
                    )}
                </>
            )}

            <ExtendDueDateModal
                isOpen={Boolean(dueDateInvoice)}
                onClose={() => setDueDateInvoice(null)}
                onSubmit={handleSaveDueDate}
                currentDueDate={dueDateInvoice?.payment_due_date}
                loading={dueDateSaving}
            />
        </div>
    );
};

export default DueInvoicesPage;
