import { useState } from 'react';
import { useParams, useNavigate, Navigate } from 'react-router-dom';
import { SlidersHorizontal, X } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { salesManApi } from '../../services/salesManApi';
import { useSalesManDetail } from '../../hooks/useSalesMan';
import { usePaginatedList } from '../../hooks/usePaginatedList';
import InvoiceTable from '../../components/billing/InvoiceTable';
import InvoiceFilterBar from '../../components/billing/InvoiceFilterBar';
import Tabs from '../../components/ui/Tabs';
import SearchBar from '../../components/ui/SearchBar';
import Button from '../../components/ui/Button';
import BackLink from '../../components/ui/BackLink';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Pagination from '../../components/ui/Pagination';
import InlineAlert from '../../components/ui/InlineAlert';

// Same tab set, filter bar, search, and table as billing/invoices
// (InvoicesPage.jsx) — this page just scopes every request to one sales
// man's customers via a single param instead of separate per-tab URLs.
const TABS = [
    { value: 'all', label: 'All Invoices' },
    { value: 'drafts', label: 'Drafts' },
    { value: 'confirmed', label: 'Confirmed' },
    { value: 'outstanding', label: 'Outstanding' },
    { value: 'due', label: 'Due Invoices' },
];

const SalesManInvoicesPage = () => {
    const { id } = useParams();
    const { user } = useAuth();
    const navigate = useNavigate();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    // Fetched once, cheaply (single row, already loaded if the user came
    // from the detail page) — just for the page header's name.
    const { salesMan } = useSalesManDetail(id);

    const [activeTab, setActiveTab] = useState('all');
    const [searchTerm, setSearchTerm] = useState('');
    const [showFilters, setShowFilters] = useState(false);

    const fetchInvoicesPage = (params) => {
        const p = { ...params };
        if (searchTerm) p.bill_number = searchTerm;
        switch (activeTab) {
            case 'drafts': p.status = 'draft'; break;
            case 'confirmed': p.status = 'confirmed'; break;
            case 'outstanding': p.outstanding_only = true; break;
            case 'due': p.due_only = true; break;
            default: break;
        }
        return salesManApi.invoices.getAll(id, p);
    };

    const {
        data: invoices, meta, page, setPage, loading, initialLoading, error,
        filters: filterValues, setFilters: setFilterValues, refetch: fetchInvoices,
    } = usePaginatedList(fetchInvoicesPage, {}, 25, [id, activeTab, searchTerm]);

    if (!isAdmin) {
        return <Navigate to="/dashboard" replace />;
    }

    const handleTabChange = (tab) => {
        setActiveTab(tab);
        setPage(1);
    };

    const handleSearch = (value) => {
        setSearchTerm(value);
        setPage(1);
    };

    const handleApplyFilters = (newFilters) => {
        setFilterValues(newFilters);
    };

    const handleResetFilters = () => {
        setFilterValues({});
        setSearchTerm('');
    };

    const handleRowClick = (invoice) => {
        navigate(`/billing/invoices/${invoice.id}`);
    };

    if (initialLoading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <BackLink to={`/sales-man/${id}`}>Back to Sales Man</BackLink>

            <div>
                <h1 className="text-3xl font-bold text-neutral-900">
                    {salesMan ? `${salesMan.name}'s Invoices` : 'Invoices'}
                </h1>
                <p className="text-neutral-500 mt-1">All invoices billed to this sales man's customers</p>
            </div>

            <div className="space-y-4">
                <div className="flex gap-4">
                    <SearchBar
                        onSearch={handleSearch}
                        placeholder="Search by bill number..."
                        className="flex-1"
                        value={searchTerm}
                    />
                    <Button
                        variant="secondary"
                        onClick={() => setShowFilters(!showFilters)}
                        icon={SlidersHorizontal}
                    >
                        {showFilters ? 'Hide Filters' : 'Show Filters'}
                    </Button>
                    {(Object.keys(filterValues).length > 0 || searchTerm) && (
                        <Button variant="secondary" onClick={handleResetFilters} icon={X}>
                            Clear All
                        </Button>
                    )}
                </div>

                {showFilters && (
                    <InvoiceFilterBar
                        onApply={handleApplyFilters}
                        onReset={handleResetFilters}
                    />
                )}

                <Tabs tabs={TABS} activeTab={activeTab} onChange={handleTabChange} />
            </div>

            {error && <InlineAlert variant="error" message={error} onRetry={fetchInvoices} />}

            {loading && !initialLoading ? (
                <div className="flex items-center justify-center py-16">
                    <LoadingSpinner size="md" />
                </div>
            ) : (
                <InvoiceTable
                    invoices={invoices}
                    onRowClick={handleRowClick}
                    isAdmin={false}
                    showActions={false}
                />
            )}

            {meta.totalPages > 1 && (
                <Pagination
                    currentPage={meta.currentPage}
                    totalPages={meta.totalPages}
                    onPageChange={setPage}
                />
            )}
        </div>
    );
};

export default SalesManInvoicesPage;
