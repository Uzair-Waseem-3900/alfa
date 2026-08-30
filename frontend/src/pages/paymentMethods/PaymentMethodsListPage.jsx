import { useState } from 'react';
import { Navigate, useNavigate, Link } from 'react-router-dom';
import { Plus, Pencil, Trash2, Wallet, ArrowLeftRight, ShieldCheck } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import {
    usePaymentMethods, useCreateMethod, useUpdateMethod, useDeleteMethod,
} from '../../hooks/usePaymentMethods';
import { extractErrorMessage } from '../../utils/errorMessage';
import Button from '../../components/ui/Button';
import Modal from '../../components/ui/Modal';
import Input from '../../components/ui/Input';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Table from '../../components/ui/Table';
import Badge from '../../components/ui/Badge';
import SearchBar from '../../components/ui/SearchBar';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import Pagination from '../../components/ui/Pagination';
import EmptyState from '../../components/ui/EmptyState';
import InlineAlert from '../../components/ui/InlineAlert';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const PaymentMethodsListPage = () => {
    const { user } = useAuth();
    const { toast } = useToast();
    const navigate = useNavigate();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const {
        data: methods, meta, page, setPage, loading, error: listError, filters, setFilters, refetch,
    } = usePaymentMethods();

    const { create, mutating: creating } = useCreateMethod();
    const { update, mutating: updating } = useUpdateMethod();
    const { delete: deleteMethod, mutating: deleting } = useDeleteMethod();

    const [showModal, setShowModal] = useState(false);
    const [editingMethod, setEditingMethod] = useState(null);
    const [formData, setFormData] = useState({ name: '', account_number: '' });
    const [formError, setFormError] = useState('');
    const [deleteConfirm, setDeleteConfirm] = useState(null);
    const [searchTerm, setSearchTerm] = useState('');

    if (!isAdmin) {
        return <Navigate to="/dashboard" replace />;
    }

    const resetForm = () => {
        setFormData({ name: '', account_number: '' });
        setEditingMethod(null);
        setFormError('');
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setFormError('');
        try {
            const payload = { name: formData.name, account_number: formData.account_number || undefined };
            if (editingMethod) {
                await update(editingMethod.id, payload);
                toast.success('Payment method updated');
            } else {
                await create(payload);
                toast.success('Payment method created');
            }
            setShowModal(false);
            resetForm();
            await refetch();
        } catch (error) {
            setFormError(extractErrorMessage(error, 'Failed to save payment method'));
        }
    };

    const handleEdit = (method) => {
        setEditingMethod(method);
        setFormData({ name: method.name || '', account_number: method.account_number || '' });
        setShowModal(true);
    };

    const handleDelete = async (id) => {
        try {
            await deleteMethod(id);
            setDeleteConfirm(null);
            if (methods.length === 1 && page > 1) {
                setPage(page - 1);
            } else {
                await refetch();
            }
            toast.success('Payment method deleted');
        } catch (error) {
            toast.error(extractErrorMessage(error, 'Failed to delete payment method'));
        }
    };

    const handleSearch = (value) => {
        setSearchTerm(value);
        setFilters({ ...filters, search: value });
    };

    const handleRowClick = (method) => navigate(`/payment-methods/${method.id}`);

    const columns = [
        {
            key: 'name',
            label: 'Name',
            render: (value, row) => (
                <span className="flex items-center gap-2 font-medium text-neutral-900">
                    {value}
                    {row.is_protected && (
                        <Badge variant="info" className="gap-1">
                            <ShieldCheck className="w-3 h-3" /> Protected
                        </Badge>
                    )}
                </span>
            ),
        },
        {
            key: 'account_number',
            label: 'Account Number',
            render: (value) => value || <span className="text-neutral-300">—</span>,
        },
        {
            key: 'balance',
            label: 'Balance (PKR)',
            render: (value) => <span className="font-semibold text-success-600">Rs. {fmt(value)}</span>,
        },
        {
            key: 'actions',
            label: 'Actions',
            width: '100px',
            render: (_value, row) => (
                <div className="flex gap-1">
                    <button
                        onClick={(e) => { e.stopPropagation(); handleEdit(row); }}
                        disabled={row.is_protected}
                        className="inline-flex items-center justify-center w-9 h-9 rounded-lg text-primary-600 hover:bg-primary-50 transition-colors disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-transparent"
                        aria-label="Edit payment method"
                    >
                        <Pencil className="w-4 h-4" />
                    </button>
                    <button
                        onClick={(e) => { e.stopPropagation(); setDeleteConfirm(row); }}
                        disabled={row.is_protected}
                        className="inline-flex items-center justify-center w-9 h-9 rounded-lg text-error-600 hover:bg-error-50 transition-colors disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-transparent"
                        aria-label="Delete payment method"
                    >
                        <Trash2 className="w-4 h-4" />
                    </button>
                </div>
            ),
        },
    ];

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <div className="flex items-center gap-2.5">
                        <Wallet className="w-6 h-6 text-primary-600" />
                        <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900">Payment Methods</h1>
                    </div>
                    <p className="text-neutral-500 mt-1">Manage cash, mobile wallets, and other payment accounts</p>
                </div>
                <div className="flex gap-2">
                    <Link to="/payment-methods/transfers">
                        <Button variant="secondary" icon={ArrowLeftRight}>Transfers</Button>
                    </Link>
                    <Button onClick={() => { resetForm(); setShowModal(true); }} icon={Plus}>
                        Add Method
                    </Button>
                </div>
            </div>

            <SearchBar onSearch={handleSearch} placeholder="Search by name..." value={searchTerm} />

            {listError && !loading && (
                <InlineAlert variant="error" title="Couldn't load payment methods" message={listError} onRetry={refetch} />
            )}

            {loading ? (
                <div className="flex items-center justify-center py-16">
                    <LoadingSpinner size="lg" />
                </div>
            ) : methods.length === 0 ? (
                <EmptyState
                    title="No Payment Methods Yet"
                    description="Add a payment method to start tracking balances across accounts."
                />
            ) : (
                <>
                    <Table columns={columns} data={methods} onRowClick={handleRowClick} />
                    {meta.totalPages > 1 && (
                        <Pagination currentPage={meta.currentPage} totalPages={meta.totalPages} onPageChange={setPage} />
                    )}
                </>
            )}

            <Modal
                isOpen={showModal}
                onClose={() => { setShowModal(false); resetForm(); }}
                title={editingMethod ? 'Edit Payment Method' : 'Add Payment Method'}
                size="md"
            >
                <form onSubmit={handleSubmit} className="space-y-4">
                    <Input
                        label="Name"
                        value={formData.name}
                        onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                        placeholder="e.g. JazzCash"
                        required
                    />
                    <Input
                        label="Account Number"
                        value={formData.account_number}
                        onChange={(e) => setFormData({ ...formData, account_number: e.target.value })}
                        placeholder="Optional"
                    />

                    {formError && <InlineAlert variant="error" message={formError} />}

                    <div className="flex justify-end gap-3 pt-4">
                        <Button type="button" variant="secondary" onClick={() => { setShowModal(false); resetForm(); }}>
                            Cancel
                        </Button>
                        <Button type="submit" loading={creating || updating}>
                            {editingMethod ? 'Update Method' : 'Create Method'}
                        </Button>
                    </div>
                </form>
            </Modal>

            <ConfirmDialog
                isOpen={!!deleteConfirm}
                onClose={() => setDeleteConfirm(null)}
                onConfirm={() => handleDelete(deleteConfirm?.id)}
                title="Delete Payment Method"
                message={`Are you sure you want to delete "${deleteConfirm?.name}"? This is blocked while it still holds a balance.`}
                loading={deleting}
            />
        </div>
    );
};

export default PaymentMethodsListPage;
