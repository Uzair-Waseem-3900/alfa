import { useState, Fragment } from 'react';
import { useParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { useMonthlyProfitDetail, useCurrentMonthProfit } from '../../hooks/useProfits';
import { profitsApi } from '../../services/profitsApi';
import { extractErrorMessage } from '../../utils/errorMessage';
import { todayLocalDate } from '../../utils/helpers';
import MethodSplitPicker, { isSplitBalanced } from '../../components/paymentMethods/MethodSplitPicker';
import Card from '../../components/ui/Card';
import Button from '../../components/ui/Button';
import Badge from '../../components/ui/Badge';
import Modal from '../../components/ui/Modal';
import Input from '../../components/ui/Input';
import BackLink from '../../components/ui/BackLink';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import InlineAlert from '../../components/ui/InlineAlert';
import { TrendingUp, ShieldAlert, Undo2 } from 'lucide-react';

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

// Reinvest payouts default silently to Cash on both legs (never a real
// method choice), so only show the "via ..." breakdown for real payouts.
const formatAllocations = (allocations) => {
    if (!allocations || allocations.length === 0) return '';
    return allocations.map((a) => `${a.payment_method_name} (Rs. ${fmt(a.amount)})`).join(', ');
};

const DeductionRow = ({ label, value, hint }) => (
    <div className="flex items-center justify-between py-2 border-b border-neutral-100 last:border-0">
        <div>
            <p className="text-sm text-neutral-700">{label}</p>
            {hint && <p className="text-xs text-neutral-400">{hint}</p>}
        </div>
        <p className="text-sm font-medium text-error-600">− Rs. {fmt(value)}</p>
    </div>
);

const AdditionRow = ({ label, value, hint }) => (
    <div className="flex items-center justify-between py-2 border-b border-neutral-100 last:border-0">
        <div>
            <p className="text-sm text-neutral-700">{label}</p>
            {hint && <p className="text-xs text-neutral-400">{hint}</p>}
        </div>
        <p className="text-sm font-medium text-success-600">+ Rs. {fmt(value)}</p>
    </div>
);

const MonthlyProfitDetailPage = () => {
    const { period } = useParams();
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';
    const isCurrent = period === 'current';

    // Both hooks are always called (rules-of-hooks safe across navigation
    // between a finalized month and "current" without remounting) — only
    // the relevant one's result is actually used below.
    const {
        data: finalizedData, loading: finalizedLoading, error: finalizedError, refetch: refetchFinalized,
    } = useMonthlyProfitDetail(isCurrent ? null : period);
    const {
        data: currentData, loading: currentLoading, error: currentError, refetch: refetchCurrent,
    } = useCurrentMonthProfit();

    const mp      = isCurrent ? currentData : finalizedData;
    const loading = isCurrent ? currentLoading : finalizedLoading;
    const error   = isCurrent ? currentError : finalizedError;
    const refetch = isCurrent ? refetchCurrent : refetchFinalized;

    // settleType tracks WHICH api ('investor' or 'owner') the open modal /
    // pending delete should hit — the two settle flows are identical in
    // shape, just pointed at different backend endpoints.
    const [settleShare, setSettleShare] = useState(null);
    const [settleType, setSettleType] = useState('investor');
    const [formData, setFormData] = useState({
        amount: '', action_type: 'payout', payout_date: todayLocalDate(), note: '', method_allocations: [],
    });
    const [formLoading, setFormLoading] = useState(false);
    const [formError, setFormError] = useState('');
    const [amountError, setAmountError] = useState('');
    const [splitError, setSplitError] = useState('');
    const [deleteConfirm, setDeleteConfirm] = useState(null);
    const [deleteType, setDeleteType] = useState('investor');
    const [deleteLoading, setDeleteLoading] = useState(false);

    const resetForm = () => {
        setFormData({ amount: '', action_type: 'payout', payout_date: todayLocalDate(), note: '', method_allocations: [] });
        setFormError('');
        setAmountError('');
        setSplitError('');
    };

    const openSettle = (share, type = 'investor') => {
        resetForm();
        setSettleShare(share);
        setSettleType(type);
    };

    const openDeleteConfirm = (payout, type = 'investor') => {
        setDeleteConfirm(payout);
        setDeleteType(type);
    };

    const settleLabel = settleType === 'owner' ? 'Owner' : (settleShare?.investor_name_snapshot ?? '');

    const handleSubmit = async (e) => {
        e.preventDefault();
        setFormError('');
        setAmountError('');
        setSplitError('');
        setFormLoading(true);
        try {
            const api = settleType === 'owner' ? profitsApi.ownerPayouts : profitsApi.payouts;
            const { method_allocations, ...rest } = formData;
            const payload = { ...rest, amount: parseFloat(formData.amount) };
            // Reinvest is a bookkeeping equity swap — no real money crosses
            // accounts, so no method is sent (backend silently defaults both
            // legs to Cash). Only a payout sends the chosen split.
            if (formData.action_type === 'payout') {
                payload.method_allocations = method_allocations;
            }
            await api.create(settleShare.id, payload);
            setSettleShare(null);
            resetForm();
            refetch();
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

    const handleDeletePayout = async (payoutId) => {
        setDeleteLoading(true);
        try {
            const api = deleteType === 'owner' ? profitsApi.ownerPayouts : profitsApi.payouts;
            await api.delete(payoutId);
            setDeleteConfirm(null);
            refetch();
            toast.success('Settlement reversed and cash in hand restored');
        } catch (err) {
            setDeleteConfirm(null);
            toast.error(extractErrorMessage(err, 'Failed to reverse this settlement'));
        } finally {
            setDeleteLoading(false);
        }
    };

    if (!isAdmin) {
        return (
            <div className="text-center py-12">
                <ShieldAlert className="w-10 h-10 text-neutral-300 mx-auto mb-3" />
                <h2 className="text-2xl font-semibold text-neutral-900">Access Denied</h2>
                <p className="text-neutral-500 mt-2">Only admins or superusers can view monthly profits.</p>
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

    if (error) {
        return (
            <div className="space-y-4">
                <BackLink to="/monthly-profits">Back to Monthly Profits</BackLink>
                <InlineAlert variant="error" message={error} onRetry={refetch} />
            </div>
        );
    }

    if (!mp) {
        return (
            <div className="text-center py-12">
                <h2 className="text-2xl font-semibold text-neutral-900">Month Not Found</h2>
                <BackLink to="/monthly-profits" className="mt-4">Back to Monthly Profits</BackLink>
            </div>
        );
    }

    const netProfitPositive = parseFloat(mp.net_profit) >= 0;

    return (
        <div className="space-y-6">
            <InlineAlert
                variant="warning"
                title="This is an internal estimate, not a certified valuation."
                message="Computed from cash, inventory, assets, receivables, payables, and tax figures already tracked elsewhere in this system. Review with an accountant before using it to actually distribute profit. The developer is not responsible at all for decisions made from this page."
            />

            <div>
                <BackLink to="/monthly-profits">Back to Monthly Profits</BackLink>
                <div className="flex items-center gap-3 mt-2">
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-600 to-accent-600 flex items-center justify-center shadow-lg shadow-primary-900/20 flex-shrink-0">
                        <TrendingUp className="w-5 h-5 text-white" />
                    </div>
                    <h1 className="text-3xl font-bold text-neutral-900">{formatMonthLabel(mp.period)}</h1>
                    {isCurrent && (
                        <span className="text-xs font-medium text-amber-700 bg-amber-100 px-2 py-0.5 rounded-full">
                            In progress — provisional
                        </span>
                    )}
                </div>
                <p className={`text-lg font-semibold mt-1 ${netProfitPositive ? 'text-success-600' : 'text-error-600'}`}>
                    Net Profit: Rs. {fmt(mp.net_profit)}
                </p>
                {isCurrent && (
                    <p className="text-sm text-neutral-500 mt-1">
                        Still accumulating — figures will keep changing until the month ends and finalizes.
                    </p>
                )}
            </div>

            {/* Breakdown */}
            <Card className="p-6">
                <h3 className="font-semibold text-neutral-900 mb-4">How This Was Calculated</h3>

                <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
                    <div>
                        <p className="text-xs text-neutral-500">Gross Revenue</p>
                        <p className="font-semibold text-neutral-900">Rs. {fmt(mp.gross_revenue)}</p>
                    </div>
                    <div>
                        <p className="text-xs text-neutral-500">Gross COGS</p>
                        <p className="font-semibold text-neutral-900">Rs. {fmt(mp.gross_cogs)}</p>
                    </div>
                    <div>
                        <p className="text-xs text-neutral-500">Gross Profit</p>
                        <p className="font-semibold text-neutral-900">Rs. {fmt(mp.gross_profit)}</p>
                    </div>
                </div>

                <div className="p-3 bg-neutral-50 rounded-lg flex items-center justify-between mb-4">
                    <p className="text-sm text-neutral-600">Net Gross Profit (after returns accepted this month)</p>
                    <p className="font-semibold text-neutral-900">Rs. {fmt(mp.net_gross_profit)}</p>
                </div>

                <div className="space-y-0">
                    <DeductionRow label="Expenses Paid" value={mp.expenses_paid} />
                    <DeductionRow label="Recurring Expenses Paid" value={mp.recurring_expenses_paid} hint="Rent, salaries, utilities, etc." />
                    <DeductionRow label="GST Paid" value={mp.gst_paid} />
                    <DeductionRow label="WHT Paid" value={mp.wht_paid} />
                    <DeductionRow label="Lost Cash" value={mp.lost_cash} />
                    <AdditionRow label="Found Cash" value={mp.found_cash} />
                    <DeductionRow label="Lost Inventory" value={mp.lost_inventory} />
                    <AdditionRow label="Found Inventory" value={mp.found_inventory} />
                    <DeductionRow label="Depreciation" value={mp.depreciation} />
                    <div className="flex items-center justify-between py-2">
                        <p className="text-sm text-neutral-700">Disposal Gain / Loss</p>
                        <p className={`text-sm font-medium ${parseFloat(mp.disposal_gain_loss) >= 0 ? 'text-success-600' : 'text-error-600'}`}>
                            {parseFloat(mp.disposal_gain_loss) >= 0 ? '+' : '−'} Rs. {fmt(Math.abs(parseFloat(mp.disposal_gain_loss)))}
                        </p>
                    </div>
                </div>

                <div className="mt-4 pt-4 border-t-2 border-neutral-200 flex items-center justify-between">
                    <p className="font-semibold text-neutral-900">Net Profit</p>
                    <p className={`text-xl font-bold ${netProfitPositive ? 'text-success-600' : 'text-error-600'}`}>
                        Rs. {fmt(mp.net_profit)}
                    </p>
                </div>
            </Card>

            {/* Ownership split — a live PREVIEW for the current month (today's
                ownership % applied to the still-moving net profit — no settle
                actions, since nothing here is final yet); a real, frozen
                snapshot with settle actions for finalized months. */}
            {isCurrent ? (
                <Card className="p-6 border-2 border-dashed border-amber-300 bg-amber-50/40">
                    <div className="flex items-center gap-2 mb-1">
                        <h3 className="font-semibold text-neutral-900">Ownership Split — Preview</h3>
                        <span className="text-xs font-medium text-amber-700 bg-amber-100 px-2 py-0.5 rounded-full">
                            Informational only
                        </span>
                    </div>
                    <p className="text-sm text-amber-700 mb-4">
                        Today's ownership % applied to this month's still-moving net profit — nothing here is
                        final, and no settlement can be recorded until the month finalizes.
                    </p>
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="text-left text-neutral-500 border-b border-amber-200">
                                    <th className="pb-2 font-medium">Investor</th>
                                    <th className="pb-2 font-medium">Share %</th>
                                    <th className="pb-2 font-medium">Share Amount (preview)</th>
                                </tr>
                            </thead>
                            <tbody>
                                {mp.investors_preview.map((inv) => (
                                    <tr key={inv.id} className="border-b border-amber-100">
                                        <td className="py-2 text-neutral-900">{inv.name}</td>
                                        <td className="py-2 text-neutral-700">{fmt(inv.share_percent)}%</td>
                                        <td className="py-2 text-neutral-700">Rs. {fmt(inv.share_amount)}</td>
                                    </tr>
                                ))}
                                <tr>
                                    <td className="py-2 font-semibold text-neutral-900">Owner</td>
                                    <td className="py-2 font-semibold text-neutral-900">{fmt(mp.owner_share_percent)}%</td>
                                    <td className="py-2 font-semibold text-neutral-900">Rs. {fmt(mp.owner_share_amount_preview)}</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </Card>
            ) : (
            <Card className="p-8">
                <h3 className="text-lg font-semibold text-neutral-900 mb-5">Ownership Split</h3>
                <div className="overflow-x-auto">
                    <table className="w-full text-[15px]">
                        <thead>
                            <tr className="text-left text-neutral-500 border-b border-neutral-200">
                                <th className="pb-3 font-medium">Investor</th>
                                <th className="pb-3 font-medium">Share %</th>
                                <th className="pb-3 font-medium">Share Amount</th>
                                <th className="pb-3 font-medium">Settled</th>
                                <th className="pb-3 font-medium">Remaining</th>
                                <th className="pb-3 font-medium">Status</th>
                                <th className="pb-3 font-medium"></th>
                            </tr>
                        </thead>
                        <tbody>
                            {mp.investor_shares.map((share) => (
                                <Fragment key={share.id}>
                                    <tr className="border-b border-neutral-100">
                                        <td className="py-3 text-neutral-900">{share.investor_name_snapshot}</td>
                                        <td className="py-3 text-neutral-700">{fmt(share.share_percent_snapshot)}%</td>
                                        <td className="py-3 text-neutral-700">Rs. {fmt(share.share_amount)}</td>
                                        <td className="py-3 text-neutral-700">Rs. {fmt(share.amount_settled)}</td>
                                        <td className="py-3 text-neutral-700">Rs. {fmt(share.amount_remaining)}</td>
                                        <td className="py-3">{statusBadge(share.payment_status)}</td>
                                        <td className="py-3 text-right">
                                            {parseFloat(share.amount_remaining) > 0 && (
                                                <Button size="sm" variant="secondary" onClick={() => openSettle(share, 'investor')}>
                                                    Settle Share
                                                </Button>
                                            )}
                                        </td>
                                    </tr>
                                    {share.payouts.length > 0 && (
                                        <tr>
                                            <td colSpan={7} className="pb-4">
                                                <div className="ml-2 space-y-1.5">
                                                    {share.payouts.map((p) => (
                                                        <div key={p.id} className="flex items-center justify-between text-sm bg-neutral-50 rounded-lg px-3 py-2.5">
                                                            <span className="text-neutral-600">
                                                                {p.action_type === 'reinvest' ? 'Reinvested' : 'Paid out'}{' '}
                                                                <strong>Rs. {fmt(p.amount)}</strong> on {new Date(p.payout_date).toLocaleDateString()}
                                                                {p.action_type === 'payout' && p.allocations?.length > 0 && (
                                                                    <> — via {formatAllocations(p.allocations)}</>
                                                                )}
                                                                {p.note && ` — ${p.note}`}
                                                            </span>
                                                            <button
                                                                onClick={() => openDeleteConfirm(p, 'investor')}
                                                                className="inline-flex items-center gap-1 text-error-600 hover:text-error-700 font-medium min-h-[44px] px-2"
                                                            >
                                                                <Undo2 className="w-3.5 h-3.5" />
                                                                Reverse
                                                            </button>
                                                        </div>
                                                    ))}
                                                </div>
                                            </td>
                                        </tr>
                                    )}
                                </Fragment>
                            ))}
                            {mp.owner_share && (
                                <Fragment>
                                    <tr className="border-b border-neutral-100 border-t-2 border-t-neutral-200">
                                        <td className="py-3 font-semibold text-neutral-900">Owner</td>
                                        <td className="py-3 font-semibold text-neutral-900">{fmt(mp.owner_share_percent)}%</td>
                                        <td className="py-3 font-semibold text-neutral-900">Rs. {fmt(mp.owner_share.share_amount)}</td>
                                        <td className="py-3 text-neutral-700">Rs. {fmt(mp.owner_share.amount_settled)}</td>
                                        <td className="py-3 text-neutral-700">Rs. {fmt(mp.owner_share.amount_remaining)}</td>
                                        <td className="py-3">{statusBadge(mp.owner_share.payment_status)}</td>
                                        <td className="py-3 text-right">
                                            {parseFloat(mp.owner_share.amount_remaining) > 0 && (
                                                <Button size="sm" variant="secondary" onClick={() => openSettle(mp.owner_share, 'owner')}>
                                                    Settle Share
                                                </Button>
                                            )}
                                        </td>
                                    </tr>
                                    {mp.owner_share.payouts.length > 0 && (
                                        <tr>
                                            <td colSpan={7} className="pb-4">
                                                <div className="ml-2 space-y-1.5">
                                                    {mp.owner_share.payouts.map((p) => (
                                                        <div key={p.id} className="flex items-center justify-between text-sm bg-neutral-50 rounded-lg px-3 py-2.5">
                                                            <span className="text-neutral-600">
                                                                {p.action_type === 'reinvest' ? 'Reinvested' : 'Paid out'}{' '}
                                                                <strong>Rs. {fmt(p.amount)}</strong> on {new Date(p.payout_date).toLocaleDateString()}
                                                                {p.action_type === 'payout' && p.allocations?.length > 0 && (
                                                                    <> — via {formatAllocations(p.allocations)}</>
                                                                )}
                                                                {p.note && ` — ${p.note}`}
                                                            </span>
                                                            <button
                                                                onClick={() => openDeleteConfirm(p, 'owner')}
                                                                className="inline-flex items-center gap-1 text-error-600 hover:text-error-700 font-medium min-h-[44px] px-2"
                                                            >
                                                                <Undo2 className="w-3.5 h-3.5" />
                                                                Reverse
                                                            </button>
                                                        </div>
                                                    ))}
                                                </div>
                                            </td>
                                        </tr>
                                    )}
                                </Fragment>
                            )}
                        </tbody>
                    </table>
                </div>
                <p className="text-xs text-neutral-400 mt-5">
                    Share % is frozen as of this month — it won't change even if ownership % changes later.
                    An unpaid or partial balance isn't a business liability, it's informational tracking only.
                </p>
            </Card>
            )}

            {/* Settle modal */}
            <Modal
                isOpen={!!settleShare}
                onClose={() => { setSettleShare(null); resetForm(); }}
                title={`Settle Share — ${settleLabel}`}
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
                                        ? `Rs. ${fmt(formData.amount)} will leave cash in hand, then immediately come back in as a new ${settleType === 'owner' ? 'contribution' : 'investment'} for ${settleLabel} — net cash effect is zero, but both are recorded.`
                                        : `This will deduct Rs. ${fmt(formData.amount)} from cash in hand, paid to ${settleLabel}.`
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

            <ConfirmDialog
                isOpen={!!deleteConfirm}
                onClose={() => setDeleteConfirm(null)}
                onConfirm={() => handleDeletePayout(deleteConfirm?.id)}
                title="Reverse Settlement"
                message={`Are you sure you want to reverse this Rs. ${fmt(deleteConfirm?.amount)} ${deleteConfirm?.action_type === 'reinvest' ? 'reinvestment' : 'payout'}? This restores cash in hand${deleteConfirm?.action_type === 'reinvest' ? ` and undoes the linked ${deleteType === 'owner' ? 'contribution' : 'investment'}` : ''}.`}
                loading={deleteLoading}
            />
        </div>
    );
};

export default MonthlyProfitDetailPage;
