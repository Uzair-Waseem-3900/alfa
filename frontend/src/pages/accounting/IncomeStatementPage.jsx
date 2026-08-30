import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, FileBarChart, Printer } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { useIncomeStatement } from '../../hooks/useAccounting';
import { todayLocalDate } from '../../utils/helpers';
import { printReport } from '../../utils/print';
import { extractErrorMessage } from '../../utils/errorMessage';
import Card from '../../components/ui/Card';
import Input from '../../components/ui/Input';
import Button from '../../components/ui/Button';
import Badge from '../../components/ui/Badge';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import InlineAlert from '../../components/ui/InlineAlert';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const Line = ({ label, amount, subtract, bold, indent }) => (
    <div className={`flex items-center justify-between py-2 ${bold ? '' : 'border-b border-neutral-100'} ${indent ? 'pl-4' : ''}`}>
        <span className={bold ? 'font-semibold text-neutral-900' : 'text-sm text-neutral-600'}>{label}</span>
        <span className={bold ? 'font-bold text-neutral-900' : 'text-sm font-medium text-neutral-800'}>
            {subtract ? '(' : ''}Rs. {fmt(amount)}{subtract ? ')' : ''}
        </span>
    </div>
);

const SectionSubtitle = ({ children }) => (
    <p className="text-xs text-neutral-500 mb-2">{children}</p>
);

const IncomeStatementPage = () => {
    const { user } = useAuth();
    const navigate = useNavigate();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const currentPeriod = todayLocalDate().slice(0, 7);
    const [period, setPeriod] = useState(currentPeriod);
    const [appliedPeriod, setAppliedPeriod] = useState(currentPeriod);
    const [printing, setPrinting] = useState(false);

    const { data, loading, error, refetch } = useIncomeStatement({ period: appliedPeriod });

    if (!isAdmin) {
        navigate('/dashboard');
        return null;
    }

    const handlePrint = async () => {
        setPrinting(true);
        try {
            // Prints exactly the currently-applied period, not whatever is
            // sitting unsaved in the month picker.
            await printReport('/accounting/income-statement/print/', { period: appliedPeriod });
        } catch (err) {
            toast.error(extractErrorMessage(err, 'Failed to print statement'));
        } finally {
            setPrinting(false);
        }
    };

    const totalOperatingExpenses = data
        ? Number(data.expenses_paid) + Number(data.recurring_expenses_paid) + Number(data.gst_paid)
            + Number(data.wht_paid) + Number(data.depreciation)
        : 0;

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
                        <FileBarChart className="w-5 h-5 text-white" />
                    </div>
                    <h1 className="text-3xl font-bold text-neutral-900">Income Statement</h1>
                </div>
                <p className="text-neutral-500 mt-1">
                    Also called a Profit &amp; Loss statement — shows whether the business actually made
                    money in the period you pick, after every cost.
                </p>
            </div>

            <Card className="p-4">
                <div className="flex flex-wrap items-end gap-3">
                    <Input type="month" label="Month" value={period} onChange={(e) => setPeriod(e.target.value)} />
                    <Button onClick={() => setAppliedPeriod(period)}>View</Button>
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
                <Card className="p-6">
                    {data.is_provisional && (
                        <div className="mb-4">
                            <Badge variant="warning">Still in progress — this month isn't finished yet</Badge>
                        </div>
                    )}

                    <div className="mb-5">
                        <h3 className="font-semibold text-neutral-900 mb-1">Revenue</h3>
                        <SectionSubtitle>Total sales made this period.</SectionSubtitle>
                        <Line label="Sales Revenue" amount={data.net_revenue} />
                        <Line label="Cost of Goods Sold" amount={data.net_cogs} subtract />
                        <Line label="Gross Profit" amount={data.net_gross_profit} bold />
                    </div>

                    <div className="mb-5">
                        <h3 className="font-semibold text-neutral-900 mb-1">Operating Expenses</h3>
                        <SectionSubtitle>
                            Day-to-day costs of running the business. One-off expenses are listed by
                            category; recurring expenses are shown as a single total on their own line.
                        </SectionSubtitle>
                        {data.expense_breakdown.length === 0 ? (
                            <p className="text-sm text-neutral-400 italic py-2">No one-off expenses this period.</p>
                        ) : (
                            data.expense_breakdown.map((line, i) => (
                                <Line key={i} label={line.category || 'Uncategorized'} amount={line.amount} indent />
                            ))
                        )}
                        <Line label="Recurring Expenses" amount={data.recurring_expenses_paid} indent />
                        <Line label="GST Paid" amount={data.gst_paid} indent />
                        <Line label="WHT Paid" amount={data.wht_paid} indent />
                        <Line label="Depreciation" amount={data.depreciation} indent />
                        <Line label="Total Operating Expenses" amount={totalOperatingExpenses} bold />
                    </div>

                    <div className="mb-5">
                        <h3 className="font-semibold text-neutral-900 mb-1">Other Items</h3>
                        <SectionSubtitle>Cash/inventory found or lost, and gains or losses from selling equipment.</SectionSubtitle>
                        <Line label="Cash Lost" amount={data.lost_cash} indent />
                        <Line label="Cash Found" amount={data.found_cash} indent />
                        <Line label="Inventory Lost" amount={data.lost_inventory} indent />
                        <Line label="Inventory Found" amount={data.found_inventory} indent />
                        <Line label="Gain/(Loss) on Asset Disposal" amount={data.disposal_gain_loss} indent />
                    </div>

                    <div className="pt-4 border-t-2 border-neutral-200">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="font-bold text-lg text-neutral-900">Net Income</p>
                                <p className="text-xs text-neutral-500 mt-0.5">
                                    What's actually left over — the real profit for this period.
                                </p>
                            </div>
                            <p className={`text-2xl font-bold ${data.net_profit < 0 ? 'text-error-600' : 'text-success-600'}`}>
                                Rs. {fmt(data.net_profit)}
                            </p>
                        </div>
                    </div>
                </Card>
            )}
        </div>
    );
};

export default IncomeStatementPage;
