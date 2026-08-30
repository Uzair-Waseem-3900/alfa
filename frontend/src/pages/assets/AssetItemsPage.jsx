import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Package, ShieldAlert, Info, AlertTriangle, SlidersHorizontal, X } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { useAssets, useAssetStats } from '../../hooks/useAssets';
import { assetsApi } from '../../services/assetsApi';
import { extractErrorMessage } from '../../utils/errorMessage';
import { todayLocalDate } from '../../utils/helpers';
import MethodSplitPicker, { isSplitBalanced } from '../../components/paymentMethods/MethodSplitPicker';
import Button from '../../components/ui/Button';
import Modal from '../../components/ui/Modal';
import Input from '../../components/ui/Input';
import Select from '../../components/ui/Select';
import Badge from '../../components/ui/Badge';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Table from '../../components/ui/Table';
import FilterBar from '../../components/ui/FilterBar';
import Pagination from '../../components/ui/Pagination';
import BackLink from '../../components/ui/BackLink';
import InlineAlert from '../../components/ui/InlineAlert';
import EmptyState from '../../components/ui/EmptyState';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const emptyFieldErrors = { name: '', category: '', cost: '', acquisition_date: '' };

const AssetItemsPage = () => {
    const { user } = useAuth();
    const { toast } = useToast();
    const navigate = useNavigate();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    // Disposed assets never appear on this page, under any filter — they
    // have their own dedicated Disposals page. is_disposed is force-merged
    // into every filter change below so it can never be overridden.
    const {
        data: assets, meta, page, setPage, loading, error: listError,
        filters, setFilters, refetch, create,
    } = useAssets({ is_disposed: 'false' });
    const { refetch: refetchStats } = useAssetStats();

    const [categories, setCategories] = useState([]);
    const [categoriesError, setCategoriesError] = useState('');
    const [showModal, setShowModal] = useState(false);
    const [formData, setFormData] = useState({
        name: '', category: '', acquisition_type: 'existing',
        cost: '', acquisition_date: todayLocalDate(), note: '',
    });
    const [formLoading, setFormLoading] = useState(false);
    const [formError, setFormError] = useState('');
    const [fieldErrors, setFieldErrors] = useState(emptyFieldErrors);
    const [methodAllocations, setMethodAllocations] = useState([]);
    const [splitError, setSplitError] = useState('');
    const [showFilters, setShowFilters] = useState(false);

    const loadCategories = () => {
        setCategoriesError('');
        assetsApi.categories.getAll({ page_size: 500 })
            .then((res) => setCategories(res?.results ?? res ?? []))
            .catch((error) => {
                console.error('Failed to load asset categories:', error);
                setCategoriesError(extractErrorMessage(error, 'Failed to load categories'));
            });
    };

    useEffect(() => {
        loadCategories();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const resetForm = () => {
        setFormData({
            name: '', category: '', acquisition_type: 'existing',
            cost: '', acquisition_date: todayLocalDate(), note: '',
        });
        setFormError('');
        setFieldErrors(emptyFieldErrors);
        setMethodAllocations([]);
        setSplitError('');
    };

    const handleAcquisitionTypeChange = (value) => {
        setFormData({ ...formData, acquisition_type: value });
        // Switching away from "new" drops any staged split — it's never sent
        // for an "existing" asset (no cash moves), so stale rows shouldn't linger.
        if (value !== 'new') {
            setMethodAllocations([]);
            setSplitError('');
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setFormError('');
        setFieldErrors(emptyFieldErrors);
        setSplitError('');
        setFormLoading(true);
        try {
            const payload = { ...formData, category: parseInt(formData.category), cost: parseFloat(formData.cost) };
            // Only "new" acquisitions move cash — "existing" assets never send
            // method_allocations at all.
            if (formData.acquisition_type === 'new') {
                payload.method_allocations = methodAllocations;
            }
            await create(payload);
            setShowModal(false);
            resetForm();
            refetch();
            refetchStats();
            toast.success('Asset registered successfully');
        } catch (error) {
            const data = error.response?.data;
            const fe = {
                name: Array.isArray(data?.name) ? data.name[0] : data?.name || '',
                category: Array.isArray(data?.category) ? data.category[0] : data?.category || '',
                cost: Array.isArray(data?.cost) ? data.cost[0] : data?.cost || '',
                acquisition_date: Array.isArray(data?.acquisition_date) ? data.acquisition_date[0] : data?.acquisition_date || '',
            };
            const methodError = data?.method_allocations || data?.splits;
            const hasFieldErrors = fe.name || fe.category || fe.cost || fe.acquisition_date;
            if (hasFieldErrors) {
                setFieldErrors(fe);
            }
            if (methodError) {
                setSplitError(Array.isArray(methodError) ? methodError[0] : methodError);
            }
            if (!hasFieldErrors && !methodError) {
                setFormError(extractErrorMessage(error, 'Failed to register asset'));
            }
        } finally {
            setFormLoading(false);
        }
    };

    // is_disposed is force-merged on every apply/reset — never overridable.
    const handleApplyFilters = (values) => setFilters({ ...values, is_disposed: 'false' });
    const handleResetFilters = () => setFilters({ is_disposed: 'false' });
    const handleRowClick = (row) => navigate(`/assets/items/${row.id}`);

    // "Clear Filters" only shows once the admin has actually diverged from
    // the default — not on first load.
    const isDefaultFilters = Object.keys(filters).length === 1 && filters.is_disposed === 'false';

    const filterConfig = [
        { name: 'category_id', label: 'Category', type: 'select', options: [
            { value: '', label: 'All' },
            ...categories.map((c) => ({ value: c.id, label: c.name })),
        ] },
        { name: 'acquisition_type', label: 'Acquisition', type: 'select', options: [
            { value: '', label: 'All' },
            { value: 'existing', label: 'Existing' },
            { value: 'new', label: 'New' },
        ] },
    ];

    const columns = [
        { key: 'name', label: 'Name' },
        { key: 'category_name', label: 'Category' },
        {
            key: 'acquisition_type',
            label: 'Acquisition',
            render: (v) => v === 'new'
                ? <Badge variant="info" size="sm">New</Badge>
                : <Badge size="sm">Existing</Badge>,
        },
        { key: 'cost', label: 'Cost (PKR)', render: (v) => `Rs. ${fmt(v)}` },
        {
            key: 'current_worth',
            label: 'Current Worth (PKR)',
            render: (v) => <span className="font-semibold text-purple-600">Rs. {fmt(v)}</span>,
        },
        { key: 'acquisition_date', label: 'Date', render: (v) => new Date(v).toLocaleDateString() },
    ];

    if (!isAdmin) {
        return (
            <div className="text-center py-16">
                <div className="w-16 h-16 rounded-full bg-error-50 flex items-center justify-center mx-auto mb-4">
                    <ShieldAlert className="w-8 h-8 text-error-500" />
                </div>
                <h2 className="text-2xl font-semibold text-neutral-900">Access Denied</h2>
                <p className="text-neutral-500 mt-2">Only admins or superusers can view assets.</p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <BackLink to="/assets">Back to Assets</BackLink>
                    <h1 className="text-3xl font-bold text-neutral-900 mt-2">Assets</h1>
                    <p className="text-neutral-500 mt-1">Every registered fixed asset</p>
                </div>
                <Button
                    onClick={() => { resetForm(); setShowModal(true); }}
                    disabled={categories.length === 0}
                >
                    Add Asset
                </Button>
            </div>

            {categoriesError && (
                <InlineAlert variant="error" message={categoriesError} onRetry={loadCategories} />
            )}

            {categories.length === 0 && !categoriesError && (
                <InlineAlert
                    variant="warning"
                    message={<>Create an <Link to="/assets/categories" className="underline font-semibold">asset category</Link> first before registering an asset.</>}
                />
            )}

            {listError && (
                <InlineAlert variant="error" message={listError} onRetry={refetch} />
            )}

            <div className="space-y-4">
                <div className="flex gap-3">
                    <Button variant="secondary" icon={showFilters ? X : SlidersHorizontal} onClick={() => setShowFilters(!showFilters)}>
                        {showFilters ? 'Hide Filters' : 'Show Filters'}
                    </Button>
                    {!isDefaultFilters && (
                        <Button variant="secondary" onClick={handleResetFilters}>Clear Filters</Button>
                    )}
                </div>
                {showFilters && (
                    <FilterBar filters={filterConfig} onApply={handleApplyFilters} onReset={handleResetFilters} />
                )}
            </div>

            {loading ? (
                <div className="flex items-center justify-center py-12">
                    <LoadingSpinner size="lg" />
                </div>
            ) : assets.length === 0 ? (
                <EmptyState
                    icon={<Package className="w-8 h-8 text-neutral-400" />}
                    title="No Assets Registered Yet"
                    description="Add one to start tracking its worth over time."
                />
            ) : (
                <>
                    <Table columns={columns} data={assets} onRowClick={handleRowClick} />
                    {meta.totalPages > 1 && (
                        <Pagination currentPage={meta.currentPage} totalPages={meta.totalPages} onPageChange={setPage} />
                    )}
                </>
            )}

            <Modal
                isOpen={showModal}
                onClose={() => { setShowModal(false); resetForm(); }}
                title="Add Asset"
                size="lg"
            >
                <form onSubmit={handleSubmit} className="space-y-4">
                    <Input
                        label="Name"
                        value={formData.name}
                        onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                        placeholder="e.g. Delivery Bike, Front Shelving"
                        error={fieldErrors.name}
                        required
                    />
                    <Select
                        label="Category"
                        value={formData.category}
                        onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                        options={categories.map((c) => ({ value: c.id, label: `${c.name} (${c.valuation_method})` }))}
                        error={fieldErrors.category}
                        required
                    />
                    <Select
                        label="Acquisition Type"
                        value={formData.acquisition_type}
                        onChange={(e) => handleAcquisitionTypeChange(e.target.value)}
                        options={[
                            { value: 'existing', label: 'Existing — already owned, no cash movement' },
                            { value: 'new', label: 'New — purchased now, deducts cash in hand' },
                        ]}
                        required
                    />
                    <Input
                        label="Cost (PKR)"
                        type="number"
                        step="0.01"
                        min="0.01"
                        value={formData.cost}
                        onChange={(e) => setFormData({ ...formData, cost: e.target.value })}
                        error={fieldErrors.cost}
                        required
                    />
                    <Input
                        label={formData.acquisition_type === 'existing' ? 'Original Acquisition Date' : 'Purchase Date'}
                        type="date"
                        value={formData.acquisition_date}
                        onChange={(e) => setFormData({ ...formData, acquisition_date: e.target.value })}
                        error={fieldErrors.acquisition_date}
                        required
                    />
                    <Input
                        label="Note"
                        value={formData.note}
                        onChange={(e) => setFormData({ ...formData, note: e.target.value })}
                        placeholder="Optional"
                    />

                    {formData.acquisition_type === 'existing' ? (
                        <div className="flex items-start gap-2.5 p-3 bg-info-50 rounded-xl">
                            <Info className="w-4 h-4 text-info-600 flex-shrink-0 mt-0.5" />
                            <p className="text-sm text-info-700">
                                No cash movement. The system will back-fill depreciation history from the acquisition date to today automatically.
                            </p>
                        </div>
                    ) : (
                        formData.cost && parseFloat(formData.cost) > 0 && (
                            <div className="flex items-start gap-2.5 p-3 bg-warning-50 rounded-xl">
                                <AlertTriangle className="w-4 h-4 text-warning-600 flex-shrink-0 mt-0.5" />
                                <p className="text-sm text-warning-700">
                                    This will deduct <strong>Rs. {fmt(formData.cost)}</strong> from cash in hand.
                                </p>
                            </div>
                        )
                    )}

                    {formData.acquisition_type === 'new' && (
                        <MethodSplitPicker
                            totalAmount={formData.cost}
                            value={methodAllocations}
                            onChange={setMethodAllocations}
                            error={splitError}
                        />
                    )}

                    {formError && <InlineAlert variant="error" message={formError} />}

                    <div className="flex justify-end gap-3 pt-4">
                        <Button type="button" variant="secondary" onClick={() => { setShowModal(false); resetForm(); }}>
                            Cancel
                        </Button>
                        <Button
                            type="submit"
                            loading={formLoading}
                            disabled={formData.acquisition_type === 'new' && !isSplitBalanced(formData.cost, methodAllocations)}
                        >
                            Register Asset
                        </Button>
                    </div>
                </form>
            </Modal>
        </div>
    );
};

export default AssetItemsPage;
