import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { cashManagementApi } from '../../services/cashManagementApi';
import { profitsApi } from '../../services/profitsApi';
import { extractErrorMessage } from '../../utils/errorMessage';
import { todayLocalDate } from '../../utils/helpers';
import { useInvestorMonthlyShares } from '../../hooks/useProfits';
import MethodSplitPicker, { isSplitBalanced } from '../../components/paymentMethods/MethodSplitPicker';
import Card from '../../components/ui/Card';
import Button from '../../components/ui/Button';
import Badge from '../../components/ui/Badge';
import Modal from '../../components/ui/Modal';
import BackLink from '../../components/ui/BackLink';
import Input from '../../components/ui/Input';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Pagination from '../../components/ui/Pagination';
import InlineAlert from '../../components/ui/InlineAlert';
import EmptyState from '../../components/ui/EmptyState';
import { Wallet, ArrowDownCircle, TrendingUp, ShieldAlert, ReceiptText } from 'lucide-react';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const formatMonthLabel = (period) => {
    if (!period) return '';
    const [year, m] = period.split('-');
    const date = new Date(Number(year), Number(m) - 1, 1);
    return date.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
};

const statusBadge = (status) => {
    if (status === 'paid') return <Badge variant="success" size="sm">Paid</Badge>;
    if (status === 'partial') return <Badge variant="warning" size="sm">Partial</Badge>;
    return <Badge variant="error" size="sm">Unpaid</Badge>;
};

const ProfitInvestorDetailPage = () => {
    const { id } = useParams();
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const [investor, setInvestor] = useState(null);
    const [investorLoading, setInvestorLoading] = useState(true);
    const [investorError, setInvestorError] = useState(null);

    const { data: shares, meta, page, setPage, loading: sharesLoading, error: sharesError, refetch } = useInvestorMonthlyShares(id);

    const [settleShare, setSettleShare] = useState(null);
    const [formData, setFormData] = useState({
        amount: '', action_type: 'payout', payout_date: todayLocalDate(), note: '', method_allocations: [],
    });
    const [formLoading, setFormLoading] = useState(false);
    const [formError, setFormError] = useState('');
    const [amountError, setAmountError] = useState('');
    const [splitError, setSplitError] = useState('');

    const fetchInvestor = useCallback(() => {
        setInvestorLoading(true);
        setInvestorError(null);
        cashManagementApi.investors.getById(id)
            .then(setInvestor)
            .catch((err) => setInvestorError(extractErrorMessage(err, 'Failed to load investor')))
            .finally(() => setInvestorLoading(false));
    }, [id]);

    useEffect(() => {
        fetchInvestor();
    }, [fetchInvestor]);

    const resetForm = () => {
        setFormData({ amount: '', action_type: 'payout', payout_date: todayLocalDate(), note: '', method_allocations: [] });
        setFormError('');
        setAmountError('');
        setSplitError('');
    };

    const openSettle = (share) => {
        resetForm();
        setSettleShare(share);
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setFormError('');
        setAmountError('');
        setSplitError('');
        setFormLoading(true);
        try {
            const { method_allocations, ...rest } = formData;
            const payload = { ...rest, amount: parseFloat(formData.amount) };
            // Reinvest never crosses accounts — no method is sent for it (see
            // MonthlyProfitDetailPage's identical settle flow for the same rule).
            if (formData.action_type === 'payout') {
                payload.method_allocations = method_allocations;
            }
            await profitsApi.payouts.create(settleShare.id, payload);
            setSettleShare(null);
            resetForm();
            refetch();
            fetchInvestor();
            toast.success(`${formData.action_type === 'reinvest' ? 'Reinvestment' : 'Payout'} recorded successfully`);
        } catch (err) {
            const fieldAmountError = err.response?.data?.amount?.[0];
            const fieldSplitError = err.response?.data?.method_allocations?.[0] || err.response?.data?.splits?.[0];
            if (fieldAmountError) {
                setAmountError(fieldAmountError);
            } else if (fieldSplitError) {
                setSplitError(fieldSplitError);
            } else {
                setFormError(extractErrorMessage(err, 'Failed to record settlement'));
            }
        } finally {
            setFormLoading(false);
        }
    };

    if (!isAdmin) {
        return (
            <div className="text-center py-12">
                <ShieldAlert className="w-10 h-10 text-neutral-300 mx-auto mb-3" />
                <h2 className="text-2xl font-semibold text-neutral-900">Access Denied</h2>
                <p className="text-neutral-500 mt-2">Only admins or superusers can view this.</p>
            </div>
        );
    }

    if (investorLoading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    if (investorError) {
        return (
            <div className="space-y-4">
                <BackLink to="/profits/investors">Back to Investors</BackLink>
                <InlineAlert variant="error" message={investorError} onRetry={fetchInvestor} />
            </div>
        );
    }

    if (!investor) {
        return (
            <div className="text-center py-12">
                <h2 className="text-2xl font-semibold text-neutral-900">Investor Not Found</h2>
                <BackLink to="/profits/investors" className="mt-4">Back to Investors</BackLink>
            </div>
        );
    }

    const columns = [
        { key: 'period', label: 'Month', render: (v) => formatMonthLabel(v) },
        { key: 'share_percent_snapshot', label: 'Share %', render: (v) => `${fmt(v)}%` },
        { key: 'share_amount', label: 'Share Amount', render: (v) => `Rs. ${fmt(v)}` },
        { key: 'amount_settled', label: 'Settled', render: (v) => `Rs. ${fmt(v)}` },
        { key: 'amount_remaining', label: 'Remaining', render: (v) => `Rs. ${fmt(v)}` },
        { key: 'payment_status', label: 'Status', render: (v) => statusBadge(v) },
    ];

    return (
        <div className="space-y-6">
            <InlineAlert
                variant="warning"
                message="Profit share figures here are computed from an internal estimate, not a certified valuation. Review with an accountant before settling anything. The developer is not responsible at all for decisions made from this page."
            />

            <div>
                <BackLink to="/profits/investors">Back to Investors</BackLink>
                <h1 className="text-3xl font-bold text-neutral-900 mt-2">{investor.name}</h1>
                <p className="text-neutral-500">{investor.contact_number || investor.email || '—'}</p>
            </div>

            {/* Header stats */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <Card className="p-4">
                    <div className="flex items-center gap-2 mb-1">
                        <Wallet className="w-4 h-4 text-info-500" />
                        <p className="text-xs text-neutral-500">Current Invested Money</p>
                    </div>
                    <p className="text-xl font-bold text-info-600">Rs. {fmt(investor.total_invested)}</p>
                    <p className="text-xs text-neutral-400 mt-1">All-time, gross</p>
                </Card>
                <Card className="p-4">
                    <div className="flex items-center gap-2 mb-1">
                        <ArrowDownCircle className="w-4 h-4 text-orange-500" />
                        <p className="text-xs text-neutral-500">Current Withdrawal</p>
                    </div>
                    <p className="text-xl font-bold text-orange-600">Rs. {fmt(investor.total_withdrawn)}</p>
                    <p className="text-xs text-neutral-400 mt-1">All-time, gross</p>
                </Card>
                <Card className="p-4">
                    <div className="flex items-center gap-2 mb-1">
                        <TrendingUp className="w-4 h-4 text-success-500" />
                        <p className="text-xs text-neutral-500">Net Stake</p>
                    </div>
                    <p className="text-xl font-bold text-success-600">Rs. {fmt(investor.net_stake)}</p>
                    <p className="text-xs text-neutral-400 mt-1">Invested minus withdrawn</p>
                </Card>
            </div>

            {/* Profit shares by month — pay for profit only, withdrawals live in Cash Management */}
            <Card className="p-6">
                <h3 className="font-semibold text-neutral-900 mb-1">Monthly Profit Shares</h3>
                <p className="text-sm text-neutral-500 mb-4">
                    Settle this investor's profit share, month by month — payouts or reinvestments only.
                    Capital withdrawals aren't handled here; use Cash Management → Investors for those.
                </p>

                {sharesError ? (
                    <InlineAlert variant="error" message={sharesError} onRetry={refetch} />
                ) : sharesLoading ? (
                    <div className="flex items-center justify-center py-8">
                        <LoadingSpinner size="lg" />
                    </div>
                ) : shares.length === 0 ? (
                    <EmptyState
                        icon={<ReceiptText className="w-8 h-8 text-neutral-400" />}
                        title="No Shares Yet"
                        description="No finalized months with a share for this investor yet."
                    />
                ) : (
                    <>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="text-left text-neutral-500 border-b border-neutral-200">
                                        {columns.map((c) => (
                                            <th key={c.key} className="pb-2 font-medium">{c.label}</th>
                                        ))}
                                        <th className="pb-2 font-medium"></th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {shares.map((share) => (
                                        <tr key={share.id} className="border-b border-neutral-100">
                                            {columns.map((c) => (
                                                <td key={c.key} className="py-2 text-neutral-700">
                                                    {c.render ? c.render(share[c.key]) : share[c.key]}
                                                </td>
                                            ))}
                                            <td className="py-2 text-right">
                                                {parseFloat(share.amount_remaining) > 0 && (
                                                    <Button size="sm" variant="secondary" onClick={() => openSettle(share)}>
                                                        Pay for Profit
                                                    </Button>
                                                )}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                        {meta.totalPages > 1 && (
                            <div className="mt-4">
                                <Pagination currentPage={meta.currentPage} totalPages={meta.totalPages} onPageChange={setPage} />
                            </div>
                        )}
                    </>
                )}
            </Card>

            {/* Settle modal */}
            <Modal
                isOpen={!!settleShare}
                onClose={() => { setSettleShare(null); resetForm(); }}
                title={`Pay for Profit — ${settleShare ? formatMonthLabel(settleShare.period) : ''}`}
                size="lg"
            >
                {settleShare && (
                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div className="p-3 bg-neutral-50 rounded-lg text-sm text-neutral-600">
                            Share amount: <strong>Rs. {fmt(settleShare.share_amount)}</strong> · Remaining: <strong>Rs. {fmt(settleShare.amount_remaining)}</strong>
                        </div>

                        <Input
                            label="Amount (PKR)"
                            type="number"
                            step="0.01"
                            min="0.01"
                            max={settleShare.amount_remaining}
                            value={formData.amount}
                            onChange={(e) => { setFormData({ ...formData, amount: e.target.value }); setAmountError(''); }}
                            error={amountError}
                            required
                        />

                        <div>
                            <label className="block text-sm font-medium text-neutral-700 mb-1.5">Action</label>
                            <div className="flex gap-3">
                                <button
                                    type="button"
                                    onClick={() => setFormData({ ...formData, action_type: 'payout' })}
                                    className={`flex-1 px-4 py-3 rounded-xl border text-sm font-medium transition-colors ${formData.action_type === 'payout' ? 'border-primary-500 bg-primary-50 text-primary-700' : 'border-neutral-200 text-neutral-600'}`}
                                >
                                    Pay Out
                                    <p className="text-xs font-normal mt-0.5 opacity-75">Cash leaves the business</p>
                                </button>
                                <button
                                    type="button"
                                    onClick={() => { setFormData({ ...formData, action_type: 'reinvest', method_allocations: [] }); setSplitError(''); }}
                                    className={`flex-1 px-4 py-3 rounded-xl border text-sm font-medium transition-colors ${formData.action_type === 'reinvest' ? 'border-primary-500 bg-primary-50 text-primary-700' : 'border-neutral-200 text-neutral-600'}`}
                                >
                                    Reinvest
                                    <p className="text-xs font-normal mt-0.5 opacity-75">Cash out, then back in as new investment</p>
                                </button>
                            </div>
                        </div>

                        <Input
                            label="Date"
                            type="date"
                            value={formData.payout_date}
                            onChange={(e) => setFormData({ ...formData, payout_date: e.target.value })}
                            required
                        />
                        <Input
                            label="Note"
                            value={formData.note}
                            onChange={(e) => setFormData({ ...formData, note: e.target.value })}
                            placeholder="Optional"
                        />

                        {formData.action_type === 'payout' && (
                            <div>
                                <label className="block text-sm font-medium text-neutral-700 mb-1.5">Pay Via</label>
                                <MethodSplitPicker
                                    totalAmount={formData.amount}
                                    value={formData.method_allocations}
                                    onChange={(value) => setFormData({ ...formData, method_allocations: value })}
                                    error={splitError}
                                />
                            </div>
                        )}

                        {formData.amount && parseFloat(formData.amount) > 0 && (
                            <InlineAlert
                                variant="info"
                                message={
                                    formData.action_type === 'reinvest'
                                        ? `Rs. ${fmt(formData.amount)} will leave cash in hand, then immediately come back in as a new investment for ${investor.name} — net cash effect is zero, but both are recorded.`
                                        : `This will deduct Rs. ${fmt(formData.amount)} from cash in hand, paid to ${investor.name}.`
                                }
                            />
                        )}

                        {formError && <InlineAlert variant="error" message={formError} />}

                        <div className="flex justify-end gap-3 pt-4">
                            <Button type="button" variant="secondary" onClick={() => { setSettleShare(null); resetForm(); }}>
                                Cancel
                            </Button>
                            <Button
                                type="submit"
                                loading={formLoading}
                                disabled={formData.action_type === 'payout' && !isSplitBalanced(formData.amount, formData.method_allocations)}
                            >
                                {formData.action_type === 'reinvest' ? 'Reinvest' : 'Pay Out'}
                            </Button>
                        </div>
                    </form>
                )}
            </Modal>
        </div>
    );
};

export default ProfitInvestorDetailPage;
