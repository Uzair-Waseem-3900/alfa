import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Pencil, Trash2, BookOpen, Truck } from 'lucide-react';
import { useCRUD } from '../../hooks/usePurchases';
import { purchasesApi } from '../../services/purchasesApi';
import Table from '../../components/ui/Table';
import Button from '../../components/ui/Button';
import Modal from '../../components/ui/Modal';
import Input from '../../components/ui/Input';
import SearchBar from '../../components/ui/SearchBar';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Badge from '../../components/ui/Badge';
import Card from '../../components/ui/Card';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import InlineAlert from '../../components/ui/InlineAlert';
import EmptyState from '../../components/ui/EmptyState';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { extractErrorMessage } from '../../utils/errorMessage';

const SuppliersPage = () => {
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';
    const navigate = useNavigate();

    const { data, loading, error, create, update, delete: deleteSupplier, refetch } = useCRUD(
        purchasesApi.suppliers,
        { search: '' }
    );

    const [searchTerm, setSearchTerm] = useState('');
    const [showModal, setShowModal] = useState(false);
    const [editingSupplier, setEditingSupplier] = useState(null);
    const [formData, setFormData] = useState({
        name: '',
        code: '',
    });
    const [formLoading, setFormLoading] = useState(false);
    const [formError, setFormError] = useState('');
    const [deleteConfirm, setDeleteConfirm] = useState(null);
    const [deleteLoading, setDeleteLoading] = useState(false);

    const filteredData = data.filter(item =>
        item.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        item.code.toLowerCase().includes(searchTerm.toLowerCase())
    );

    const columns = [
        { key: 'code', label: 'Code', width: '120px' },
        { key: 'name', label: 'Name' },
        {
            key: 'is_deleted',
            label: 'Status',
            width: '110px',
            render: (value) => (
                <Badge variant={value ? 'error' : 'success'}>
                    {value ? 'Deleted' : 'Active'}
                </Badge>
            ),
        },
        {
            key: 'actions',
            label: 'Actions',
            width: '150px',
            render: (_, row) => isAdmin && !row.is_deleted && (
                <div className="flex items-center gap-1">
                    <button
                        onClick={(e) => {
                            e.stopPropagation();
                            handleEdit(row);
                        }}
                        title="Edit supplier"
                        aria-label="Edit supplier"
                        className="p-2 rounded-lg text-neutral-500 hover:text-primary-700 hover:bg-primary-50 transition-colors"
                    >
                        <Pencil className="w-4 h-4" />
                    </button>
                    <button
                        onClick={(e) => {
                            e.stopPropagation();
                            navigate(`/ledger/supplier/${row.id}`);
                        }}
                        title="View ledger"
                        aria-label="View ledger"
                        className="p-2 rounded-lg text-neutral-500 hover:text-indigo-700 hover:bg-indigo-50 transition-colors"
                    >
                        <BookOpen className="w-4 h-4" />
                    </button>
                    <button
                        onClick={(e) => {
                            e.stopPropagation();
                            setDeleteConfirm(row);
                        }}
                        title="Delete supplier"
                        aria-label="Delete supplier"
                        className="p-2 rounded-lg text-neutral-500 hover:text-error-600 hover:bg-error-50 transition-colors"
                    >
                        <Trash2 className="w-4 h-4" />
                    </button>
                </div>
            ),
        },
    ];

    const handleSubmit = async (e) => {
        e.preventDefault();
        setFormLoading(true);
        setFormError('');
        try {
            const submitData = {
                ...formData,
                code: formData.code.toUpperCase(),
            };
            if (editingSupplier) {
                await update(editingSupplier.id, submitData);
                toast.success('Supplier updated successfully');
            } else {
                await create(submitData);
                toast.success('Supplier created successfully');
            }
            setShowModal(false);
            resetForm();
        } catch (err) {
            setFormError(extractErrorMessage(err, 'Failed to save supplier.'));
        } finally {
            setFormLoading(false);
        }
    };

    const handleViewDetails = (supplier) => {
        if (!supplier || supplier.is_deleted) return;
        navigate(`/purchases/suppliers/${supplier.id}`);
    };

    const handleDelete = async (id) => {
        setDeleteLoading(true);
        try {
            await deleteSupplier(id);
            toast.success('Supplier deleted successfully');
            setDeleteConfirm(null);
        } catch (err) {
            toast.error(extractErrorMessage(err, 'Failed to delete supplier.'));
        } finally {
            setDeleteLoading(false);
        }
    };

    const handleEdit = (supplier) => {
        setEditingSupplier(supplier);
        setFormData({
            name: supplier.name,
            code: supplier.code,
        });
        setFormError('');
        setShowModal(true);
    };

    const resetForm = () => {
        setFormData({ name: '', code: '' });
        setEditingSupplier(null);
        setFormError('');
    };

    if (loading && data.length === 0) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                    <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-primary-600 to-accent-600 flex items-center justify-center shadow-lg shadow-primary-900/20 flex-shrink-0">
                        <Truck className="w-5 h-5 text-white" />
                    </div>
                    <div>
                        <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900">Suppliers</h1>
                        <p className="text-neutral-500 mt-0.5 text-sm sm:text-base">Manage suppliers and view outstanding</p>
                    </div>
                </div>
                {isAdmin && (
                    <Button
                        onClick={() => {
                            resetForm();
                            setShowModal(true);
                        }}
                        icon={Plus}
                    >
                        Add Supplier
                    </Button>
                )}
            </div>

            {error && (
                <InlineAlert variant="error" message={error} onRetry={refetch} />
            )}

            <SearchBar
                onSearch={setSearchTerm}
                placeholder="Search suppliers by name or code..."
                className="w-full sm:max-w-md"
            />

            <Card className="p-0 overflow-hidden" hover={false}>
                {filteredData.length === 0 ? (
                    <EmptyState
                        icon={<Truck className="w-8 h-8 text-neutral-400" />}
                        title="No suppliers found"
                        description={searchTerm ? 'Try adjusting your search.' : 'Get started by adding your first supplier.'}
                    />
                ) : (
                    <div className="p-2">
                        <Table
                            columns={columns}
                            data={filteredData}
                            onRowClick={handleViewDetails}
                        />
                    </div>
                )}
            </Card>

            {/* Create/Edit Modal */}
            <Modal
                isOpen={showModal}
                onClose={() => {
                    setShowModal(false);
                    resetForm();
                }}
                title={editingSupplier ? 'Edit Supplier' : 'Create Supplier'}
            >
                <form onSubmit={handleSubmit} className="space-y-4">
                    {formError && <InlineAlert variant="error" message={formError} />}
                    <Input
                        label="Name"
                        value={formData.name}
                        onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                        placeholder="Enter supplier name"
                        required
                    />
                    <Input
                        label="Code"
                        value={formData.code}
                        onChange={(e) => setFormData({ ...formData, code: e.target.value.toUpperCase() })}
                        placeholder="Enter unique code (auto-uppercased)"
                        required
                    />
                    <div className="flex justify-end gap-3 pt-4">
                        <Button
                            type="button"
                            variant="secondary"
                            onClick={() => {
                                setShowModal(false);
                                resetForm();
                            }}
                        >
                            Cancel
                        </Button>
                        <Button type="submit" loading={formLoading}>
                            {editingSupplier ? 'Update' : 'Create'}
                        </Button>
                    </div>
                </form>
            </Modal>

            <ConfirmDialog
                isOpen={!!deleteConfirm}
                onClose={() => setDeleteConfirm(null)}
                onConfirm={() => handleDelete(deleteConfirm?.id)}
                title="Delete Supplier"
                message={`Are you sure you want to delete "${deleteConfirm?.name}"? This action cannot be undone.`}
                confirmText="Delete"
                variant="danger"
                loading={deleteLoading}
            />
        </div>
    );
};

export default SuppliersPage;
