import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Plus, Trash2, TrendingUp, FileText } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { cashManagementApi } from '../../services/cashManagementApi';
import { useInvestorTransactions } from '../../hooks/useCashManagement';
import { extractErrorMessage } from '../../utils/errorMessage';
import { todayLocalDate } from '../../utils/helpers';
import MethodSplitPicker, { isSplitBalanced } from '../../components/paymentMethods/MethodSplitPicker';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';
import Modal from '../../components/ui/Modal';
import Input from '../../components/ui/Input';
import Select from '../../components/ui/Select';
import Badge from '../../components/ui/Badge';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Table from '../../components/ui/Table';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import Pagination from '../../components/ui/Pagination';
import BackLink from '../../components/ui/BackLink';
import EmptyState from '../../components/ui/EmptyState';
import InlineAlert from '../../components/ui/InlineAlert';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const formatAllocations = (allocations) => {
    if (!allocations || allocations.length === 0) return <span className="text-neutral-300">—</span>;
    return allocations.map((a) => `${a.payment_method_name} (Rs. ${fmt(a.amount)})`).join(', ');
};

const InvestorDetailPage = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const [investor, setInvestor] = useState(null);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState(null);
    const [notFound, setNotFound] = useState(false);

    const {
        data: transactions, meta, page, setPage, loading: txnLoading, error: txnError,
        refetch: refetchTxns, create, delete: deleteTxn,
    } = useInvestorTransactions({ investor_id: id });

    const [showModal, setShowModal] = useState(false);
    const [formData, setFormData] = useState({
        transaction_type: 'investment',
        amount: '',
        transaction_date: todayLocalDate(),
        note: '',
        method_allocations: [],
    });
    const [formLoading, setFormLoading] = useState(false);
    const [formError, setFormError] = useState('');
    const [splitError, setSplitError] = useState('');
    const [deleteConfirm, setDeleteConfirm] = useState(null);
    const [deleteLoading, setDeleteLoading] = useState(false);

    const fetchInvestor = useCallback(async () => {
        setLoading(true);
        setLoadError(null);
        setNotFound(false);
        try {
            const data = await cashManagementApi.investors.getById(id);
            setInvestor(data);
        } catch (error) {
            if (error?.response?.status === 404) {
                setNotFound(true);
            } else {
                setLoadError(extractErrorMessage(error, 'Failed to load investor'));
            }
            setInvestor(null);
        } finally {
            setLoading(false);
        }
    }, [id]);

    useEffect(() => {
        fetchInvestor();
    }, [fetchInvestor]);

    const resetForm = () => {
        setFormData({
            transaction_type: 'investment', amount: '',
            transaction_date: todayLocalDate(), note: '', method_allocations: [],
        });
        setFormError('');
        setSplitError('');
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setFormError('');
        setSplitError('');
        setFormLoading(true);
        try {
            await create({ ...formData, investor: id, amount: parseFloat(formData.amount) });
            setShowModal(false);
            resetForm();
            await Promise.all([refetchTxns(), fetchInvestor()]);
            toast.success('Transaction recorded successfully');
        } catch (error) {
            const fieldSplitError = error.response?.data?.method_allocations?.[0] || error.response?.data?.splits?.[0];
            if (fieldSplitError) {
                setSplitError(fieldSplitError);
            } else {
                setFormError(extractErrorMessage(error, 'Failed to record transaction'));
            }
        } finally {
            setFormLoading(false);
        }
    };

    const handleDelete = async (txnId) => {
        setDeleteLoading(true);
        try {
            await deleteTxn(txnId);
            setDeleteConfirm(null);
            await Promise.all([refetchTxns(), fetchInvestor()]);
            toast.success('Transaction deleted and balances restored');
        } catch (error) {
            toast.error(extractErrorMessage(error, 'Failed to delete transaction'));
        } finally {
            setDeleteLoading(false);
        }
    };

    const columns = [
        { key: 'transaction_date', label: 'Date', render: (v) => new Date(v).toLocaleDateString() },
        {
            key: 'transaction_type',
            label: 'Type',
            render: (v) => v === 'investment'
                ? <Badge variant="success" size="sm">Investment</Badge>
                : <Badge variant="warning" size="sm">Withdrawal</Badge>,
        },
        {
            key: 'amount',
            label: 'Amount (PKR)',
            render: (v, row) => (
                <span className={`font-semibold ${row.transaction_type === 'investment' ? 'text-success-600' : 'text-warning-700'}`}>
                    Rs. {fmt(v)}
                </span>
            ),
        },
        { key: 'note', label: 'Note', render: (v) => v || <span className="text-neutral-300">—</span> },
        { key: 'allocations', label: 'Method', render: (v) => formatAllocations(v) },
        {
            key: 'actions',
            label: 'Actions',
            width: '90px',
            render: (_v, row) => (
                <button
                    onClick={(e) => { e.stopPropagation(); setDeleteConfirm(row); }}
                    className="inline-flex items-center justify-center w-9 h-9 rounded-lg text-error-600 hover:bg-error-50 transition-colors"
                    aria-label="Delete transaction"
                >
                    <Trash2 className="w-4 h-4" />
                </button>
            ),
        },
    ];

    if (!isAdmin) {
        return (
            <div className="text-center py-16">
                <h2 className="text-2xl font-semibold text-neutral-900">Access Denied</h2>
                <p className="text-neutral-500 mt-2">Only admins or superusers can view investors.</p>
            </div>
        );
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
                <h2 className="text-2xl font-semibold text-neutral-900">Investor Not Found</h2>
                <BackLink to="/cash-management/investors" className="mt-4 inline-flex">Back to Investors</BackLink>
            </div>
        );
    }

    if (loadError || !investor) {
        return (
            <div className="space-y-4">
                <BackLink to="/cash-management/investors">Back to Investors</BackLink>
                <InlineAlert
                    variant="error"
                    title="Couldn't load this investor"
                    message={loadError || 'Something went wrong'}
                    onRetry={fetchInvestor}
                />
            </div>
        );
    }

    const growthIncrease = parseFloat(investor.current_worth) - parseFloat(investor.net_stake);

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <BackLink to="/cash-management/investors">Back to Investors</BackLink>
                    <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900 mt-2">{investor.name}</h1>
                    <p className="text-neutral-500">
                        {investor.contact_number || 'No contact number'}{investor.email ? ` · ${investor.email}` : ''}
                    </p>
                </div>
                <div className="flex gap-2">
                    <Button
                        variant="secondary"
                        icon={TrendingUp}
                        onClick={() => navigate('/cash-management/growth-history', { state: { investor_id: id } })}
                    >
                        Growth History
                    </Button>
                    <Button icon={Plus} onClick={() => { resetForm(); setShowModal(true); }}>
                        Record Transaction
                    </Button>
                </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                <Card className="p-4" hover={false}>
                    <p className="text-xs text-neutral-500 mb-1">Total Invested</p>
                    <p className="text-xl font-bold text-info-600">Rs. {fmt(investor.total_invested)}</p>
                </Card>
                <Card className="p-4" hover={false}>
                    <p className="text-xs text-neutral-500 mb-1">Total Withdrawn</p>
                    <p className="text-xl font-bold text-warning-700">Rs. {fmt(investor.total_withdrawn)}</p>
                </Card>
                <Card className="p-4" hover={false}>
                    <p className="text-xs text-neutral-500 mb-1">Net Stake</p>
                    <p className="text-xl font-bold text-purple-600">Rs. {fmt(investor.net_stake)}</p>
                </Card>
                <Card className="p-4" hover={false}>
                    <p className="text-xs text-neutral-500 mb-1">Growth Rate</p>
                    <p className="text-xl font-bold text-neutral-900">
                        {parseFloat(investor.growth_rate) > 0 ? `${(parseFloat(investor.growth_rate) * 100).toFixed(2)}% / yr` : '—'}
                    </p>
                </Card>
                <Card className="p-4" hover={false}>
                    <p className="text-xs text-neutral-500 mb-1">Current Worth</p>
                    <p className="text-xl font-bold text-teal-600">Rs. {fmt(investor.current_worth)}</p>
                    {growthIncrease > 0 && (
                        <p className="text-xs text-success-600 mt-1">+Rs. {fmt(growthIncrease)} from growth</p>
                    )}
                </Card>
            </div>

            {parseFloat(investor.growth_rate) > 0 && (
                <InlineAlert
                    variant="info"
                    message="Current Worth is a theoretical value grown monthly at this investor's rate — it's informational only. Withdrawals are always capped by Net Stake (the actual amount invested), never by Current Worth."
                />
            )}

            {investor.note && (
                <Card className="p-4" hover={false}>
                    <p className="text-xs font-medium text-neutral-500 flex items-center gap-1.5 mb-1">
                        <FileText className="w-3.5 h-3.5" /> Note
                    </p>
                    <p className="font-medium text-neutral-900">{investor.note}</p>
                </Card>
            )}

            <div className="space-y-4">
                <h2 className="text-lg font-semibold text-neutral-900">Transaction History</h2>

                {txnError && !txnLoading && (
                    <InlineAlert variant="error" title="Couldn't load transactions" message={txnError} onRetry={refetchTxns} />
                )}

                {txnLoading ? (
                    <div className="flex items-center justify-center py-12">
                        <LoadingSpinner size="lg" />
                    </div>
                ) : transactions.length === 0 ? (
                    <EmptyState
                        title="No Transactions Yet"
                        description="Record an investment or withdrawal to get started."
                    />
                ) : (
                    <>
                        <Table
                            columns={columns}
                            data={transactions}
                            onRowClick={(row) => navigate(`/cash-management/investor-transactions/${row.id}`)}
                        />
                        {meta.totalPages > 1 && (
                            <Pagination currentPage={meta.currentPage} totalPages={meta.totalPages} onPageChange={setPage} />
                        )}
                    </>
                )}
            </div>

            {/* Record Transaction Modal */}
            <Modal
                isOpen={showModal}
                onClose={() => { setShowModal(false); resetForm(); }}
                title="Record Investment / Withdrawal"
                size="lg"
            >
                <form onSubmit={handleSubmit} className="space-y-4">
                    <Select
                        label="Type"
                        value={formData.transaction_type}
                        onChange={(e) => setFormData({ ...formData, transaction_type: e.target.value })}
                        options={[
                            { value: 'investment', label: 'Investment — increases cash in hand' },
                            { value: 'withdrawal', label: 'Withdrawal — decreases cash in hand' },
                        ]}
                        required
                    />
                    <Input
                        label="Amount (PKR)"
                        type="number"
                        step="0.01"
                        min="0.01"
                        value={formData.amount}
                        onChange={(e) => setFormData({ ...formData, amount: e.target.value })}
                        placeholder="Enter amount"
                        required
                    />
                    <Input
                        label="Date"
                        type="date"
                        value={formData.transaction_date}
                        onChange={(e) => setFormData({ ...formData, transaction_date: e.target.value })}
                        required
                    />
                    <Input
                        label="Note"
                        value={formData.note}
                        onChange={(e) => setFormData({ ...formData, note: e.target.value })}
                        placeholder="Optional"
                    />

                    {formData.transaction_type === 'withdrawal' && (
                        <p className="text-xs text-neutral-500">
                            Current net stake: <strong>Rs. {fmt(investor.net_stake)}</strong> — withdrawals above this are rejected.
                        </p>
                    )}

                    <div>
                        <label className="block text-sm font-medium text-neutral-700 mb-1.5">
                            {formData.transaction_type === 'investment' ? 'Received Via' : 'Paid Via'}
                        </label>
                        <MethodSplitPicker
                            totalAmount={formData.amount}
                            value={formData.method_allocations}
                            onChange={(value) => setFormData({ ...formData, method_allocations: value })}
                            error={splitError}
                        />
                    </div>

                    {formError && <InlineAlert variant="error" message={formError} />}

                    <div className="flex justify-end gap-3 pt-4">
                        <Button type="button" variant="secondary" onClick={() => { setShowModal(false); resetForm(); }}>
                            Cancel
                        </Button>
                        <Button
                            type="submit"
                            loading={formLoading}
                            disabled={!isSplitBalanced(formData.amount, formData.method_allocations)}
                        >
                            Record
                        </Button>
                    </div>
                </form>
            </Modal>

            {/* Delete Confirmation */}
            <ConfirmDialog
                isOpen={!!deleteConfirm}
                onClose={() => setDeleteConfirm(null)}
                onConfirm={() => handleDelete(deleteConfirm?.id)}
                title="Delete Transaction"
                message={`Are you sure you want to delete this Rs. ${fmt(deleteConfirm?.amount)} ${deleteConfirm?.transaction_type}? This will reverse its effect on cash in hand and this investor's balance.`}
                loading={deleteLoading}
            />
        </div>
    );
};

export default InvestorDetailPage;
