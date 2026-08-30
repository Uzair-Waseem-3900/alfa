import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Package, DollarSign } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { purchasesApi } from '../../services/purchasesApi';
import { ratesApi } from '../../services/ratesApi';
import { usePaginatedList } from '../../hooks/usePaginatedList';
import { extractErrorMessage } from '../../utils/errorMessage';
import Card from '../ui/Card';
import SearchBar from '../ui/SearchBar';
import Select from '../ui/Select';
import LoadingSpinner from '../ui/LoadingSpinner';
import Badge from '../ui/Badge';
import Table from '../ui/Table';
import Pagination from '../ui/Pagination';

const NormalUserDashboard = () => {
    const { user } = useAuth();
    const { toast } = useToast();
    const [rates, setRates] = useState([]);
    const [ratesLoading, setRatesLoading] = useState(true);
    const [searchTerm, setSearchTerm] = useState('');
    const [categoryFilter, setCategoryFilter] = useState('');
    const [categories, setCategories] = useState([]);
    const [invStats, setInvStats] = useState(null);
    const [activeTab, setActiveTab] = useState('inventory');

    // Search/category are routed through query params — the backend
    // supports search/category on this endpoint — so the table itself
    // stays correctly paginated instead of filtering a client-side array.
    // Shelf is no longer a product-level filter (a product can now span
    // multiple shelves) — per-shelf breakdowns live on the Shelves page.
    const fetchInventoryPage = (params) => {
        const p = { ...params };
        if (searchTerm) p.search = searchTerm;
        if (categoryFilter) p.category = categoryFilter;
        return purchasesApi.inventory.getAll(p);
    };

    const {
        data: inventory, meta, page, setPage, loading: inventoryLoading,
    } = usePaginatedList(fetchInventoryPage, {}, 25, [searchTerm, categoryFilter]);

    useEffect(() => {
        loadLookupsAndRates();
    }, []);

    const loadLookupsAndRates = async () => {
        setRatesLoading(true);
        try {
            // Normal users have no Purchases app access, so category
            // filter options are derived from a full (page_size:500) inventory
            // fetch rather than calling purchasesApi.categories (admin-only)
            // — kept separate from the paginated table fetch.
            const [fullInventoryData, ratesData, statsData] = await Promise.all([
                purchasesApi.inventory.getAll({ page_size: 500 }),
                ratesApi.getAll(),
                purchasesApi.inventory.getStats(),
            ]);
            const fullInventory = fullInventoryData?.results || fullInventoryData || [];
            setRates(ratesData?.results || ratesData || []);
            setInvStats(statsData);

            const categoryMap = new Map();
            fullInventory.forEach(item => {
                const category = item.product?.category;
                if (category?.id) categoryMap.set(category.id, category);
            });
            setCategories([...categoryMap.values()]);
        } catch (error) {
            console.error('Failed to load data:', error);
            toast.error(extractErrorMessage(error, 'Failed to load dashboard data'));
        } finally {
            setRatesLoading(false);
        }
    };

    // Summary stats come from the dedicated O(1) stats endpoint (stored
    // counters on the backend) — whole-inventory numbers by design.
    const totalProducts = invStats?.total_products ?? 0;
    const lowStockItems = invStats?.low_stock_count ?? 0;
    const outOfStockItems = invStats?.out_of_stock_count ?? 0;

    const inventoryColumns = [
        { key: 'product', label: 'Code', render: (value) => value?.code || 'N/A' },
        { key: 'product', label: 'Name', render: (value) => value?.name || 'N/A' },
        { key: 'product', label: 'Category', render: (value) => value?.category?.name || 'N/A' },
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
    ];

    const ratesColumns = [
        { key: 'product', label: 'Code', render: (value) => value?.code || 'N/A' },
        { key: 'product', label: 'Name', render: (value) => value?.name || 'N/A' },
        { key: 'product', label: 'Category', render: (value) => value?.category?.name || 'N/A' },
        {
            key: 'rate',
            label: 'Selling Price',
            render: (value) => {
                if (!value) return <Badge variant="error">No price set</Badge>;
                return <span className="font-semibold text-primary-600">{parseFloat(value.selling_price).toFixed(2)}</span>;
            }
        },
    ];

    return (
        <div className="space-y-6">
            {/* Welcome Section — renders immediately, no data dependency */}
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="bg-gradient-to-r from-primary-700 to-accent-600 rounded-2xl p-6 text-white"
            >
                <h1 className="text-2xl font-bold">
                    Welcome back, {user?.first_name} {user?.last_name}!
                </h1>
                <div className="flex items-center gap-2 mt-1">
                    <Badge variant="info" className="bg-white/20 text-white">User</Badge>
                    <span className="text-white/80 text-sm">View-only access</span>
                </div>
            </motion.div>

            {/* Summary Cards — own skeleton while stats load */}
            {ratesLoading ? (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {[0, 1, 2].map((i) => (
                        <Card key={i} className="p-4">
                            <div className="h-4 bg-neutral-200 rounded w-28 animate-pulse" />
                            <div className="h-8 bg-neutral-200 rounded w-16 mt-2 animate-pulse" />
                        </Card>
                    ))}
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <Card className="p-4">
                        <p className="text-sm text-neutral-500">Total Products</p>
                        <p className="text-2xl font-bold text-neutral-900">{totalProducts}</p>
                    </Card>
                    <Card className="p-4">
                        <p className="text-sm text-neutral-500">Low Stock (≤ 5)</p>
                        <p className="text-2xl font-bold text-warning-600">{lowStockItems}</p>
                    </Card>
                    <Card className="p-4">
                        <p className="text-sm text-neutral-500">Out of Stock</p>
                        <p className="text-2xl font-bold text-error-600">{outOfStockItems}</p>
                    </Card>
                </div>
            )}

            {/* Tabs */}
            <div className="flex gap-2 border-b border-neutral-200 overflow-x-auto">
                <button
                    onClick={() => setActiveTab('inventory')}
                    className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-t-lg transition-all cursor-pointer whitespace-nowrap ${activeTab === 'inventory'
                            ? 'text-primary-700 border-b-2 border-primary-700'
                            : 'text-neutral-500 hover:text-neutral-700 hover:bg-neutral-50'
                        }`}
                >
                    <Package className="w-4 h-4" /> Inventory
                </button>
                <button
                    onClick={() => setActiveTab('rates')}
                    className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-t-lg transition-all cursor-pointer whitespace-nowrap ${activeTab === 'rates'
                            ? 'text-primary-700 border-b-2 border-primary-700'
                            : 'text-neutral-500 hover:text-neutral-700 hover:bg-neutral-50'
                        }`}
                >
                    <DollarSign className="w-4 h-4" /> Rates
                </button>
            </div>

            {/* Inventory Tab */}
            {activeTab === 'inventory' && (
                <div className="space-y-4">
                    <div className="flex flex-wrap gap-4">
                        <SearchBar
                            onSearch={(value) => { setSearchTerm(value); setPage(1); }}
                            placeholder="Search by name or code..."
                            className="flex-1 min-w-[200px]"
                        />
                        <Select
                            value={categoryFilter}
                            onChange={(e) => { setCategoryFilter(e.target.value); setPage(1); }}
                            options={[
                                { value: '', label: 'All Categories' },
                                ...categories.map(c => ({ value: c.id, label: c.name })),
                            ]}
                            className="w-48"
                        />
                    </div>
                    {inventoryLoading ? (
                        <div className="flex items-center justify-center py-12">
                            <LoadingSpinner size="lg" />
                        </div>
                    ) : (
                        <>
                            <Table columns={inventoryColumns} data={inventory} />
                            {meta.totalPages > 1 && (
                                <Pagination
                                    currentPage={meta.currentPage}
                                    totalPages={meta.totalPages}
                                    onPageChange={setPage}
                                />
                            )}
                        </>
                    )}
                </div>
            )}

            {/* Rates Tab */}
            {activeTab === 'rates' && (
                <div className="space-y-4">
                    <p className="text-sm text-neutral-500">View current selling prices (read-only)</p>
                    {ratesLoading ? (
                        <div className="flex items-center justify-center py-12">
                            <LoadingSpinner size="lg" />
                        </div>
                    ) : (
                        <Table columns={ratesColumns} data={rates} />
                    )}
                </div>
            )}
        </div>
    );
};

export default NormalUserDashboard;