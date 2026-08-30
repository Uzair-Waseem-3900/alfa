import { Link } from 'react-router-dom';
import {
    ShieldAlert, AlertTriangle, Landmark, Receipt, ArrowRight,
    ArrowDownCircle, ArrowUpCircle, Wallet, CircleDollarSign,
    HandCoins, Banknote,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useTaxesStats } from '../../hooks/useTaxes';
import Card from '../../components/ui/Card';
import Button from '../../components/ui/Button';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import InlineAlert from '../../components/ui/InlineAlert';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const TONES = {
    neutral: { text: 'text-neutral-900', bg: 'bg-neutral-100', icon: 'text-neutral-500' },
    amber: { text: 'text-warning-700', bg: 'bg-warning-50', icon: 'text-warning-600' },
    red: { text: 'text-error-600', bg: 'bg-error-50', icon: 'text-error-500' },
    blue: { text: 'text-info-600', bg: 'bg-info-50', icon: 'text-info-500' },
    purple: { text: 'text-purple-600', bg: 'bg-purple-50', icon: 'text-purple-500' },
    green: { text: 'text-success-600', bg: 'bg-success-50', icon: 'text-success-500' },
    orange: { text: 'text-orange-600', bg: 'bg-orange-50', icon: 'text-orange-500' },
};

const StatBox = ({ label, value, tone = 'neutral', subtitle, icon: Icon }) => {
    const t = TONES[tone] || TONES.neutral;
    return (
        <Card className="p-5">
            <div className="flex items-start justify-between">
                <p className="text-xs font-medium text-neutral-500 uppercase tracking-wide">{label}</p>
                {Icon && (
                    <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${t.bg}`}>
                        <Icon className={`w-4.5 h-4.5 ${t.icon}`} />
                    </div>
                )}
            </div>
            <p className={`text-2xl font-bold mt-2 ${t.text}`}>Rs. {fmt(value)}</p>
            {subtitle && <p className="text-xs text-neutral-400 mt-1">{subtitle}</p>}
        </Card>
    );
};

const TaxesPage = () => {
    const { user } = useAuth();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const { data: stats, loading: statsLoading, error: statsError, refetch: refetchStats } = useTaxesStats();

    if (!isAdmin) {
        return (
            <div className="flex flex-col items-center justify-center text-center py-20">
                <div className="w-14 h-14 rounded-full bg-error-50 flex items-center justify-center mb-4">
                    <ShieldAlert className="w-7 h-7 text-error-500" />
                </div>
                <h2 className="text-2xl font-semibold text-neutral-900">Access Denied</h2>
                <p className="text-neutral-500 mt-2 max-w-sm">Only admins or superusers can view taxes.</p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Compliance disclaimer — always visible at the top, this is not
                legal/tax advice and figures must be independently verified. */}
            <div className="p-4 bg-amber-50 border-l-4 border-amber-500 rounded-r-xl flex gap-3">
                <AlertTriangle className="w-5 h-5 flex-shrink-0 mt-0.5 text-amber-600" />
                <div>
                    <p className="text-sm font-semibold text-amber-800">
                        These figures are an internal estimate, not a certified filing.
                    </p>
                    <p className="text-sm text-amber-700 mt-0.5">
                        This page is a development tool and its calculations are not guaranteed to be
                        perfect. Always double-check these numbers and consult a qualified accountant
                        or tax professional before filing or paying anything to FBR. The developer is
                        not responsible for tax decisions made from this page.
                    </p>
                </div>
            </div>

            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <h1 className="text-3xl font-bold text-neutral-900 flex items-center gap-2.5">
                        <Landmark className="w-7 h-7 text-primary-600" />
                        Taxes
                    </h1>
                    <p className="text-neutral-500 mt-1">
                        Sales tax (GST) position and withholding tax (WHT) position — see{' '}
                        <Link to="/reports/sales-tax" className="text-primary-600 hover:text-primary-700 font-medium">
                            Sales Tax Report
                        </Link>{' '}
                        for a transaction-level breakdown.
                    </p>
                </div>
                <div className="flex gap-3">
                    <Link to="/taxes/payments">
                        <Button variant="secondary" icon={Receipt}>
                            GST Payments
                        </Button>
                    </Link>
                    <Link to="/taxes/wht-payments">
                        <Button icon={Receipt}>
                            WHT Payments
                        </Button>
                    </Link>
                </div>
            </div>

            {statsError ? (
                <InlineAlert variant="error" message={statsError} onRetry={refetchStats} />
            ) : statsLoading ? (
                <div className="flex items-center justify-center py-12">
                    <LoadingSpinner size="lg" />
                </div>
            ) : (
                <>
                    <div>
                        <h2 className="text-lg font-semibold text-neutral-900 mb-1 flex items-center gap-2">
                            <CircleDollarSign className="w-5 h-5 text-primary-600" />
                            Sales Tax (GST)
                        </h2>
                        <p className="text-sm text-neutral-500 mb-3">
                            Netted — you only owe FBR the difference between what you charged customers and
                            what you already paid your suppliers.
                        </p>
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                            <StatBox label="Input Tax Paid" value={stats?.total_input_tax_paid} tone="blue" subtitle="GST paid to suppliers" icon={ArrowDownCircle} />
                            <StatBox label="Output Tax Collected" value={stats?.total_output_tax_collected} tone="purple" subtitle="GST charged to customers" icon={ArrowUpCircle} />
                            <StatBox label="Net Sales Tax Payable" value={stats?.net_sales_tax_payable} tone="amber" subtitle="Output minus Input tax" icon={Banknote} />
                            <StatBox label="Sales Tax Outstanding" value={stats?.sales_tax_outstanding} tone="red" subtitle="Still to pay FBR" icon={AlertTriangle} />
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4">
                            <StatBox label="Sales Tax Paid" value={stats?.total_sales_tax_paid} tone="green" subtitle="Actually paid to FBR so far" icon={Wallet} />
                        </div>
                    </div>

                    <div>
                        <h2 className="text-lg font-semibold text-neutral-900 mb-1 mt-2 flex items-center gap-2">
                            <HandCoins className="w-5 h-5 text-primary-600" />
                            Withholding Tax (WHT)
                        </h2>
                        <p className="text-sm text-neutral-500 mb-3">
                            Never netted against Sales Tax, or against each other — each side belongs to a
                            different taxpayer's obligation. Only the supplier side (money you're holding)
                            is something you actually pay.
                        </p>
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                            <StatBox label="WHT Withheld from Suppliers" value={stats?.total_wht_withheld_from_suppliers} tone="orange" subtitle="Input side — real FBR liability" icon={ArrowDownCircle} />
                            <StatBox label="WHT Withheld by Customers" value={stats?.total_wht_withheld_by_customers} tone="blue" subtitle="Output side — credit only, not payable" icon={ArrowUpCircle} />
                            <StatBox label="WHT Paid" value={stats?.total_wht_paid} tone="green" subtitle="Actually deposited to FBR so far" icon={Wallet} />
                            <StatBox label="WHT Outstanding" value={stats?.wht_outstanding} tone="red" subtitle="Withheld from suppliers minus paid" icon={AlertTriangle} />
                        </div>
                    </div>
                </>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                <Card className="p-6">
                    <h3 className="font-semibold text-neutral-900 mb-2">GST Payments</h3>
                    <p className="text-sm text-neutral-500 mb-4">
                        Record and manage every GST payment actually made to FBR — each one reduces cash in hand.
                    </p>
                    <Link to="/taxes/payments">
                        <Button variant="secondary" icon={ArrowRight}>View GST Payments</Button>
                    </Link>
                </Card>
                <Card className="p-6">
                    <h3 className="font-semibold text-neutral-900 mb-2">WHT Payments</h3>
                    <p className="text-sm text-neutral-500 mb-4">
                        Record and manage every WHT deposit actually made to FBR, against tax withheld from
                        suppliers — each one reduces cash in hand.
                    </p>
                    <Link to="/taxes/wht-payments">
                        <Button variant="secondary" icon={ArrowRight}>View WHT Payments</Button>
                    </Link>
                </Card>
            </div>
        </div>
    );
};

export default TaxesPage;
