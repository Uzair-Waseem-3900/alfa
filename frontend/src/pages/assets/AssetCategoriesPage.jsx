import { useState } from 'react';
import { Tag, Percent, ShieldAlert, Pencil } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { useAssetCategories } from '../../hooks/useAssets';
import { extractErrorMessage } from '../../utils/errorMessage';
import Button from '../../components/ui/Button';
import BackLink from '../../components/ui/BackLink';
import Modal from '../../components/ui/Modal';
import Input from '../../components/ui/Input';
import Select from '../../components/ui/Select';
import Badge from '../../components/ui/Badge';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Table from '../../components/ui/Table';
import Pagination from '../../components/ui/Pagination';
import InlineAlert from '../../components/ui/InlineAlert';
import EmptyState from '../../components/ui/EmptyState';

const methodBadge = (method) => {
    if (method === 'depreciation') return <Badge variant="warning" size="sm">Depreciation</Badge>;
    if (method === 'revaluation') return <Badge variant="info" size="sm">Revaluation</Badge>;
    return <Badge size="sm">None</Badge>;
};

const emptyFieldErrors = { name: '', depreciation_rate: '' };

const AssetCategoriesPage = () => {
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const {
        data: categories, meta, page, setPage, loading, error: listError,
        refetch, create, update,
    } = useAssetCategories();

    const [showModal, setShowModal] = useState(false);
    const [editingCategory, setEditingCategory] = useState(null);
    const [formData, setFormData] = useState({ name: '', valuation_method: 'depreciation', depreciation_rate: '' });
    const [formLoading, setFormLoading] = useState(false);
    const [formError, setFormError] = useState('');
    const [fieldErrors, setFieldErrors] = useState(emptyFieldErrors);

    const resetForm = () => {
        setFormData({ name: '', valuation_method: 'depreciation', depreciation_rate: '' });
        setEditingCategory(null);
        setFormError('');
        setFieldErrors(emptyFieldErrors);
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setFormError('');
        setFieldErrors(emptyFieldErrors);
        setFormLoading(true);
        try {
            if (editingCategory) {
                const payload = { name: formData.name };
                if (editingCategory.valuation_method === 'depreciation') {
                    payload.depreciation_rate = parseFloat(formData.depreciation_rate) / 100;
                }
                await update(editingCategory.id, payload);
                toast.success('Category updated successfully');
            } else {
                const payload = { name: formData.name, valuation_method: formData.valuation_method };
                if (formData.valuation_method === 'depreciation') {
                    payload.depreciation_rate = parseFloat(formData.depreciation_rate) / 100;
                }
                await create(payload);
                toast.success('Category created successfully');
            }
            setShowModal(false);
            resetForm();
            refetch();
        } catch (error) {
            const data = error.response?.data;
            const nameError = Array.isArray(data?.name) ? data.name[0] : data?.name;
            const rateError = Array.isArray(data?.depreciation_rate) ? data.depreciation_rate[0] : data?.depreciation_rate;
            if (nameError || rateError) {
                setFieldErrors({ name: nameError || '', depreciation_rate: rateError || '' });
            } else {
                setFormError(extractErrorMessage(error, 'Failed to save category'));
            }
        } finally {
            setFormLoading(false);
        }
    };

    const handleEdit = (category) => {
        setEditingCategory(category);
        setFormData({
            name: category.name,
            valuation_method: category.valuation_method,
            depreciation_rate: category.valuation_method === 'depreciation'
                ? (parseFloat(category.depreciation_rate) * 100).toString()
                : '',
        });
        setFieldErrors(emptyFieldErrors);
        setFormError('');
        setShowModal(true);
    };

    const columns = [
        { key: 'name', label: 'Name' },
        { key: 'valuation_method', label: 'Method', render: (v) => methodBadge(v) },
        {
            key: 'depreciation_rate',
            label: 'Rate',
            render: (v, row) => row.valuation_method === 'depreciation'
                ? `${(parseFloat(v) * 100).toFixed(2)}%`
                : <span className="text-neutral-300">—</span>,
        },
        {
            key: 'actions',
            label: 'Actions',
            width: '100px',
            render: (_v, row) => (
                <button
                    onClick={() => handleEdit(row)}
                    className="inline-flex items-center gap-1.5 text-primary-600 hover:text-primary-700 text-sm font-medium min-h-[44px] sm:min-h-0"
                >
                    <Pencil className="w-3.5 h-3.5" />
                    Edit
                </button>
            ),
        },
    ];

    if (!isAdmin) {
        return (
            <div className="text-center py-16">
                <div className="w-16 h-16 rounded-full bg-error-50 flex items-center justify-center mx-auto mb-4">
                    <ShieldAlert className="w-8 h-8 text-error-500" />
                </div>
                <h2 className="text-2xl font-semibold text-neutral-900">Access Denied</h2>
                <p className="text-neutral-500 mt-2">Only admins or superusers can view asset categories.</p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <BackLink to="/assets">Back to Assets</BackLink>
                    <h1 className="text-3xl font-bold text-neutral-900 mt-2">Asset Categories</h1>
                    <p className="text-neutral-500 mt-1 max-w-2xl">
                        The valuation method (Depreciation/Revaluation/None) is locked once a category is created —
                        only the name and rate can be changed later.
                    </p>
                </div>
                <Button onClick={() => { resetForm(); setShowModal(true); }}>Add Category</Button>
            </div>

            {listError && (
                <InlineAlert variant="error" message={listError} onRetry={refetch} />
            )}

            {loading ? (
                <div className="flex items-center justify-center py-12">
                    <LoadingSpinner size="lg" />
                </div>
            ) : categories.length === 0 ? (
                <EmptyState
                    icon={<Tag className="w-8 h-8 text-neutral-400" />}
                    title="No Categories Yet"
                    description="Add one to start registering assets."
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
                        placeholder="e.g. Furniture & Fixtures"
                        error={fieldErrors.name}
                        required
                    />

                    {editingCategory ? (
                        <div>
                            <p className="text-sm font-medium text-neutral-700 mb-1.5">Valuation Method</p>
                            <p className="text-sm text-neutral-500 flex items-center gap-2">{methodBadge(editingCategory.valuation_method)} — cannot be changed</p>
                        </div>
                    ) : (
                        <Select
                            label="Valuation Method"
                            value={formData.valuation_method}
                            onChange={(e) => setFormData({ ...formData, valuation_method: e.target.value })}
                            options={[
                                { value: 'depreciation', label: 'Depreciation — wears out over time (reducing balance)' },
                                { value: 'revaluation', label: 'Revaluation — value set manually (e.g. Land)' },
                                { value: 'none', label: 'None — never changes' },
                            ]}
                            required
                        />
                    )}

                    {formData.valuation_method === 'depreciation' && (
                        <Input
                            label="Annual Depreciation Rate (%)"
                            type="number"
                            step="0.01"
                            min="0.01"
                            max="100"
                            icon={Percent}
                            value={formData.depreciation_rate}
                            onChange={(e) => setFormData({ ...formData, depreciation_rate: e.target.value })}
                            placeholder="e.g. 15 for FBR furniture/vehicles, 30 for computers"
                            error={fieldErrors.depreciation_rate}
                            required
                        />
                    )}

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
        </div>
    );
};

export default AssetCategoriesPage;
