import { useState } from 'react';
import { Plus, Pencil, Trash2, ShieldAlert, Tags } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { useRecurringExpenseCategories } from '../../hooks/useRecurringExpenses';
import { extractErrorMessage } from '../../utils/errorMessage';
import Button from '../../components/ui/Button';
import BackLink from '../../components/ui/BackLink';
import Modal from '../../components/ui/Modal';
import Input from '../../components/ui/Input';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Table from '../../components/ui/Table';
import Pagination from '../../components/ui/Pagination';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import EmptyState from '../../components/ui/EmptyState';
import InlineAlert from '../../components/ui/InlineAlert';

const RecurringExpenseCategoriesPage = () => {
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const {
        data: categories, meta, page, setPage, loading,
        refetch, create, update, delete: deleteCategory,
    } = useRecurringExpenseCategories();

    const [showModal, setShowModal] = useState(false);
    const [editingCategory, setEditingCategory] = useState(null);
    const [formData, setFormData] = useState({ name: '', description: '' });
    const [formLoading, setFormLoading] = useState(false);
    const [formError, setFormError] = useState('');
    const [deleteConfirm, setDeleteConfirm] = useState(null);
    const [deleteLoading, setDeleteLoading] = useState(false);

    const resetForm = () => {
        setFormData({ name: '', description: '' });
        setEditingCategory(null);
        setFormError('');
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setFormError('');
        setFormLoading(true);
        try {
            if (editingCategory) {
                await update(editingCategory.id, formData);
            } else {
                await create(formData);
            }
            setShowModal(false);
            resetForm();
            refetch();
            toast.success(editingCategory ? 'Category updated successfully' : 'Category created successfully');
        } catch (error) {
            setFormError(extractErrorMessage(error, 'Failed to save category'));
        } finally {
            setFormLoading(false);
        }
    };

    const handleEdit = (category) => {
        setEditingCategory(category);
        setFormData({ name: category.name, description: category.description || '' });
        setShowModal(true);
    };

    const handleDelete = async (id) => {
        setDeleteLoading(true);
        try {
            await deleteCategory(id);
            setDeleteConfirm(null);
            refetch();
            toast.success('Category deleted');
        } catch (error) {
            setDeleteConfirm(null);
            toast.error(extractErrorMessage(error, 'Failed to delete category'));
        } finally {
            setDeleteLoading(false);
        }
    };

    const columns = [
        { key: 'name', label: 'Name', render: (v) => <span className="font-medium text-neutral-900">{v}</span> },
        { key: 'description', label: 'Description', render: (v) => v || <span className="text-neutral-300">—</span> },
        {
            key: 'actions',
            label: 'Actions',
            width: '150px',
            render: (_v, row) => (
                <div className="flex items-center gap-3">
                    <button onClick={() => handleEdit(row)} className="inline-flex items-center gap-1 text-primary-600 hover:text-primary-700 text-sm font-medium min-h-[44px] sm:min-h-0">
                        <Pencil className="w-3.5 h-3.5" /> Edit
                    </button>
                    <button onClick={() => setDeleteConfirm(row)} className="inline-flex items-center gap-1 text-error-600 hover:text-error-700 text-sm font-medium min-h-[44px] sm:min-h-0">
                        <Trash2 className="w-3.5 h-3.5" /> Delete
                    </button>
                </div>
            ),
        },
    ];

    if (!isAdmin) {
        return (
            <div className="flex flex-col items-center justify-center text-center py-20">
                <div className="w-14 h-14 rounded-full bg-error-50 flex items-center justify-center mb-4">
                    <ShieldAlert className="w-7 h-7 text-error-500" />
                </div>
                <h2 className="text-2xl font-semibold text-neutral-900">Access Denied</h2>
                <p className="text-neutral-500 mt-2 max-w-sm">Only admins or superusers can view recurring expense categories.</p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <BackLink to="/recurring-expenses">Back to Recurring Expenses</BackLink>
                    <h1 className="text-3xl font-bold text-neutral-900 mt-1">Categories</h1>
                    <p className="text-neutral-500 mt-1 max-w-xl">
                        Deleting a category only hides it from new templates — anything already assigned keeps its own frozen category name forever.
                    </p>
                </div>
                <Button onClick={() => { resetForm(); setShowModal(true); }} icon={Plus}>Add Category</Button>
            </div>

            {loading ? (
                <div className="flex items-center justify-center py-8">
                    <LoadingSpinner size="lg" />
                </div>
            ) : categories.length === 0 ? (
                <EmptyState
                    icon={<Tags className="w-8 h-8 text-neutral-400" />}
                    title="No Categories Yet"
                    description="Add one to start registering recurring expenses (Rent, Salaries, ...)."
                />
            ) : (
                <>
                    <Table columns={columns} data={categories} />
                    {meta.totalPages > 1 && (
                        <Pagination currentPage={meta.currentPage} totalPages={meta.totalPages} onPageChange={setPage} />
                    )}
                </>
            )}

            <Modal
                isOpen={showModal}
                onClose={() => { setShowModal(false); resetForm(); }}
                title={editingCategory ? 'Edit Category' : 'Add Category'}
                size="lg"
            >
                <form onSubmit={handleSubmit} className="space-y-4">
                    <Input
                        label="Name"
                        value={formData.name}
                        onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                        placeholder="e.g. Rent, Salaries, Utilities"
                        required
                    />
                    <Input
                        label="Description"
                        value={formData.description}
                        onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                        placeholder="Optional"
                    />

                    {formError && <InlineAlert variant="error" message={formError} />}

                    <div className="flex justify-end gap-3 pt-4">
                        <Button type="button" variant="secondary" onClick={() => { setShowModal(false); resetForm(); }}>
                            Cancel
                        </Button>
                        <Button type="submit" loading={formLoading}>
                            {editingCategory ? 'Update Category' : 'Create Category'}
                        </Button>
                    </div>
                </form>
            </Modal>

            <ConfirmDialog
                isOpen={!!deleteConfirm}
                onClose={() => setDeleteConfirm(null)}
                onConfirm={() => handleDelete(deleteConfirm?.id)}
                loading={deleteLoading}
                title="Delete Category"
                message={`Are you sure you want to delete "${deleteConfirm?.name}"? Templates and history using it are unaffected — it just won't be selectable going forward.`}
            />
        </div>
    );
};

export default RecurringExpenseCategoriesPage;
