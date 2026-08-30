import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { extractErrorMessage } from '../../utils/errorMessage';
import { purchasesApi } from '../../services/purchasesApi';
import { usePaginatedList } from '../../hooks/usePaginatedList';
import Table from '../../components/ui/Table';
import SearchBar from '../../components/ui/SearchBar';
import Button from '../../components/ui/Button';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Badge from '../../components/ui/Badge';
import Card from '../../components/ui/Card';
import Modal from '../../components/ui/Modal';
import FilterBar from '../../components/ui/FilterBar';
import Pagination from '../../components/ui/Pagination';
import EmptyState from '../../components/ui/EmptyState';

const InventoryPage = () => {
    const navigate = useNavigate();
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const [searchTerm, setSearchTerm] = useState('');
    const [categories, setCategories] = useState([]);
    const [showFilters, setShowFilters] = useState(false);
    const [totalStock, setTotalStock] = useState(0);
    const [stats, setStats] = useState(null);
    // Which list the table shows: 'all' | 'low' | 'out'. Driven by clicking
    // the Low Stock / Out of Stock cards — each maps to its own backend
    // breakdown endpoint.
    const [stockView, setStockView] = useState('all');

    // Detail modal state
    const [showDetailModal, setShowDetailModal] = useState(false);
    const [selectedProduct, setSelectedProduct] = useState(null);
    const [productDetail, setProductDetail] = useState(null);
    const [detailLoading, setDetailLoading] = useState(false);
    // Per-shelf breakdown for the selected product (which shelves hold it,
    // and how much) — a product can now span multiple shelves.
    const [shelfBreakdown, setShelfBreakdown] = useState([]);
    const [shelfBreakdownLoading, setShelfBreakdownLoading] = useState(false);

    // Search is routed through the same query params as the category
    // filter — the backend supports search/category on all three
    // inventory list endpoints (all / low-stock / out-of-stock). Shelf is
    // no longer a product-level filter here (a product can now span
    // multiple shelves) — see the Shelves page for per-shelf breakdowns.
    const fetchInventoryPage = (params) => {
        const p = { ...params };
        if (searchTerm) p.search = searchTerm;
        if (stockView === 'low') return purchasesApi.inventory.getLowStock(p);
        if (stockView === 'out') return purchasesApi.inventory.getOutOfStock(p);
        return purchasesApi.inventory.getAll(p);
    };

    const {
        data: inventory, meta, page, setPage, loading,
        filters, setFilters,
    } = usePaginatedList(fetchInventoryPage, {}, 25, [searchTerm, stockView]);

    useEffect(() => {
        loadLookups();
        loadStats();
    }, []);

    // O(1) stats read off the backend singleton — always whole-inventory
    // numbers, independent of the active search/filters/breakdown view.
    const loadStats = async () => {
        try {
            const data = await purchasesApi.inventory.getStats();
            setStats(data);
        } catch (error) {
            console.error('Failed to load inventory stats:', error);
            toast.error(extractErrorMessage(error, 'Failed to load inventory stats'));
        }
    };

    // Toggle a breakdown view: click again (or click Total Products) to
    // return to the full list.
    const handleCardClick = (view) => {
        setStockView(current => (current === view ? 'all' : view));
        setPage(1);
    };

    // "Total Stock" (sum of quantity across the full filtered set) has no
    // backend stats equivalent (the stats block only has total_products /
    // low_stock / out_of_stock), so it's computed from a dedicated
    // page_size:500 fetch mirroring the same filters — same workaround
    // pattern used elsewhere for "need the full list, not just one page".
    useEffect(() => {
        let cancelled = false;
        const computeTotalStock = async () => {
            try {
                const params = { ...filters, page_size: 500 };
                if (searchTerm) params.search = searchTerm;
                const res = await purchasesApi.inventory.getAll(params);
                const items = res?.results || res || [];
                const sum = items.reduce((s, item) => s + (parseFloat(item.quantity) || 0), 0);
                if (!cancelled) setTotalStock(sum);
            } catch (error) {
                if (!cancelled) setTotalStock(0);
            }
        };
        computeTotalStock();
        return () => { cancelled = true; };
    }, [filters, searchTerm]);

    const loadLookups = async () => {
        try {
            // page_size override — dropdown needs every category, not
            // just one paginated page of them.
            const catsRes = await purchasesApi.categories.getAll({ page_size: 500 });
            const cats = catsRes?.results || catsRes || [];
            setCategories(cats.filter(c => !c.is_deleted));
        } catch (error) {
            console.error('Failed to load lookups:', error);
            toast.error(extractErrorMessage(error, 'Failed to load categories'));
        }
    };

    const handleSearch = (value) => {
        setSearchTerm(value);
        setPage(1);
    };

    const handleApplyFilters = (filterValues) => {
        setFilters(filterValues);
    };

    const handleResetFilters = () => {
        setFilters({});
        setSearchTerm('');
    };

    const filterConfig = [
        {
            name: 'category',
            label: 'Category',
            type: 'select',
            options: categories.map(c => ({ value: c.id, label: c.name })),
        },
    ];

    const handleRowClick = async (row) => {
        // Get the product ID from the row
        const productId = row.product?.id;
        if (!productId) return;

        setSelectedProduct(row);
        setShowDetailModal(true);
        setDetailLoading(true);
        setShelfBreakdownLoading(true);
        try {
            const detail = await purchasesApi.inventory.getByProduct(productId);
            setProductDetail(detail);
        } catch (error) {
            console.error('Failed to fetch product details:', error);
            toast.error(extractErrorMessage(error, 'Failed to load product details'));
            setProductDetail(null);
        } finally {
            setDetailLoading(false);
        }
        try {
            const shelves = await purchasesApi.shelves.getCandidates(productId);
            setShelfBreakdown(shelves?.results || shelves || []);
        } catch (error) {
            console.error('Failed to fetch shelf breakdown:', error);
            toast.error(extractErrorMessage(error, 'Failed to load shelf breakdown'));
            setShelfBreakdown([]);
        } finally {
            setShelfBreakdownLoading(false);
        }
    };

    // Summary stats come from the dedicated O(1) stats endpoint (stored
    // counters), not from scanning the list — global numbers by design.
    const totalProducts = stats?.total_products ?? 0;
    const lowStockItems = stats?.low_stock_count ?? 0;
    const outOfStockItems = stats?.out_of_stock_count ?? 0;

    const columns = [
        {
            key: 'product',
            label: 'Product Code',
            render: (value) => value?.code || 'N/A'
        },
        {
            key: 'product',
            label: 'Product Name',
            render: (value) => value?.name || 'N/A'
        },
        {
            key: 'product',
            label: 'Category',
            render: (value) => value?.category?.name || 'N/A'
        },
        {
            key: 'quantity',
            label: 'Quantity',
            render: (value) => {
                const num = typeof value === 'string' ? parseFloat(value) : value;
                return (
                    <span className={`font-semibold ${num <= 0 ? 'text-error-600' : num <= 5 ? 'text-warning-600' : 'text-success-600'}`}>
                        {isNaN(num) ? '0' : num}
                    </span>
                );
            }
        },
        {
            key: 'last_updated_at',
            label: 'Last Updated',
            render: (value) => value ? new Date(value).toLocaleString() : 'N/A'
        },
    ];

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
                    <h1 className="text-3xl font-bold text-neutral-900">Inventory</h1>
                    <p className="text-neutral-500 mt-1">View current inventory levels across all products</p>
                    <p className="text-sm text-neutral-400 mt-1">Click on any row to view detailed product information</p>
                </div>
                {isAdmin && (
                    <div className="flex flex-wrap gap-3">
                        <Button
                            variant="secondary"
                            onClick={() => navigate('/purchases/lost-inventory/records')}
                            icon={({ className }) => (
                                <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17v-6h6v6m-9 4h12a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v14a2 2 0 002 2z" />
                                </svg>
                            )}
                        >
                            Lost Inventory Records
                        </Button>
                        <Button
                            onClick={() => navigate('/purchases/lost-inventory')}
                            icon={({ className }) => (
                                <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2z" />
                                </svg>
                            )}
                        >
                            Manage Inventory
                        </Button>
                    </div>
                )}
            </div>

            {/* Summary Cards — Low Stock / Out of Stock are clickable and
                switch the table to that breakdown list; click again (or
                Total Products) to go back to the full list. */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <Card
                    className={`p-4 cursor-pointer transition-shadow hover:shadow-md ${stockView === 'all' ? 'ring-2 ring-primary-500' : ''}`}
                    onClick={() => handleCardClick('all')}
                >
                    <p className="text-sm text-neutral-500">Total Products</p>
                    <p className="text-2xl font-bold text-neutral-900">{totalProducts}</p>
                </Card>
                <Card className="p-4">
                    <p className="text-sm text-neutral-500">Total Stock</p>
                    <p className="text-2xl font-bold text-neutral-900">{totalStock}</p>
                </Card>
                <Card
                    className={`p-4 cursor-pointer transition-shadow hover:shadow-md ${stockView === 'low' ? 'ring-2 ring-warning-500' : ''}`}
                    onClick={() => handleCardClick('low')}
                >
                    <p className="text-sm text-neutral-500">Low Stock (≤ 5)</p>
                    <p className="text-2xl font-bold text-warning-600">{lowStockItems}</p>
                    <p className="text-xs text-neutral-400 mt-1">Click to view breakdown</p>
                </Card>
                <Card
                    className={`p-4 cursor-pointer transition-shadow hover:shadow-md ${stockView === 'out' ? 'ring-2 ring-error-500' : ''}`}
                    onClick={() => handleCardClick('out')}
                >
                    <p className="text-sm text-neutral-500">Out of Stock</p>
                    <p className="text-2xl font-bold text-error-600">{outOfStockItems}</p>
                    <p className="text-xs text-neutral-400 mt-1">Click to view breakdown</p>
                </Card>
            </div>

            {stockView !== 'all' && (
                <div className={`flex items-center justify-between rounded-lg px-4 py-2 ${stockView === 'low' ? 'bg-warning-50 text-warning-700' : 'bg-error-50 text-error-700'}`}>
                    <p className="text-sm font-medium">
                        Showing {stockView === 'low' ? 'low stock' : 'out of stock'} products only
                    </p>
                    <button
                        className="text-sm font-semibold underline"
                        onClick={() => handleCardClick(stockView)}
                    >
                        Show all
                    </button>
                </div>
            )}

            {/* Filters */}
            <div className="space-y-4">
                <div className="flex gap-4">
                    <div className="flex-1">
                        <SearchBar
                            onSearch={handleSearch}
                            placeholder="Search products by name or code..."
                            className="w-full"
                        />
                    </div>
                    <Button
                        variant="secondary"
                        onClick={() => setShowFilters(!showFilters)}
                        icon={({ className }) => (
                            <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
                            </svg>
                        )}
                    >
                        {showFilters ? 'Hide Filters' : 'Show Filters'}
                    </Button>
                    {(Object.keys(filters).length > 0 || searchTerm) && (
                        <Button variant="secondary" onClick={handleResetFilters}>
                            Clear All
                        </Button>
                    )}
                </div>

                {showFilters && (
                    <FilterBar
                        filters={filterConfig}
                        onApply={handleApplyFilters}
                        onReset={handleResetFilters}
                    />
                )}
            </div>

            {/* Inventory Table */}
            <Table
                columns={columns}
                data={inventory}
                onRowClick={handleRowClick}
            />

            {meta.totalPages > 1 && (
                <Pagination
                    currentPage={meta.currentPage}
                    totalPages={meta.totalPages}
                    onPageChange={setPage}
                />
            )}

            {inventory.length === 0 && !loading && (
                <EmptyState title="No inventory found" description="Try adjusting your search or filters" />
            )}

            {/* Inventory Detail Modal */}
            <Modal
                isOpen={showDetailModal}
                onClose={() => {
                    setShowDetailModal(false);
                    setSelectedProduct(null);
                    setProductDetail(null);
                    setShelfBreakdown([]);
                }}
                title="Product Details"
                size="lg"
            >
                {detailLoading ? (
                    <div className="flex items-center justify-center py-8">
                        <LoadingSpinner size="lg" />
                    </div>
                ) : productDetail ? (
                    <div className="space-y-6">
                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <p className="text-sm text-neutral-500">Product Name</p>
                                <p className="font-medium">{productDetail.product?.name || 'N/A'}</p>
                            </div>
                            <div>
                                <p className="text-sm text-neutral-500">Product Code</p>
                                <p className="font-medium">{productDetail.product?.code || 'N/A'}</p>
                            </div>
                            <div>
                                <p className="text-sm text-neutral-500">Category</p>
                                <p className="font-medium">{productDetail.product?.category?.name || 'N/A'}</p>
                            </div>
                            <div>
                                <p className="text-sm text-neutral-500">Current Quantity</p>
                                <p className={`text-xl font-bold ${productDetail.quantity <= 0 ? 'text-error-600' :
                                        productDetail.quantity <= 5 ? 'text-warning-600' : 'text-success-600'
                                    }`}>
                                    {productDetail.quantity || 0}
                                </p>
                            </div>
                            <div>
                                <p className="text-sm text-neutral-500">Status</p>
                                <Badge variant={
                                    productDetail.quantity <= 0 ? 'error' :
                                        productDetail.quantity <= 5 ? 'warning' : 'success'
                                }>
                                    {productDetail.quantity <= 0 ? 'Out of Stock' :
                                        productDetail.quantity <= 5 ? 'Low Stock' : 'In Stock'}
                                </Badge>
                            </div>
                            <div>
                                <p className="text-sm text-neutral-500">Last Updated</p>
                                <p className="font-medium">
                                    {productDetail.last_updated_at ? new Date(productDetail.last_updated_at).toLocaleString() : 'N/A'}
                                </p>
                            </div>
                            <div>
                                <p className="text-sm text-neutral-500">Last Updated By</p>
                                <p className="font-medium">{productDetail.last_updated_by || 'N/A'}</p>
                            </div>
                        </div>

                        {productDetail.product?.description && (
                            <div>
                                <p className="text-sm text-neutral-500">Description</p>
                                <p className="font-medium">{productDetail.product.description}</p>
                            </div>
                        )}

                        <div>
                            <p className="text-sm text-neutral-500 mb-2">Stock by Shelf</p>
                            {shelfBreakdownLoading ? (
                                <div className="flex items-center py-4">
                                    <LoadingSpinner size="sm" />
                                </div>
                            ) : shelfBreakdown.length === 0 ? (
                                <p className="text-sm text-neutral-400 italic">
                                    Not currently on any shelf.
                                </p>
                            ) : (
                                <div className="border border-neutral-200 rounded-lg divide-y divide-neutral-100">
                                    {shelfBreakdown.map((s) => (
                                        <div
                                            key={s.id}
                                            className="flex items-center justify-between px-3 py-2"
                                        >
                                            <span className="font-medium text-neutral-900">{s.name}</span>
                                            <span className="font-semibold text-primary-600">
                                                {s.available_quantity}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                ) : (
                    <div className="text-center py-8">
                        <p className="text-neutral-500">No product details available</p>
                    </div>
                )}
            </Modal>
        </div>
    );
};

export default InventoryPage;