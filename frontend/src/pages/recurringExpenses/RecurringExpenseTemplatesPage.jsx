import { useState, useEffect } from 'react';
import { Plus, Pencil, Trash2, ShieldAlert, Repeat, SlidersHorizontal } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { useRecurringExpenseTemplates } from '../../hooks/useRecurringExpenses';
import { recurringExpensesApi } from '../../services/recurringExpensesApi';
import { extractErrorMessage } from '../../utils/errorMessage';
import { todayLocalDate } from '../../utils/helpers';
import Button from '../../components/ui/Button';
import BackLink from '../../components/ui/BackLink';
import Modal from '../../components/ui/Modal';
import Input from '../../components/ui/Input';
import Select from '../../components/ui/Select';
import Badge from '../../components/ui/Badge';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Table from '../../components/ui/Table';
import FilterBar from '../../components/ui/FilterBar';
import Pagination from '../../components/ui/Pagination';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import EmptyState from '../../components/ui/EmptyState';
import InlineAlert from '../../components/ui/InlineAlert';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const emptyForm = { name: '', category: '', amount: '', start_date: todayLocalDate(), note: '' };

const RecurringExpenseTemplatesPage = () => {
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const {
        data: templates, meta, page, setPage, loading, filters, setFilters,
        refetch, create, update, delete: deleteTemplate,
    } = useRecurringExpenseTemplates();

    const [categories, setCategories] = useState([]);
    const [showFilters, setShowFilters] = useState(false);
    const [showModal, setShowModal] = useState(false);
    const [editingTemplate, setEditingTemplate] = useState(null);
    const [formData, setFormData] = useState(emptyForm);
    const [formLoading, setFormLoading] = useState(false);
    const [formError, setFormError] = useState('');
    const [deleteConfirm, setDeleteConfirm] = useState(null);
    const [deleteLoading, setDeleteLoading] = useState(false);
    const [togglingId, setTogglingId] = useState(null);

    useEffect(() => {
        recurringExpensesApi.categories.getAll({ page_size: 500 }).then((res) => {
            setCategories(res?.results ?? res ?? []);
        });
    }, []);

    const resetForm = () => {
        setFormData(emptyForm);
        setEditingTemplate(null);
        setFormError('');
    };

    const handleApplyFilters = (values) => setFilters(values);
    const handleResetFilters = () => setFilters({});

    const filterConfig = [
        { name: 'category_id', label: 'Category', type: 'select', options: [
            { value: '', label: 'All' },
            ...categories.map((c) => ({ value: c.id, label: c.name })),
        ] },
        { name: 'is_active', label: 'Status', type: 'select', options: [
            { value: '', label: 'All' },
            { value: 'true', label: 'Active' },
            { value: 'false', label: 'Inactive' },
        ] },
    ];

    const handleSubmit = async (e) => {
        e.preventDefault();
        setFormError('');
        setFormLoading(true);
        try {
            const payload = { ...formData, amount: parseFloat(formData.amount) };
            if (editingTemplate) {
                await update(editingTemplate.id, payload);
            } else {
                await create(payload);
            }
            setShowModal(false);
            resetForm();
            refetch();
            toast.success(editingTemplate ? 'Recurring expense updated successfully' : 'Recurring expense created successfully');
        } catch (error) {
            setFormError(extractErrorMessage(error, 'Failed to save recurring expense'));
        } finally {
            setFormLoading(false);
        }
    };

    const handleEdit = (template) => {
        setEditingTemplate(template);
        setFormData({
            name: template.name,
            category: template.category,
            amount: template.amount,
            start_date: template.start_date,
            note: template.note || '',
        });
        setShowModal(true);
    };

    const handleToggleActive = async (template) => {
        setTogglingId(template.id);
        try {
            await update(template.id, { is_active: !template.is_active });
            refetch();
            toast.success(template.is_active ? 'Marked as inactive' : 'Marked as active');
        } catch (error) {
            toast.error(extractErrorMessage(error, 'Failed to update status'));
        } finally {
            setTogglingId(null);
        }
    };

    const handleDelete = async (id) => {
        setDeleteLoading(true);
        try {
            await deleteTemplate(id);
            setDeleteConfirm(null);
            refetch();
            toast.success('Recurring expense deleted');
        } catch (error) {
            setDeleteConfirm(null);
            toast.error(extractErrorMessage(error, 'Failed to delete recurring expense'));
        } finally {
            setDeleteLoading(false);
        }
    };

    const columns = [
        { key: 'name', label: 'Name', render: (v) => <span className="font-medium text-neutral-900">{v}</span> },
        { key: 'category_name', label: 'Category' },
        { key: 'amount', label: 'Monthly Amount (PKR)', render: (v) => <span className="font-semibold text-info-600">Rs. {fmt(v)}</span> },
        { key: 'start_date', label: 'Start Date', render: (v) => new Date(v).toLocaleDateString() },
        {
            key: 'is_active',
            label: 'Status',
            render: (v, row) => (
                <Button 
                    size="sm"
                    variant={v ? 'success' : 'secondary'}
                    onClick={() => handleToggleActive(row)} 
                    disabled={togglingId === row.id}
                >
                    {v ? 'Active' : 'Inactive'}
                </Button>
            ),
        },
        {
            key: 'actions',
            label: 'Actions',
            width: '200px',
            render: (_v, row) => (
                <div className="flex items-center gap-2">
                    <button onClick={() => handleEdit(row)} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-primary-200 bg-primary-50 text-primary-700 hover:bg-primary-100 transition-colors text-sm font-medium min-h-[44px] sm:min-h-0">
                        <Pencil className="w-3.5 h-3.5" /> Edit
                    </button>
                    <button onClick={() => setDeleteConfirm(row)} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-error-200 bg-error-50 text-error-700 hover:bg-error-100 transition-colors text-sm font-medium min-h-[44px] sm:min-h-0">
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
                <p className="text-neutral-500 mt-2 max-w-sm">Only admins or superusers can view recurring expenses.</p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <BackLink to="/recurring-expenses">Back to Recurring Expenses</BackLink>
                    <h1 className="text-3xl font-bold text-neutral-900 mt-1">Recurring Expense Templates</h1>
                    <p className="text-neutral-500 mt-1 max-w-2xl">
                        Salaries, rent, and anything else that recurs monthly. Creating one here never moves cash by itself —
                        use Post Dues to assign a month, then record a payment against it.
                    </p>
                </div>
                <Button onClick={() => { resetForm(); setShowModal(true); }} icon={Plus}>Add Recurring Expense</Button>
            </div>

            <div className="flex gap-4">
                <Button variant="secondary" icon={SlidersHorizontal} onClick={() => setShowFilters(!showFilters)}>
                    {showFilters ? 'Hide Filters' : 'Show Filters'}
                </Button>
                {Object.keys(filters).length > 0 && (
                    <Button variant="secondary" onClick={handleResetFilters}>Clear Filters</Button>
                )}
            </div>
            {showFilters && (
                <FilterBar filters={filterConfig} onApply={handleApplyFilters} onReset={handleResetFilters} />
            )}

            {loading ? (
                <div className="flex items-center justify-center py-8">
                    <LoadingSpinner size="lg" />
                </div>
            ) : templates.length === 0 ? (
                <EmptyState
                    icon={<Repeat className="w-8 h-8 text-neutral-400" />}
                    title="No Recurring Expenses Yet"
                    description="Add a salary, rent, or subscription to get started."
                />
            ) : (
                <>
                    <Table columns={columns} data={templates} />
                    {meta.totalPages > 1 && (
                        <Pagination currentPage={meta.currentPage} totalPages={meta.totalPages} onPageChange={setPage} />
                    )}
                </>
            )}

            <Modal
                isOpen={showModal}
                onClose={() => { setShowModal(false); resetForm(); }}
                title={editingTemplate ? 'Edit Recurring Expense' : 'Add Recurring Expense'}
                size="lg"
            >
                <form onSubmit={handleSubmit} className="space-y-4">
                    <Input
                        label="Name"
                        value={formData.name}
                        onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                        placeholder="e.g. Ali Khan — Sales Staff Salary"
                        required
                    />
                    <Select
                        label="Category"
                        value={formData.category}
                        onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                        options={categories.map((c) => ({ value: c.id, label: c.name }))}
                        placeholder="Select a category"
                        required
                    />
                    <Input
                        label="Monthly Amount (PKR)"
                        type="number"
                        step="0.01"
                        min="0.01"
                        value={formData.amount}
                        onChange={(e) => setFormData({ ...formData, amount: e.target.value })}
                        required
                    />
                    <Input
                        label="Start Date"
                        type="date"
                        value={formData.start_date}
                        onChange={(e) => setFormData({ ...formData, start_date: e.target.value })}
                        required
                        disabled={!!editingTemplate}
                    />
                    <Input
                        label="Note"
                        value={formData.note}
                        onChange={(e) => setFormData({ ...formData, note: e.target.value })}
                        placeholder="Optional"
                    />

                    {formError && <InlineAlert variant="error" message={formError} />}

                    <div className="flex justify-end gap-3 pt-4">
                        <Button type="button" variant="secondary" onClick={() => { setShowModal(false); resetForm(); }}>
                            Cancel
                        </Button>
                        <Button type="submit" loading={formLoading}>
                            {editingTemplate ? 'Update' : 'Create'}
                        </Button>
                    </div>
                </form>
            </Modal>

            <ConfirmDialog
                isOpen={!!deleteConfirm}
                onClose={() => setDeleteConfirm(null)}
                onConfirm={() => handleDelete(deleteConfirm?.id)}
                loading={deleteLoading}
                title="Delete Recurring Expense"
                message={`Are you sure you want to delete "${deleteConfirm?.name}"? Past assignments and payments are unaffected — it just can't be assigned for future months anymore.`}
            />
        </div>
    );
};

export default RecurringExpenseTemplatesPage;
