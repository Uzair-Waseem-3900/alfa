import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, CheckCircle2, Clock, Landmark, Wallet, Scale, Printer } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { useBalanceSheet } from '../../hooks/useAccounting';
import { printReport } from '../../utils/print';
import { extractErrorMessage } from '../../utils/errorMessage';
import Card from '../../components/ui/Card';
import Button from '../../components/ui/Button';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import InlineAlert from '../../components/ui/InlineAlert';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const Line = ({ label, amount, bold }) => (
    <div className={`flex items-center justify-between py-2 ${bold ? '' : 'border-b border-neutral-100'}`}>
        <span className={bold ? 'font-semibold text-neutral-900' : 'text-sm text-neutral-600'}>{label}</span>
        <span className={bold ? 'font-bold text-neutral-900' : 'text-sm font-medium text-neutral-800'}>
            Rs. {fmt(amount)}
        </span>
    </div>
);

const BalanceSheetPage = () => {
    const { user } = useAuth();
    const navigate = useNavigate();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const [printing, setPrinting] = useState(false);

    const { data, loading, error, refetch } = useBalanceSheet({});

    if (!isAdmin) {
        navigate('/dashboard');
        return null;
    }

    const handlePrint = async () => {
        setPrinting(true);
        try {
            await printReport('/accounting/balance-sheet/print/', {});
        } catch (err) {
            toast.error(extractErrorMessage(err, 'Failed to print statement'));
        } finally {
            setPrinting(false);
        }
    };

    return (
        <div className="space-y-6">
            <div className="p-4 bg-amber-50 border-l-4 border-amber-500 rounded-r-xl flex gap-3">
                <AlertTriangle className="w-5 h-5 flex-shrink-0 mt-0.5 text-amber-600" />
                <div>
                    <p className="text-sm font-semibold text-amber-800">
                        This is an internal estimate, not a certified financial statement.
                    </p>
                    <p className="text-sm text-amber-700 mt-0.5">
                        This always shows today's snapshot — older days were never recorded and can't be
                        reconstructed accurately after the fact. Always double-check these numbers and
                        consult a qualified accountant before making financial decisions based on this page.
                    </p>
                </div>
            </div>

            <div className="flex items-start justify-between gap-4">
                <div>
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-700 to-accent-600 flex items-center justify-center shadow-md shadow-primary-900/20 flex-shrink-0">
                            <Landmark className="w-5 h-5 text-white" />
                        </div>
                        <h1 className="text-3xl font-bold text-neutral-900">Balance Sheet</h1>
                    </div>
                    <p className="text-neutral-500 mt-1">
                        A snapshot of everything your business owns, owes, and is worth, as of today.
                    </p>
                </div>
                <Button variant="secondary" icon={Printer} onClick={handlePrint} loading={printing}>
                    Print
                </Button>
            </div>

            {error && (
                <InlineAlert variant="error" message={error} onRetry={refetch} />
            )}

            {loading ? (
                <div className="flex items-center justify-center min-h-[40vh]">
                    <LoadingSpinner size="lg" />
                </div>
            ) : data && (
                <>
                    {data.freshness?.is_stale && (
                        <Card className="p-4 flex items-start gap-3 bg-warning-50 border-l-4 border-warning-500">
                            <Clock className="w-5 h-5 text-warning-600 flex-shrink-0 mt-0.5" />
                            <div>
                                <p className="text-sm font-semibold text-warning-700">
                                    These figures were saved {data.freshness.lag_days} days after the month ended
                                </p>
                                <p className="text-xs text-warning-600 mt-0.5">
                                    A month's Balance Sheet has to be saved soon after that month finishes.
                                    This one was saved on{' '}
                                    {new Date(data.freshness.snapshot_taken_on).toLocaleDateString()}, so it may
                                    include sales, payments and expenses that actually belong to the following
                                    month. Treat these numbers as approximate — the "As of Today" view above is
                                    always exact.
                                </p>
                            </div>
                        </Card>
                    )}

                    <Card className={`p-4 flex items-center gap-3 ${data.is_balanced ? 'bg-success-50 border border-success-100' : 'bg-error-50 border border-error-100'}`}>
                        {data.is_balanced ? (
                            <CheckCircle2 className="w-5 h-5 text-success-600 flex-shrink-0" />
                        ) : (
                            <AlertTriangle className="w-5 h-5 text-error-600 flex-shrink-0" />
                        )}
                        <div>
                            <p className={`text-sm font-semibold ${data.is_balanced ? 'text-success-700' : 'text-error-700'}`}>
                                {data.is_balanced ? 'Your books are balanced' : 'Your books do not balance'}
                            </p>
                            <p className={`text-xs mt-0.5 ${data.is_balanced ? 'text-success-600' : 'text-error-600'}`}>
                                {data.is_balanced
                                    ? "What you own exactly equals what you owe plus what you're worth — as it should."
                                    : `Off by Rs. ${fmt(Math.abs(data.balance_check))} — this points to a real data issue and needs investigating.`}
                            </p>
                        </div>
                    </Card>

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                        <Card className="p-5">
                            <div className="flex items-center gap-2.5 mb-1">
                                <Wallet className="w-5 h-5 text-primary-600" />
                                <h3 className="font-semibold text-neutral-900">Assets</h3>
                            </div>
                            <p className="text-xs text-neutral-500 mb-4">Everything your business owns.</p>
                            <Line label="Cash in Hand" amount={data.assets.cash_in_hand} />
                            <Line label="Money Customers Owe You" amount={data.assets.accounts_receivable} />
                            <Line label="Inventory Value" amount={data.assets.inventory_value} />
                            <Line label="Equipment &amp; Fixed Assets" amount={data.assets.fixed_assets_nbv} />
                            <div className="pt-3 mt-2 border-t border-neutral-200">
                                <Line label="Total Assets" amount={data.assets.total} bold />
                            </div>
                        </Card>

                        <div className="space-y-4">
                            <Card className="p-5">
                                <div className="flex items-center gap-2.5 mb-1">
                                    <Scale className="w-5 h-5 text-warning-600" />
                                    <h3 className="font-semibold text-neutral-900">Liabilities</h3>
                                </div>
                                <p className="text-xs text-neutral-500 mb-4">Everything your business owes.</p>
                                <Line label="Money You Owe Suppliers" amount={data.liabilities.accounts_payable} />
                                <Line label="GST Owed to FBR" amount={data.liabilities.gst_payable} />
                                <Line label="WHT Owed to FBR" amount={data.liabilities.wht_payable} />
                                <div className="pt-3 mt-2 border-t border-neutral-200">
                                    <Line label="Total Liabilities" amount={data.liabilities.total} bold />
                                </div>
                            </Card>

                            <Card className="p-5">
                                <div className="flex items-center gap-2.5 mb-1">
                                    <Landmark className="w-5 h-5 text-success-600" />
                                    <h3 className="font-semibold text-neutral-900">Equity</h3>
                                </div>
                                <p className="text-xs text-neutral-500 mb-4">Your ownership stake in the business.</p>
                                <Line label="Owner's Capital" amount={data.equity.owner_capital} />
                                <Line label="Investors' Capital" amount={data.equity.investor_capital} />
                                <Line label="Opening Balance (Pre-Existing Debts/Stock)" amount={data.equity.opening_balance_equity} />
                                <Line label="Equipment You Already Owned" amount={data.equity.pre_owned_asset_equity} />
                                <Line label="Increase in Equipment Value (Revaluation)" amount={data.equity.asset_revaluation_surplus} />
                                <Line label="Retained Earnings (Undistributed Profit)" amount={data.equity.retained_earnings} />
                                <div className="pt-3 mt-2 border-t border-neutral-200">
                                    <Line label="Total Equity" amount={data.equity.total} bold />
                                </div>
                            </Card>
                        </div>
                    </div>
                </>
            )}
        </div>
    );
};

export default BalanceSheetPage;
