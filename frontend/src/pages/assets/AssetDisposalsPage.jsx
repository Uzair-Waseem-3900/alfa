import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Trash2, ShieldAlert, SlidersHorizontal, X } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useAssetDisposals } from '../../hooks/useAssets';
import { assetsApi } from '../../services/assetsApi';
import { extractErrorMessage } from '../../utils/errorMessage';
import Button from '../../components/ui/Button';
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

const AssetDisposalsPage = () => {
    const { user } = useAuth();
    const navigate = useNavigate();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const {
        data: disposals, meta, page, setPage, loading, error: listError, filters, setFilters, refetch,
    } = useAssetDisposals();

    const [showFilters, setShowFilters] = useState(false);
    const [categories, setCategories] = useState([]);
    const [categoriesError, setCategoriesError] = useState('');

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

    const handleApplyFilters = (values) => setFilters(values);
    const handleResetFilters = () => setFilters({});
    const handleRowClick = (row) => navigate(`/assets/items/${row.asset}`);

    const filterConfig = [
        { name: 'disposal_type', label: 'Type', type: 'select', options: [
            { value: '', label: 'All' },
            { value: 'scrapped', label: 'Scrapped' },
            { value: 'sold', label: 'Sold' },
        ] },
        { name: 'category_id', label: 'Category', type: 'select', options: [
            { value: '', label: 'All' },
            ...categories.map((c) => ({ value: c.id, label: c.name })),
        ] },
    ];

    const columns = [
        { key: 'disposal_date', label: 'Date', render: (v) => new Date(v).toLocaleDateString() },
        { key: 'asset_name', label: 'Asset' },
        { key: 'category_name', label: 'Category' },
        {
            key: 'disposal_type',
            label: 'Type',
            render: (v) => v === 'sold'
                ? <Badge variant="info" size="sm">Sold</Badge>
                : <Badge variant="warning" size="sm">Scrapped</Badge>,
        },
        { key: 'worth_at_disposal', label: 'Worth at Disposal', render: (v) => `Rs. ${fmt(v)}` },
        { key: 'sale_amount', label: 'Sale Amount', render: (v) => v != null ? `Rs. ${fmt(v)}` : <span className="text-neutral-300">—</span> },
        {
            key: 'gain_loss',
            label: 'Gain / Loss',
            render: (v) => v == null
                ? <span className="text-neutral-300">—</span>
                : (
                    <span className={parseFloat(v) >= 0 ? 'text-success-600 font-semibold' : 'text-error-600 font-semibold'}>
                        {parseFloat(v) >= 0 ? '+' : ''}Rs. {fmt(v)}
                    </span>
                ),
        },
        { key: 'reason', label: 'Reason', render: (v) => v || <span className="text-neutral-300">—</span> },
    ];

    if (!isAdmin) {
        return (
            <div className="text-center py-16">
                <div className="w-16 h-16 rounded-full bg-error-50 flex items-center justify-center mx-auto mb-4">
                    <ShieldAlert className="w-8 h-8 text-error-500" />
                </div>
                <h2 className="text-2xl font-semibold text-neutral-900">Access Denied</h2>
                <p className="text-neutral-500 mt-2">Only admins or superusers can view asset disposals.</p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div>
                <BackLink to="/assets">Back to Assets</BackLink>
                <h1 className="text-3xl font-bold text-neutral-900 mt-2">Asset Disposals</h1>
                <p className="text-neutral-500 mt-1">Audit trail of every asset that's been scrapped or sold</p>
            </div>

            {categoriesError && (
                <InlineAlert variant="warning" message={categoriesError} onRetry={loadCategories} />
            )}
            {listError && (
                <InlineAlert variant="error" message={listError} onRetry={refetch} />
            )}

            <div className="flex gap-3">
                <Button variant="secondary" icon={showFilters ? X : SlidersHorizontal} onClick={() => setShowFilters(!showFilters)}>
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
                <div className="flex items-center justify-center py-12">
                    <LoadingSpinner size="lg" />
                </div>
            ) : disposals.length === 0 ? (
                <EmptyState
                    icon={<Trash2 className="w-8 h-8 text-neutral-400" />}
                    title="No Disposals Yet"
                    description="Disposed assets will appear here."
                />
            ) : (
                <>
                    <Table columns={columns} data={disposals} onRowClick={handleRowClick} />
                    {meta.totalPages > 1 && (
                        <Pagination currentPage={meta.currentPage} totalPages={meta.totalPages} onPageChange={setPage} />
                    )}
                </>
            )}
        </div>
    );
};

export default AssetDisposalsPage;
