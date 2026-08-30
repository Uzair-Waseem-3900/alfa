import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Pencil, Trash2, X, LayoutGrid } from 'lucide-react';
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
import Pagination from '../../components/ui/Pagination';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { extractErrorMessage } from '../../utils/errorMessage';

const ShelvesPage = () => {
    const navigate = useNavigate();
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const { data, meta, page, setPage, loading, error, filters, setFilters, create, update, delete: deleteShelf, refetch } = useCRUD(
        purchasesApi.shelves,
        { product_search: '' }
    );

    const [searchTerm, setSearchTerm] = useState('');
    const [productSearchTerm, setProductSearchTerm] = useState('');
    // Bumped on "Clear Filters" to force both SearchBars (uncontrolled,
    // internal-state inputs) to remount with an empty value — SearchBar
    // has no external value/reset prop, so a key change is the only way
    // to visually clear it without changing the shared component.
    const [filterResetKey, setFilterResetKey] = useState(0);
    const [showModal, setShowModal] = useState(false);
    const [editingShelf, setEditingShelf] = useState(null);
    const [formData, setFormData] = useState({ name: '', description: '' });
    const [formLoading, setFormLoading] = useState(false);
    const [formError, setFormError] = useState('');
    const [deleteConfirm, setDeleteConfirm] = useState(null);
    const [deleteLoading, setDeleteLoading] = useState(false);

    const filteredData = data.filter(item =>
        item.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (item.description && item.description.toLowerCase().includes(searchTerm.toLowerCase()))
    );

    const handleProductSearch = (value) => {
        setProductSearchTerm(value);
        setFilters({ ...filters, product_search: value });
    };

    const hasActiveFilters = !!searchTerm || !!productSearchTerm;

    const handleClearFilters = () => {
        setSearchTerm('');
        setProductSearchTerm('');
        setFilters({ ...filters, product_search: '' });
        setFilterResetKey((k) => k + 1);
    };

    const columns = [
        { key: 'id', label: 'ID', width: '80px' },
        { key: 'name', label: 'Name' },
        {
            key: 'description',
            label: 'Description',
            render: (value) => value || <span className="text-neutral-400">—</span>,
        },
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
            width: '100px',
            render: (_, row) => isAdmin && !row.is_deleted && (
                <div className="flex items-center gap-1">
                    <button
                        onClick={(e) => {
                            e.stopPropagation();
                            handleEdit(row);
                        }}
                        title="Edit shelf"
                        aria-label="Edit shelf"
                        className="p-2 rounded-lg text-neutral-500 hover:text-primary-700 hover:bg-primary-50 transition-colors"
                    >
                        <Pencil className="w-4 h-4" />
                    </button>
                    <button
                        onClick={(e) => {
                            e.stopPropagation();
                            setDeleteConfirm(row);
                        }}
                        title="Delete shelf"
                        aria-label="Delete shelf"
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
            if (editingShelf) {
                await update(editingShelf.id, formData);
                toast.success('Shelf updated successfully');
            } else {
                await create(formData);
                toast.success('Shelf created successfully');
            }
            setShowModal(false);
            resetForm();
        } catch (err) {
            setFormError(extractErrorMessage(err, 'Failed to save shelf.'));
        } finally {
            setFormLoading(false);
        }
    };

    const handleDelete = async (id) => {
        setDeleteLoading(true);
        try {
            await deleteShelf(id);
            toast.success('Shelf deleted successfully');
            setDeleteConfirm(null);
        } catch (err) {
            toast.error(extractErrorMessage(err, 'Failed to delete shelf.'));
        } finally {
            setDeleteLoading(false);
        }
    };

    const handleEdit = (shelf) => {
        setEditingShelf(shelf);
        setFormData({ name: shelf.name, description: shelf.description || '' });
        setFormError('');
        setShowModal(true);
    };

    const resetForm = () => {
        setFormData({ name: '', description: '' });
        setEditingShelf(null);
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
                        <LayoutGrid className="w-5 h-5 text-white" />
                    </div>
                    <div>
                        <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900">Shelves</h1>
                        <p className="text-neutral-500 mt-0.5 text-sm sm:text-base">Manage product shelves</p>
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
                        Add Shelf
                    </Button>
                )}
            </div>

            {error && (
                <InlineAlert variant="error" message={error} onRetry={refetch} />
            )}

            <div className="flex flex-col sm:flex-row gap-3">
                <SearchBar
                    key={`name-${filterResetKey}`}
                    onSearch={setSearchTerm}
                    placeholder="Search shelves..."
                    className="flex-1"
                />
                <SearchBar
                    key={`product-${filterResetKey}`}
                    onSearch={handleProductSearch}
                    placeholder="Search by product name or code..."
                    className="flex-1"
                />
                {hasActiveFilters && (
                    <Button type="button" variant="secondary" onClick={handleClearFilters} icon={X}>
                        Clear Filters
                    </Button>
                )}
            </div>

            <Card className="p-0 overflow-hidden" hover={false}>
                {filteredData.length === 0 ? (
                    <EmptyState
                        icon={<LayoutGrid className="w-8 h-8 text-neutral-400" />}
                        title="No shelves found"
                        description={hasActiveFilters ? 'Try adjusting your search.' : 'Get started by adding your first shelf.'}
                    />
                ) : (
                    <div className="p-2">
                        <Table
                            columns={columns}
                            data={filteredData}
                            onRowClick={(row) => navigate(`/purchases/shelves/${row.id}`)}
                        />
                    </div>
                )}
            </Card>

            {meta.totalPages > 1 && (
                <Pagination
                    currentPage={meta.currentPage}
                    totalPages={meta.totalPages}
                    onPageChange={setPage}
                />
            )}

            <Modal
                isOpen={showModal}
                onClose={() => {
                    setShowModal(false);
                    resetForm();
                }}
                title={editingShelf ? 'Edit Shelf' : 'Create Shelf'}
            >
                <form onSubmit={handleSubmit} className="space-y-4">
                    {formError && <InlineAlert variant="error" message={formError} />}
                    <Input
                        label="Name"
                        value={formData.name}
                        onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                        placeholder="Enter shelf name"
                        required
                    />
                    <Input
                        label="Description"
                        value={formData.description}
                        onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                        placeholder="Enter description (optional)"
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
                            {editingShelf ? 'Update' : 'Create'}
                        </Button>
                    </div>
                </form>
            </Modal>

            <ConfirmDialog
                isOpen={!!deleteConfirm}
                onClose={() => setDeleteConfirm(null)}
                onConfirm={() => handleDelete(deleteConfirm?.id)}
                title="Delete Shelf"
                message={`Are you sure you want to delete "${deleteConfirm?.name}"? This action cannot be undone.`}
                confirmText="Delete"
                variant="danger"
                loading={deleteLoading}
            />
        </div>
    );
};

export default ShelvesPage;
