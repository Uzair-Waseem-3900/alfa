import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Filter as FilterIcon, X } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useBillingCRUD } from '../../hooks/useBilling';
import { billingApi } from '../../services/billingApi';
import { useToast } from '../../context/ToastContext';
import { extractErrorMessage } from '../../utils/errorMessage';
import CustomerTable from '../../components/billing/CustomerTable';
import CustomerForm from '../../components/billing/CustomerForm';
import SearchBar from '../../components/ui/SearchBar';
import Button from '../../components/ui/Button';
import Modal from '../../components/ui/Modal';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import Pagination from '../../components/ui/Pagination';
import InlineAlert from '../../components/ui/InlineAlert';
import Card from '../../components/ui/Card';

const TIER_TABS = [
    { value: '', label: 'All' },
    { value: 'good', label: 'Good (70+)' },
    { value: 'average', label: 'Average (31-69)' },
    { value: 'poor', label: 'Poor (≤30)' },
];

const CustomersPage = () => {
    const { user } = useAuth();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';
    const navigate = useNavigate();
    const { toast } = useToast();

    const {
        data, meta, setPage, loading, initialLoading, error,
        filters, setFilters, resetFilters, create, update, delete: deleteCustomer, refetch,
    } = useBillingCRUD(billingApi.customers);

    const [nameSearch, setNameSearch] = useState('');
    const [codeSearch, setCodeSearch] = useState('');
    const [tierFilter, setTierFilter] = useState('');
    const [showModal, setShowModal] = useState(false);
    const [editingCustomer, setEditingCustomer] = useState(null);
    const [formLoading, setFormLoading] = useState(false);
    const [deleteConfirm, setDeleteConfirm] = useState(null);
    const [deleting, setDeleting] = useState(false);

    const handleSearchName = (value) => {
        setNameSearch(value);
        setFilters({ name: value, code: codeSearch, tier: tierFilter || undefined });
    };

    const handleSearchCode = (value) => {
        setCodeSearch(value);
        setFilters({ name: nameSearch, code: value, tier: tierFilter || undefined });
    };

    const handleTierChange = (tier) => {
        setTierFilter(tier);
        setFilters({ name: nameSearch, code: codeSearch, tier: tier || undefined });
    };

    const handleResetFilters = () => {
        setNameSearch('');
        setCodeSearch('');
        setTierFilter('');
        resetFilters();
    };

    // Errors thrown here are re-thrown (not swallowed) so CustomerForm can
    // map DRF field errors (name/code/mobile) onto the right input; only the
    // success path is handled locally.
    const handleSubmit = async (formData) => {
        setFormLoading(true);
        try {
            if (editingCustomer) {
                await update(editingCustomer.id, formData);
                toast.success('Customer updated successfully.');
            } else {
                await create(formData);
                toast.success('Customer created successfully.');
            }
            setShowModal(false);
            setEditingCustomer(null);
        } finally {
            setFormLoading(false);
        }
    };

    const handleEdit = (customer) => {
        setEditingCustomer(customer);
        setShowModal(true);
    };

    const handleDelete = async () => {
        if (!deleteConfirm) return;
        setDeleting(true);
        try {
            await deleteCustomer(deleteConfirm);
            toast.success('Customer deleted successfully.');
            setDeleteConfirm(null);
        } catch (err) {
            toast.error(extractErrorMessage(err, 'Failed to delete customer.'));
        } finally {
            setDeleting(false);
        }
    };

    const handleRowClick = (customer) => {
        navigate(`/billing/customers/${customer.id}`);
    };

    // Full-page spinner ONLY before the very first load completes — a later
    // filter/tier/search change keeps the page (tabs, search bars, table)
    // visible instead of blanking it, with a small inline indicator instead
    // (see the table wrapper below).
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
                    <h1 className="text-3xl font-bold text-neutral-900">Customers</h1>
                    <p className="text-neutral-500 mt-1">Manage customers and view their outstanding</p>
                </div>
                {isAdmin && (
                    <Button
                        onClick={() => {
                            setEditingCustomer(null);
                            setShowModal(true);
                        }}
                        icon={Plus}
                    >
                        Add Customer
                    </Button>
                )}
            </div>

            <Card className="p-4 sm:p-5" hover={false}>
                <div className="flex flex-col sm:flex-row gap-3">
                    <SearchBar
                        onSearch={handleSearchName}
                        placeholder="Search by name..."
                        className="flex-1"
                        value={nameSearch}
                    />
                    <SearchBar
                        onSearch={handleSearchCode}
                        placeholder="Search by code..."
                        className="flex-1"
                        value={codeSearch}
                    />
                    {(nameSearch || codeSearch || tierFilter) && (
                        <button
                            onClick={handleResetFilters}
                            className="flex items-center justify-center gap-1.5 px-4 py-2.5 min-h-[44px] bg-neutral-100 text-neutral-700 rounded-xl hover:bg-neutral-200 transition-colors flex-shrink-0"
                        >
                            <X className="w-4 h-4" />
                            Clear
                        </button>
                    )}
                </div>

                <div className="flex gap-2 flex-wrap mt-4">
                    <FilterIcon className="w-4 h-4 text-neutral-400 self-center mr-1 hidden sm:block" />
                    {TIER_TABS.map((tab) => (
                        <Button
                            key={tab.value || 'all'}
                            size="sm"
                            variant={tierFilter === tab.value ? 'primary' : 'secondary'}
                            onClick={() => handleTierChange(tab.value)}
                        >
                            {tab.label}
                        </Button>
                    ))}
                </div>
            </Card>

            {error && <InlineAlert variant="error" message={error} onRetry={refetch} />}

            <Card className="p-0 overflow-hidden" hover={false}>
                <div className={`relative transition-opacity ${loading ? 'opacity-60' : 'opacity-100'}`}>
                    {loading && (
                        <div className="absolute right-4 top-4 z-10">
                            <LoadingSpinner size="sm" />
                        </div>
                    )}
                    <CustomerTable
                        customers={data}
                        onRowClick={handleRowClick}
                        onEdit={handleEdit}
                        onDelete={(id) => setDeleteConfirm(id)}
                        isAdmin={isAdmin}
                    />
                </div>
            </Card>

            {meta.totalPages > 1 && (
                <Pagination
                    currentPage={meta.currentPage}
                    totalPages={meta.totalPages}
                    onPageChange={setPage}
                />
            )}

            {/* Create/Edit Modal */}
            <Modal
                isOpen={showModal}
                onClose={() => {
                    setShowModal(false);
                    setEditingCustomer(null);
                }}
                title={editingCustomer ? 'Edit Customer' : 'Create Customer'}
            >
                <CustomerForm
                    initialData={editingCustomer}
                    onSubmit={handleSubmit}
                    onCancel={() => {
                        setShowModal(false);
                        setEditingCustomer(null);
                    }}
                    loading={formLoading}
                />
            </Modal>

            {/* Delete Confirmation */}
            <ConfirmDialog
                isOpen={!!deleteConfirm}
                onClose={() => setDeleteConfirm(null)}
                onConfirm={handleDelete}
                title="Delete Customer"
                message="Are you sure you want to delete this customer? This action cannot be undone."
                loading={deleting}
            />
        </div>
    );
};

export default CustomersPage;
