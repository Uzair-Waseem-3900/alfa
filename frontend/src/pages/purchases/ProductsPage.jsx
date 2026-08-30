import { useState, useEffect } from 'react';
import { Plus, SlidersHorizontal, X, Pencil, Trash2, PackageSearch } from 'lucide-react';
import { useCRUD } from '../../hooks/usePurchases';
import { purchasesApi } from '../../services/purchasesApi';
import Table from '../../components/ui/Table';
import Button from '../../components/ui/Button';
import Modal from '../../components/ui/Modal';
import Input from '../../components/ui/Input';
import Select from '../../components/ui/Select';
import SearchBar from '../../components/ui/SearchBar';
import FilterBar from '../../components/ui/FilterBar';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Badge from '../../components/ui/Badge';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import Pagination from '../../components/ui/Pagination';
import EmptyState from '../../components/ui/EmptyState';
import InlineAlert from '../../components/ui/InlineAlert';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { extractErrorMessage } from '../../utils/errorMessage';

const ProductsPage = () => {
    const { user } = useAuth();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';
    const { toast } = useToast();

    const { data, meta, page, setPage, loading, error, filters, setFilters, create, update, delete: deleteProduct, refetch } = useCRUD(
        purchasesApi.products,
        { search: '', category: '' }
    );

    const [categories, setCategories] = useState([]);
    const [searchTerm, setSearchTerm] = useState('');
    const [categoryFilter, setCategoryFilter] = useState('');
    const [showFilters, setShowFilters] = useState(false);
    const [activeFilters, setActiveFilters] = useState({});
    const [showModal, setShowModal] = useState(false);
    const [editingProduct, setEditingProduct] = useState(null);
    const [formData, setFormData] = useState({
        name: '',
        code: '',
        category: '',
    });
    const [formLoading, setFormLoading] = useState(false);
    const [formError, setFormError] = useState('');
    const [deleteConfirm, setDeleteConfirm] = useState(null);
    const [deleting, setDeleting] = useState(false);

    useEffect(() => {
        loadLookups();
    }, []);

    const loadLookups = async () => {
        try {
            // page_size override — dropdown needs every category, not
            // just the first paginated page.
            const catsRes = await purchasesApi.categories.getAll({ page_size: 500 });
            const cats = catsRes.results || catsRes;
            setCategories(cats.filter(c => !c.is_deleted));
        } catch (error) {
            console.error('Failed to load lookups:', error);
            toast.error(extractErrorMessage(error, 'Failed to load categories'));
        }
    };

    // Search now goes to the backend (see handleSearch) — only category
    // is still narrowed client-side, over whatever page the backend returned.
    const filteredData = data.filter(item => {
        let matches = true;
        const catId = activeFilters.category || categoryFilter;
        if (catId) {
            matches = matches && item.category?.id === parseInt(catId);
        }
        return matches;
    });

    const handleSearch = (value) => {
        setSearchTerm(value);
        setFilters({ ...filters, search: value });
    };

    const handleApplyFilters = (filterValues) => {
        setActiveFilters(filterValues);
        setCategoryFilter(filterValues.category || '');
    };

    const handleResetFilters = () => {
        setActiveFilters({});
        setCategoryFilter('');
        setSearchTerm('');
        setFilters({ ...filters, search: '' });
    };

    const columns = [
        { key: 'code', label: 'Code', width: '120px' },
        { key: 'name', label: 'Name' },
        {
            key: 'category',
            label: 'Category',
            render: (value) => value?.name || 'N/A'
        },
        {
            key: 'is_deleted',
            label: 'Status',
            render: (value) => (
                <Badge variant={value ? 'error' : 'success'}>
                    {value ? 'Deleted' : 'Active'}
                </Badge>
            ),
        },
        {
            key: 'actions',
            label: 'Actions',
            width: '120px',
            render: (_, row) => isAdmin && !row.is_deleted && (
                <div className="flex items-center gap-1">
                    <button
                        onClick={(e) => {
                            e.stopPropagation();
                            handleEdit(row);
                        }}
                        title="Edit product"
                        className="p-2 min-w-[36px] min-h-[36px] flex items-center justify-center rounded-lg text-neutral-500 hover:text-primary-600 hover:bg-primary-50 transition-colors"
                    >
                        <Pencil className="w-4 h-4" />
                    </button>
                    <button
                        onClick={(e) => {
                            e.stopPropagation();
                            setDeleteConfirm(row);
                        }}
                        title="Delete product"
                        className="p-2 min-w-[36px] min-h-[36px] flex items-center justify-center rounded-lg text-neutral-500 hover:text-error-600 hover:bg-error-50 transition-colors"
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
                category: parseInt(formData.category),
            };
            if (editingProduct) {
                await update(editingProduct.id, submitData);
                toast.success('Product updated successfully');
            } else {
                await create(submitData);
                toast.success('Product created successfully');
            }
            setShowModal(false);
            resetForm();
        } catch (error) {
            console.error('Failed to save product:', error);
            setFormError(extractErrorMessage(error, 'Failed to save product'));
        } finally {
            setFormLoading(false);
        }
    };

    const handleDelete = async (id) => {
        setDeleting(true);
        try {
            await deleteProduct(id);
            toast.success('Product deleted successfully');
            setDeleteConfirm(null);
        } catch (error) {
            console.error('Failed to delete product:', error);
            toast.error(extractErrorMessage(error, 'Failed to delete product'));
        } finally {
            setDeleting(false);
        }
    };

    const handleEdit = (product) => {
        setEditingProduct(product);
        setFormData({
            name: product.name,
            code: product.code,
            category: product.category?.id || '',
        });
        setShowModal(true);
    };

    const resetForm = () => {
        setFormData({ name: '', code: '', category: '' });
        setEditingProduct(null);
        setFormError('');
    };

    if (loading) {
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
                    <h1 className="text-3xl font-bold text-neutral-900">Products</h1>
                    <p className="text-neutral-500 mt-1">Manage products and inventory</p>
                </div>
                {isAdmin && (
                    <Button
                        onClick={() => {
                            resetForm();
                            setShowModal(true);
                        }}
                        icon={Plus}
                    >
                        Add Product
                    </Button>
                )}
            </div>

            {error && (
                <InlineAlert variant="error" message={error} onRetry={refetch} />
            )}

            <div className="space-y-4">
                <div className="flex flex-col sm:flex-row gap-3">
                    <SearchBar
                        onSearch={handleSearch}
                        placeholder="Search products..."
                        className="flex-1"
                    />
                    <div className="flex gap-3">
                        <Button
                            variant="secondary"
                            onClick={() => setShowFilters(!showFilters)}
                            icon={SlidersHorizontal}
                            className="flex-1 sm:flex-none"
                        >
                            {showFilters ? 'Hide Filters' : 'Filters'}
                        </Button>
                        {(Object.keys(activeFilters).length > 0 || searchTerm) && (
                            <Button variant="secondary" onClick={handleResetFilters} icon={X} className="flex-1 sm:flex-none">
                                Clear
                            </Button>
                        )}
                    </div>
                </div>

                {showFilters && (
                    <FilterBar
                        filters={[
                            {
                                name: 'category',
                                label: 'Category',
                                type: 'select',
                                options: [
                                    { value: '', label: 'All Categories' },
                                    ...categories.map(c => ({ value: c.id, label: c.name })),
                                ],
                            },
                        ]}
                        onApply={handleApplyFilters}
                        onReset={handleResetFilters}
                    />
                )}
            </div>

            {filteredData.length === 0 ? (
                <EmptyState
                    title="No products found"
                    description="Try adjusting your search or filters, or add a new product."
                    icon={<PackageSearch className="w-8 h-8 text-neutral-400" />}
                />
            ) : (
                <Table
                    columns={columns}
                    data={filteredData}
                />
            )}

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
                title={editingProduct ? 'Edit Product' : 'Create Product'}
            >
                <form onSubmit={handleSubmit} className="space-y-4">
                    {formError && (
                        <InlineAlert variant="error" message={formError} />
                    )}
                    <Input
                        label="Name"
                        value={formData.name}
                        onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                        placeholder="Enter product name"
                        required
                    />
                    <Input
                        label="Code"
                        value={formData.code}
                        onChange={(e) => setFormData({ ...formData, code: e.target.value.toUpperCase() })}
                        placeholder="Enter unique code"
                        required
                    />
                    <Select
                        label="Category"
                        value={formData.category}
                        onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                        options={categories.map(c => ({ value: c.id, label: c.name }))}
                        placeholder="Select category"
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
                            {editingProduct ? 'Update' : 'Create'}
                        </Button>
                    </div>
                </form>
            </Modal>

            <ConfirmDialog
                isOpen={!!deleteConfirm}
                onClose={() => setDeleteConfirm(null)}
                onConfirm={() => handleDelete(deleteConfirm?.id)}
                title="Delete Product"
                message={`Are you sure you want to delete "${deleteConfirm?.name}"? This action cannot be undone.`}
                confirmText="Delete"
                loading={deleting}
            />
        </div>
    );
};

export default ProductsPage;