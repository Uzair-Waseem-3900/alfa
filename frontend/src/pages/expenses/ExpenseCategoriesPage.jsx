import { useState } from 'react';
import { motion } from 'framer-motion';
import { Plus, Pencil, Trash2, FolderKanban } from 'lucide-react';
import { useExpenseCategories } from '../../hooks/useCashFlow';
import { useToast } from '../../context/ToastContext';
import { extractErrorMessage } from '../../utils/errorMessage';
import Button from '../../components/ui/Button';
import Modal from '../../components/ui/Modal';
import Input from '../../components/ui/Input';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import Table from '../../components/ui/Table';
import Pagination from '../../components/ui/Pagination';
import InlineAlert from '../../components/ui/InlineAlert';
import EmptyState from '../../components/ui/EmptyState';

const CATEGORY_FIELDS = ['name', 'description'];

const splitApiErrors = (error, fieldNames) => {
    const data = error?.response?.data;
    const fieldErrors = {};
    let generalMessage = null;

    if (data && typeof data === 'object' && !Array.isArray(data)) {
        Object.keys(data).forEach((key) => {
            const val = Array.isArray(data[key]) ? data[key][0] : data[key];
            if (fieldNames.includes(key)) {
                fieldErrors[key] = val;
            } else if (!generalMessage) {
                generalMessage = val;
            }
        });
    }

    if (!generalMessage && Object.keys(fieldErrors).length === 0) {
        generalMessage = extractErrorMessage(error, 'Failed to save category');
    }

    return { fieldErrors, generalMessage };
};

const ExpenseCategoriesPage = () => {
    const { toast } = useToast();
    const {
        data: categories, meta, page, setPage, loading, error,
        create, update, delete: deleteCategory, refetch,
    } = useExpenseCategories();

    const [showModal, setShowModal] = useState(false);
    const [editingCategory, setEditingCategory] = useState(null);
    const [formData, setFormData] = useState({ name: '', description: '' });
    const [fieldErrors, setFieldErrors] = useState({});
    const [formError, setFormError] = useState(null);
    const [formLoading, setFormLoading] = useState(false);
    const [deleteConfirm, setDeleteConfirm] = useState(null);
    const [deleteLoading, setDeleteLoading] = useState(false);

    const handleFieldChange = (field, value) => {
        setFormData((prev) => ({ ...prev, [field]: value }));
        if (fieldErrors[field]) {
            setFieldErrors((prev) => ({ ...prev, [field]: '' }));
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setFormError(null);
        setFieldErrors({});
        setFormLoading(true);
        try {
            if (editingCategory) {
                await update(editingCategory.id, formData);
                toast.success('Category updated successfully');
            } else {
                await create(formData);
                toast.success('Category created successfully');
            }
            setShowModal(false);
            resetForm();
        } catch (error) {
            const { fieldErrors: fe, generalMessage } = splitApiErrors(error, CATEGORY_FIELDS);
            setFieldErrors(fe);
            if (generalMessage) {
                setFormError(generalMessage);
            }
        } finally {
            setFormLoading(false);
        }
    };

    const handleEdit = (category) => {
        setEditingCategory(category);
        setFormError(null);
        setFieldErrors({});
        setFormData({ name: category.name, description: category.description || '' });
        setShowModal(true);
    };

    const handleDelete = async (id) => {
        setDeleteLoading(true);
        try {
            await deleteCategory(id);
            toast.success('Category deleted successfully');
            setDeleteConfirm(null);
        } catch (error) {
            toast.error(extractErrorMessage(error, 'Failed to delete category'));
        } finally {
            setDeleteLoading(false);
        }
    };

    const resetForm = () => {
        setFormData({ name: '', description: '' });
        setEditingCategory(null);
        setFieldErrors({});
        setFormError(null);
    };

    const closeModal = () => {
        setShowModal(false);
        resetForm();
    };

    const columns = [
        { key: 'name', label: 'Name' },
        { key: 'description', label: 'Description', render: (value) => value || '-' },
        {
            key: 'created_by',
            label: 'Created By',
            render: (value) => value || 'N/A',
        },
        {
            key: 'created_at',
            label: 'Created',
            render: (value) => new Date(value).toLocaleDateString(),
        },
        {
            key: 'actions',
            label: 'Actions',
            width: '110px',
            render: (_, row) => (
                <div className="flex items-center gap-1">
                    <button
                        onClick={(e) => { e.stopPropagation(); handleEdit(row); }}
                        title="Edit category"
                        aria-label="Edit category"
                        className="inline-flex items-center justify-center w-9 h-9 rounded-lg text-neutral-500 hover:text-primary-700 hover:bg-primary-50 transition-colors"
                    >
                        <Pencil className="w-4 h-4" />
                    </button>
                    <button
                        onClick={(e) => { e.stopPropagation(); setDeleteConfirm(row); }}
                        title="Delete category"
                        aria-label="Delete category"
                        className="inline-flex items-center justify-center w-9 h-9 rounded-lg text-neutral-500 hover:text-error-600 hover:bg-error-50 transition-colors"
                    >
                        <Trash2 className="w-4 h-4" />
                    </button>
                </div>
            ),
        },
    ];

    return (
        <div className="space-y-6">
            <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex flex-col sm:flex-row sm:items-center justify-between gap-4"
            >
                <div className="flex items-center gap-3">
                    <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-primary-700 to-accent-600 flex items-center justify-center shadow-lg shadow-primary-900/20 flex-shrink-0">
                        <FolderKanban className="w-5 h-5 text-white" />
                    </div>
                    <div>
                        <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900">Expense Categories</h1>
                        <p className="text-neutral-500 mt-0.5 text-sm sm:text-base">Manage expense categories for your business</p>
                    </div>
                </div>
                <Button
                    onClick={() => {
                        resetForm();
                        setShowModal(true);
                    }}
                    icon={Plus}
                    className="w-full sm:w-auto"
                >
                    Add Category
                </Button>
            </motion.div>

            {error && <InlineAlert variant="error" message={error} onRetry={refetch} />}

            {loading ? (
                <div className="flex items-center justify-center py-16">
                    <LoadingSpinner size="lg" />
                </div>
            ) : categories.length === 0 ? (
                <EmptyState
                    title="No categories found"
                    description="Create your first expense category to start recording expenses."
                />
            ) : (
                <Table columns={columns} data={categories} />
            )}

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
                onClose={closeModal}
                title={editingCategory ? 'Edit Category' : 'Add Category'}
            >
                <form onSubmit={handleSubmit} className="space-y-4">
                    {formError && <InlineAlert variant="error" message={formError} />}

                    <Input
                        label="Name"
                        value={formData.name}
                        onChange={(e) => handleFieldChange('name', e.target.value)}
                        placeholder="Enter category name"
                        error={fieldErrors.name}
                        required
                    />
                    <Input
                        label="Description"
                        value={formData.description}
                        onChange={(e) => handleFieldChange('description', e.target.value)}
                        placeholder="Enter description (optional)"
                        error={fieldErrors.description}
                    />
                    <div className="flex justify-end gap-3 pt-4">
                        <Button
                            type="button"
                            variant="secondary"
                            onClick={closeModal}
                        >
                            Cancel
                        </Button>
                        <Button type="submit" loading={formLoading}>
                            {editingCategory ? 'Update' : 'Create'}
                        </Button>
                    </div>
                </form>
            </Modal>

            {/* Delete Confirmation */}
            <ConfirmDialog
                isOpen={!!deleteConfirm}
                onClose={() => setDeleteConfirm(null)}
                onConfirm={() => handleDelete(deleteConfirm?.id)}
                title="Delete Category"
                message={`Are you sure you want to delete "${deleteConfirm?.name}"? This action cannot be undone.`}
                confirmText="Delete"
                loading={deleteLoading}
            />
        </div>
    );
};

export default ExpenseCategoriesPage;
