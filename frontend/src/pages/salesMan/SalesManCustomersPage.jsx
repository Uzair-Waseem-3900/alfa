import { useState } from 'react';
import { useParams, useNavigate, Navigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useSalesManDetail, useSalesManCustomers } from '../../hooks/useSalesMan';
import CustomerTable from '../../components/billing/CustomerTable';
import SearchBar from '../../components/ui/SearchBar';
import BackLink from '../../components/ui/BackLink';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Pagination from '../../components/ui/Pagination';
import InlineAlert from '../../components/ui/InlineAlert';
import Card from '../../components/ui/Card';

const SalesManCustomersPage = () => {
    const { id } = useParams();
    const { user } = useAuth();
    const navigate = useNavigate();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const { salesMan } = useSalesManDetail(id);

    const [searchTerm, setSearchTerm] = useState('');
    const {
        data: customers, meta, setPage, loading, initialLoading, error,
        setFilters, refetch,
    } = useSalesManCustomers(id);

    if (!isAdmin) {
        return <Navigate to="/dashboard" replace />;
    }

    const handleSearch = (value) => {
        setSearchTerm(value);
        setFilters({ search: value || undefined });
    };

    const handleRowClick = (customer) => {
        navigate(`/billing/customers/${customer.id}`);
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
                <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900 break-words">
                    {salesMan ? `${salesMan.name}'s Customers` : 'Customers'}
                </h1>
                <p className="text-neutral-500 mt-1">Every customer currently assigned to this sales man</p>
            </div>

            <Card className="p-4 sm:p-5" hover={false}>
                <SearchBar
                    onSearch={handleSearch}
                    placeholder="Search by name or code..."
                    value={searchTerm}
                />
            </Card>

            {error && <InlineAlert variant="error" message={error} onRetry={refetch} />}

            <Card className="p-0 overflow-hidden" hover={false}>
                <div className={`relative transition-opacity ${loading ? 'opacity-60' : 'opacity-100'}`}>
                    {loading && (
                        <div className="absolute right-4 top-4 z-10">
                            <LoadingSpinner size="sm" />
                        </div>
                    )}
                    <CustomerTable customers={customers} onRowClick={handleRowClick} isAdmin={false} />
                </div>
            </Card>

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

export default SalesManCustomersPage;
