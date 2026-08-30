import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, ArrowLeftRight, TrendingUp, TrendingDown, Building2, Printer } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { useCashFlowStatement } from '../../hooks/useAccounting';
import { todayLocalDate } from '../../utils/helpers';
import { printReport } from '../../utils/print';
import { extractErrorMessage } from '../../utils/errorMessage';
import Card from '../../components/ui/Card';
import Input from '../../components/ui/Input';
import Button from '../../components/ui/Button';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import InlineAlert from '../../components/ui/InlineAlert';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const StatementLine = ({ label, amount }) => (
    <div className="flex items-center justify-between py-2 border-b border-neutral-100 last:border-0">
        <span className="text-sm text-neutral-600">{label}</span>
        <span className={`text-sm font-medium ${amount < 0 ? 'text-error-600' : 'text-success-600'}`}>
            {amount < 0 ? '(' : ''}Rs. {fmt(Math.abs(amount))}{amount < 0 ? ')' : ''}
        </span>
    </div>
);

const ActivitySection = ({ icon: Icon, title, subtitle, activity }) => (
    <Card className="p-5">
        <div className="flex items-center gap-2.5 mb-1">
            <Icon className="w-5 h-5 text-primary-600" />
            <h3 className="font-semibold text-neutral-900">{title}</h3>
        </div>
        <p className="text-xs text-neutral-500 mb-4">{subtitle}</p>
        {activity.lines.length === 0 ? (
            <p className="text-sm text-neutral-400 italic py-2">No activity in this period.</p>
        ) : (
            activity.lines.map((line, i) => <StatementLine key={i} label={line.label} amount={parseFloat(line.amount)} />)
        )}
        <div className="flex items-center justify-between pt-3 mt-2 border-t border-neutral-200">
            <span className="text-sm font-semibold text-neutral-900">Net</span>
            <span className={`text-sm font-bold ${activity.net < 0 ? 'text-error-600' : 'text-success-600'}`}>
                Rs. {fmt(activity.net)}
            </span>
        </div>
    </Card>
);

const CashFlowStatementPage = () => {
    const { user } = useAuth();
    const navigate = useNavigate();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const today = todayLocalDate();
    const defaultFrom = today.slice(0, 8) + '01';
    const [dateFrom, setDateFrom] = useState(defaultFrom);
    const [dateTo, setDateTo] = useState(today);
    const [appliedRange, setAppliedRange] = useState({ date_from: defaultFrom, date_to: today });
    const [printing, setPrinting] = useState(false);

    const { data, loading, error, refetch } = useCashFlowStatement(appliedRange);

    if (!isAdmin) {
        navigate('/dashboard');
        return null;
    }

    const handleApply = () => setAppliedRange({ date_from: dateFrom, date_to: dateTo });

    const handlePrint = async () => {
        setPrinting(true);
        try {
            // Prints exactly the currently-applied range, not whatever is
            // sitting unsaved in the date inputs.
            await printReport('/accounting/cash-flow-statement/print/', appliedRange);
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
                        Always double-check these numbers and consult a qualified accountant before making
                        financial decisions based on this page.
                    </p>
                </div>
            </div>

            <div>
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-700 to-accent-600 flex items-center justify-center shadow-md shadow-primary-900/20 flex-shrink-0">
                        <ArrowLeftRight className="w-5 h-5 text-white" />
                    </div>
                    <h1 className="text-3xl font-bold text-neutral-900">Cash Flow Statement</h1>
                </div>
                <p className="text-neutral-500 mt-1">
                    Where your cash actually came from and where it went, for the period you pick below —
                    not the same as profit, this is real money moving in and out.
                </p>
            </div>

            <Card className="p-4">
                <div className="flex flex-wrap items-end gap-3">
                    <Input type="date" label="From" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
                    <Input type="date" label="To" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
                    <Button onClick={handleApply}>Apply</Button>
                    <Button variant="secondary" icon={Printer} onClick={handlePrint} loading={printing}>
                        Print
                    </Button>
                </div>
            </Card>

            {error && <InlineAlert variant="error" message={error} onRetry={refetch} />}

            {loading ? (
                <div className="flex items-center justify-center min-h-[40vh]">
                    <LoadingSpinner size="lg" />
                </div>
            ) : data && (
                <>
                    {(data.opening_cash !== null || data.closing_cash !== null) && (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            {data.opening_cash !== null && (
                                <Card className="p-4">
                                    <p className="text-xs text-neutral-500 mb-1">Cash You Started With</p>
                                    <p className="text-xl font-bold text-neutral-900">Rs. {fmt(data.opening_cash)}</p>
                                </Card>
                            )}
                            {data.closing_cash !== null && (
                                <Card className="p-4">
                                    <p className="text-xs text-neutral-500 mb-1">Cash You Have Now</p>
                                    <p className="text-xl font-bold text-neutral-900">Rs. {fmt(data.closing_cash)}</p>
                                </Card>
                            )}
                        </div>
                    )}

                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                        <ActivitySection
                            icon={TrendingUp}
                            title="Operating Activities"
                            subtitle="Cash from everyday running of the business — sales, expenses, supplier payments, taxes."
                            activity={data.operating}
                        />
                        <ActivitySection
                            icon={Building2}
                            title="Investing Activities"
                            subtitle="Cash from buying or selling long-term things like equipment or vehicles."
                            activity={data.investing}
                        />
                        <ActivitySection
                            icon={TrendingDown}
                            title="Financing Activities"
                            subtitle="Cash from owners/investors putting money in or taking money out."
                            activity={data.financing}
                        />
                    </div>

                    <Card className="p-5 bg-primary-50 border border-primary-100">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="font-semibold text-neutral-900">Net Change in Cash</p>
                                <p className="text-xs text-neutral-500 mt-0.5">
                                    How much your total cash grew or shrank over this period.
                                </p>
                            </div>
                            <p className={`text-2xl font-bold ${data.net_change_in_cash < 0 ? 'text-error-600' : 'text-success-600'}`}>
                                Rs. {fmt(data.net_change_in_cash)}
                            </p>
                        </div>
                    </Card>
                </>
            )}
        </div>
    );
};

export default CashFlowStatementPage;
