import { useState } from 'react';
import { motion } from 'framer-motion';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useLedgerList } from '../../hooks/useLedger';
import { ledgerApi, customerLedgerApi } from '../../services/ledgerApi';
import LedgerListTable, { SUPPLIER_COLUMNS } from '../../components/ledger/LedgerListTable';
import SearchBar from '../../components/ui/SearchBar';
import Button from '../../components/ui/Button';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Pagination from '../../components/ui/Pagination';
import InlineAlert from '../../components/ui/InlineAlert';

const CUSTOMER_COLUMNS = [
    { key: 'customer_name', label: 'Customer Name' },
    { key: 'customer_code', label: 'Customer Code', width: '120px' },
    {
        key: 'created_at',
        label: 'Account Since',
        render: (value) => new Date(value).toLocaleDateString(),
    },
];

const TAB_CONFIG = {
    supplier: {
        api: ledgerApi,
        columns: SUPPLIER_COLUMNS,
        heading: 'Supplier Ledgers',
        subheading: 'View all supplier account statements',
        searchPlaceholder: 'Search by supplier name or code...',
        emptyTitle: 'No ledgers found',
        emptyDescription: 'No suppliers have been created yet.',
        detailPath: (id) => `/ledger/${id}`,
    },
    customer: {
        api: customerLedgerApi,
        columns: CUSTOMER_COLUMNS,
        heading: 'Customer Ledgers',
        subheading: 'View all customer account statements',
        searchPlaceholder: 'Search by customer name or code...',
        emptyTitle: 'No ledgers found',
        emptyDescription: 'No customers have been created yet.',
        detailPath: (id) => `/ledger/customers/${id}`,
    },
};

const LedgerListPage = () => {
    const { user } = useAuth();
    const navigate = useNavigate();
    const location = useLocation();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const activeTab = location.pathname === '/ledger/customers' ? 'customer' : 'supplier';
    const config = TAB_CONFIG[activeTab];

    // One hook instance, api client swapped by tab — `deps: [activeTab]`
    // forces a refetch on tab change even when filters/page haven't moved.
    const { data, meta, page, setPage, loading, initialLoading, error, filters, setFilters, refetch } =
        useLedgerList({}, config.api, [activeTab]);
    const [searchTerm, setSearchTerm] = useState('');

    // Redirect normal users
    if (!isAdmin) {
        navigate('/dashboard');
        return null;
    }

    const handleSearch = (value) => {
        setSearchTerm(value);
        setFilters({ search: value });
    };

    const handleRowClick = (ledger) => {
        navigate(config.detailPath(ledger.id));
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
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <h1 className="text-3xl font-bold text-neutral-900">{config.heading}</h1>
                    <p className="text-neutral-500 mt-1">{config.subheading}</p>
                </div>
            </div>

            <div className="flex gap-4">
                <SearchBar
                    onSearch={handleSearch}
                    placeholder={config.searchPlaceholder}
                    className="flex-1"
                    value={searchTerm}
                />
                {searchTerm && (
                    <Button
                        variant="secondary"
                        onClick={() => {
                            setSearchTerm('');
                            setFilters({});
                        }}
                    >
                        Clear
                    </Button>
                )}
            </div>

            {error && <InlineAlert variant="error" message={error} onRetry={refetch} />}

            <LedgerListTable
                ledgers={data}
                onRowClick={handleRowClick}
                loading={loading}
                columns={config.columns}
                emptyTitle={config.emptyTitle}
                emptyDescription={config.emptyDescription}
            />

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

export default LedgerListPage;