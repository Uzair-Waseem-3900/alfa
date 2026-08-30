import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useInvestorProfitPayouts } from '../../hooks/useProfits';
import Badge from '../../components/ui/Badge';
import Table from '../../components/ui/Table';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Pagination from '../../components/ui/Pagination';
import InlineAlert from '../../components/ui/InlineAlert';
import EmptyState from '../../components/ui/EmptyState';
import { HandCoins, ShieldAlert } from 'lucide-react';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const formatMonthLabel = (period) => {
    if (!period) return '';
    const [year, m] = period.split('-');
    const date = new Date(Number(year), Number(m) - 1, 1);
    return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
};

const actionBadge = (actionType) =>
    actionType === 'reinvest'
        ? <Badge variant="info" size="sm">Reinvest</Badge>
        : <Badge variant="success" size="sm">Payout</Badge>;

const InvestorPayoutsPage = () => {
    const navigate = useNavigate();
    const { user } = useAuth();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const { data: payouts, meta, page, setPage, loading, error, refetch } = useInvestorProfitPayouts();

    if (!isAdmin) {
        return (
            <div className="text-center py-12">
                <ShieldAlert className="w-10 h-10 text-neutral-300 mx-auto mb-3" />
                <h2 className="text-2xl font-semibold text-neutral-900">Access Denied</h2>
                <p className="text-neutral-500 mt-2">Only admins or superusers can view investor payments.</p>
            </div>
        );
    }

    const columns = [
        { key: 'created_at', label: 'Recorded On', render: (v) => new Date(v).toLocaleString() },
        { key: 'investor_name', label: 'Investor' },
        { key: 'period', label: 'For Month', render: (v) => formatMonthLabel(v) },
        { key: 'action_type', label: 'Type', render: (v) => actionBadge(v) },
        { key: 'amount', label: 'Amount (PKR)', render: (v) => <span className="font-semibold text-neutral-900">Rs. {fmt(v)}</span> },
        { key: 'payout_date', label: 'Date', render: (v) => new Date(v).toLocaleDateString() },
        { key: 'note', label: 'Note', render: (v) => v || <span className="text-neutral-300">—</span> },
        { key: 'created_by', label: 'Recorded By', render: (v) => v || 'N/A' },
    ];

    return (
        <div className="space-y-6">
            <InlineAlert
                variant="warning"
                message="Figures here are computed from an internal estimate, not a certified valuation. Review with an accountant before relying on them. The developer is not responsible at all for decisions made from this page."
            />

            <div className="flex items-center gap-3">
                <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-primary-600 to-accent-600 flex items-center justify-center shadow-lg shadow-primary-900/20 flex-shrink-0">
                    <HandCoins className="w-5 h-5 text-white" />
                </div>
                <div>
                    <h1 className="text-3xl font-bold text-neutral-900">Investor Payments</h1>
                    <p className="text-neutral-500 mt-0.5">
                        Every profit payout and reinvestment ever recorded, across every investor and month —
                        newest first. Capital withdrawals aren't shown here; see the Investors page in Cash
                        Management for those.
                    </p>
                </div>
            </div>

            {error ? (
                <InlineAlert variant="error" message={error} onRetry={refetch} />
            ) : loading ? (
                <div className="flex items-center justify-center py-8">
                    <LoadingSpinner size="lg" />
                </div>
            ) : payouts.length === 0 ? (
                <EmptyState
                    icon={<HandCoins className="w-8 h-8 text-neutral-400" />}
                    title="No Profit Payments Recorded Yet"
                    description="These appear once a finalized month's share is settled with an investor."
                />
            ) : (
                <>
                    <Table
                        columns={columns}
                        data={payouts}
                        onRowClick={(row) => navigate(`/profits/payouts/${row.id}`)}
                    />
                    {meta.totalPages > 1 && (
                        <Pagination currentPage={meta.currentPage} totalPages={meta.totalPages} onPageChange={setPage} />
                    )}
                </>
            )}
        </div>
    );
};

export default InvestorPayoutsPage;
