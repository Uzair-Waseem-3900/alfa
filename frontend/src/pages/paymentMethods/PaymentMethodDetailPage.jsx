import { Navigate, useParams } from 'react-router-dom';
import { Wallet, ArrowDownLeft, ArrowUpRight, ShieldCheck } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { usePaymentMethod, useMethodAllocations } from '../../hooks/usePaymentMethods';
import Card from '../../components/ui/Card';
import Badge from '../../components/ui/Badge';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Table from '../../components/ui/Table';
import Pagination from '../../components/ui/Pagination';
import BackLink from '../../components/ui/BackLink';
import EmptyState from '../../components/ui/EmptyState';
import InlineAlert from '../../components/ui/InlineAlert';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

// "billing.payment" -> "Payment", "cash_flow.expense" -> "Expense",
// "payment_methods.accounttransfer" -> "Accounttransfer". source_model is an
// opaque label per the API contract — only the part after the dot is shown.
const sourceLabel = (sourceModel) => {
    if (!sourceModel) return '—';
    const raw = sourceModel.split('.').pop() || sourceModel;
    return raw.charAt(0).toUpperCase() + raw.slice(1);
};

const PaymentMethodDetailPage = () => {
    const { id } = useParams();
    const { user } = useAuth();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const { data: method, loading, error: loadError, notFound, refetch } = usePaymentMethod(id);
    const {
        data: allocations, meta, setPage, loading: allocLoading, error: allocError, refetch: refetchAllocations,
    } = useMethodAllocations(id);

    if (!isAdmin) {
        return <Navigate to="/dashboard" replace />;
    }

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    if (notFound) {
        return (
            <div className="text-center py-16">
                <h2 className="text-2xl font-semibold text-neutral-900">Payment Method Not Found</h2>
                <BackLink to="/payment-methods" className="mt-4 inline-flex">Back to Payment Methods</BackLink>
            </div>
        );
    }

    if (loadError || !method) {
        return (
            <div className="space-y-4">
                <BackLink to="/payment-methods">Back to Payment Methods</BackLink>
                <InlineAlert
                    variant="error"
                    title="Couldn't load this payment method"
                    message={loadError || 'Something went wrong'}
                    onRetry={refetch}
                />
            </div>
        );
    }

    const columns = [
        { key: 'date', label: 'Date', render: (v) => new Date(v).toLocaleDateString() },
        {
            key: 'direction',
            label: 'Direction',
            render: (v) => v === 'inflow'
                ? <Badge variant="success" className="gap-1"><ArrowDownLeft className="w-3 h-3" /> Inflow</Badge>
                : <Badge variant="warning" className="gap-1"><ArrowUpRight className="w-3 h-3" /> Outflow</Badge>,
        },
        {
            key: 'amount',
            label: 'Amount (PKR)',
            render: (v, row) => (
                <span className={`font-semibold ${row.direction === 'inflow' ? 'text-success-600' : 'text-warning-700'}`}>
                    Rs. {fmt(v)}
                </span>
            ),
        },
        { key: 'source_model', label: 'Source', render: (v) => sourceLabel(v) },
        { key: 'source_id', label: 'Reference' },
    ];

    return (
        <div className="space-y-6">
            <div>
                <BackLink to="/payment-methods">Back to Payment Methods</BackLink>
                <div className="flex items-center gap-2.5 mt-2">
                    <Wallet className="w-6 h-6 text-primary-600" />
                    <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900">{method.name}</h1>
                    {method.is_protected && (
                        <Badge variant="info" className="gap-1">
                            <ShieldCheck className="w-3 h-3" /> Protected
                        </Badge>
                    )}
                </div>
                <p className="text-neutral-500 mt-1">{method.account_number || 'No account number'}</p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Card className="p-4" hover={false}>
                    <p className="text-xs text-neutral-500 mb-1">Current Balance</p>
                    <p className="text-2xl font-bold text-success-600">Rs. {fmt(method.balance)}</p>
                </Card>
                <Card className="p-4" hover={false}>
                    <p className="text-xs text-neutral-500 mb-1">Last Updated</p>
                    <p className="text-lg font-semibold text-neutral-900">
                        {method.updated_at ? new Date(method.updated_at).toLocaleString() : '—'}
                    </p>
                </Card>
            </div>

            <div className="space-y-4">
                <h2 className="text-lg font-semibold text-neutral-900">Transaction History</h2>

                {allocError && !allocLoading && (
                    <InlineAlert variant="error" title="Couldn't load transaction history" message={allocError} onRetry={refetchAllocations} />
                )}

                {allocLoading ? (
                    <div className="flex items-center justify-center py-12">
                        <LoadingSpinner size="lg" />
                    </div>
                ) : allocations.length === 0 ? (
                    <EmptyState
                        title="No Transactions Yet"
                        description="Transactions that use this payment method will show up here."
                    />
                ) : (
                    <>
                        <Table columns={columns} data={allocations} />
                        {meta.totalPages > 1 && (
                            <Pagination currentPage={meta.currentPage} totalPages={meta.totalPages} onPageChange={setPage} />
                        )}
                    </>
                )}
            </div>
        </div>
    );
};

export default PaymentMethodDetailPage;
