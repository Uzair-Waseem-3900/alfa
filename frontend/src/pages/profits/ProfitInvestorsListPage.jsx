import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { cashManagementApi } from '../../services/cashManagementApi';
import { extractErrorMessage } from '../../utils/errorMessage';
import Table from '../../components/ui/Table';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import InlineAlert from '../../components/ui/InlineAlert';
import EmptyState from '../../components/ui/EmptyState';
import { Users, ShieldAlert } from 'lucide-react';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const ProfitInvestorsListPage = () => {
    const { user } = useAuth();
    const navigate = useNavigate();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const [investors, setInvestors] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchInvestors = useCallback(() => {
        setLoading(true);
        setError(null);
        cashManagementApi.investors.getAll({ page_size: 500 })
            .then((res) => setInvestors(res?.results ?? res ?? []))
            .catch((err) => setError(extractErrorMessage(err, 'Failed to load investors')))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        fetchInvestors();
    }, [fetchInvestors]);

    if (!isAdmin) {
        return (
            <div className="text-center py-12">
                <ShieldAlert className="w-10 h-10 text-neutral-300 mx-auto mb-3" />
                <h2 className="text-2xl font-semibold text-neutral-900">Access Denied</h2>
                <p className="text-neutral-500 mt-2">Only admins or superusers can view investors.</p>
            </div>
        );
    }

    const columns = [
        { key: 'name', label: 'Name' },
        { key: 'contact', label: 'Contact', render: (_v, row) => row.contact_number || row.email || <span className="text-neutral-300">—</span> },
        { key: 'total_invested', label: 'Total Invested (PKR)', render: (v) => `Rs. ${fmt(v)}` },
        { key: 'total_withdrawn', label: 'Total Withdrawn (PKR)', render: (v) => `Rs. ${fmt(v)}` },
        { key: 'net_stake', label: 'Net Stake (PKR)', render: (v) => <span className="font-semibold text-neutral-900">Rs. {fmt(v)}</span> },
        { key: 'current_worth', label: 'Current Worth (PKR)', render: (v) => <span className="font-semibold text-primary-600">Rs. {fmt(v)}</span> },
    ];

    return (
        <div className="space-y-6">
            <div className="flex items-center gap-3">
                <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-primary-600 to-accent-600 flex items-center justify-center shadow-lg shadow-primary-900/20 flex-shrink-0">
                    <Users className="w-5 h-5 text-white" />
                </div>
                <div>
                    <h1 className="text-3xl font-bold text-neutral-900">Investors</h1>
                    <p className="text-neutral-500 mt-0.5">
                        Click an investor to view their profit history and settle monthly shares.
                    </p>
                </div>
            </div>

            {error ? (
                <InlineAlert variant="error" message={error} onRetry={fetchInvestors} />
            ) : loading ? (
                <div className="flex items-center justify-center py-8">
                    <LoadingSpinner size="lg" />
                </div>
            ) : investors.length === 0 ? (
                <EmptyState
                    icon={<Users className="w-8 h-8 text-neutral-400" />}
                    title="No Investors Yet"
                    description="Add investors from Cash Management → Investors."
                />
            ) : (
                <Table
                    columns={columns}
                    data={investors}
                    onRowClick={(row) => navigate(`/profits/investors/${row.id}`)}
                />
            )}
        </div>
    );
};

export default ProfitInvestorsListPage;
