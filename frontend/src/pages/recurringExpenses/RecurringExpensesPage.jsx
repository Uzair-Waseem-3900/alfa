import { Link } from 'react-router-dom';
import {
    ShieldAlert, Repeat, Tags, ClipboardList, CalendarRange,
    Wallet, TrendingUp, TrendingDown, Layers, ArrowRight,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useRecurringExpenseFlowStats } from '../../hooks/useRecurringExpenses';
import Card from '../../components/ui/Card';
import Button from '../../components/ui/Button';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import InlineAlert from '../../components/ui/InlineAlert';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const tones = {
    blue: { icon: 'bg-info-50 text-info-600', text: 'text-info-600' },
    green: { icon: 'bg-success-50 text-success-600', text: 'text-success-600' },
    amber: { icon: 'bg-warning-50 text-warning-700', text: 'text-warning-700' },
    purple: { icon: 'bg-purple-50 text-purple-600', text: 'text-purple-600' },
    neutral: { icon: 'bg-neutral-100 text-neutral-600', text: 'text-neutral-900' },
};

const StatBox = ({ label, value, tone = 'neutral', subtitle, isCount = false, icon: Icon }) => {
    const t = tones[tone] || tones.neutral;
    return (
        <Card className="p-5">
            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                    <p className="text-xs font-medium text-neutral-500 uppercase tracking-wide mb-1.5">{label}</p>
                    <p className={`text-2xl font-bold ${t.text} truncate`}>
                        {isCount ? (value ?? 0) : `Rs. ${fmt(value)}`}
                    </p>
                    {subtitle && <p className="text-xs text-neutral-400 mt-1.5">{subtitle}</p>}
                </div>
                {Icon && (
                    <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${t.icon}`}>
                        <Icon className="w-5 h-5" />
                    </div>
                )}
            </div>
        </Card>
    );
};

const navItems = [
    {
        to: '/recurring-expenses/categories', title: 'Categories', icon: Tags, primary: false,
        description: "Set up categories like Rent, Salaries, Utilities.",
    },
    {
        to: '/recurring-expenses/templates', title: 'Templates', icon: Layers, primary: false,
        description: 'Manage each recurring obligation and its monthly amount.',
    },
    {
        to: '/recurring-expenses/post-dues', title: 'Post Dues', icon: CalendarRange, primary: true,
        description: "Assign what's due for a month — one at a time, all at once, or by category.",
    },
    {
        to: '/recurring-expenses/assignments', title: 'Assignments', icon: ClipboardList, primary: false,
        description: 'Every month due ever assigned — record payments here.',
    },
    {
        to: '/recurring-expenses/monthly-stats', title: 'Monthly Breakdown', icon: TrendingUp, primary: false,
        description: 'Assigned/paid/pending totals per month, at a glance.',
    },
];

const RecurringExpensesPage = () => {
    const { user } = useAuth();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const { data: stats, loading: statsLoading } = useRecurringExpenseFlowStats();

    if (!isAdmin) {
        return (
            <div className="flex flex-col items-center justify-center text-center py-20">
                <div className="w-14 h-14 rounded-full bg-error-50 flex items-center justify-center mb-4">
                    <ShieldAlert className="w-7 h-7 text-error-500" />
                </div>
                <h2 className="text-2xl font-semibold text-neutral-900">Access Denied</h2>
                <p className="text-neutral-500 mt-2 max-w-sm">Only admins or superusers can view recurring expenses.</p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex items-start gap-4">
                <div className="hidden sm:flex w-12 h-12 rounded-2xl bg-gradient-to-br from-primary-700 to-accent-600 items-center justify-center flex-shrink-0 shadow-lg shadow-primary-900/20">
                    <Repeat className="w-6 h-6 text-white" />
                </div>
                <div>
                    <h1 className="text-3xl font-bold text-neutral-900">Recurring Expenses</h1>
                    <p className="text-neutral-500 mt-1">
                        Salaries, rent, and anything else that must be paid every month — assign what's due,
                        then record payments as they're actually made.
                    </p>
                </div>
            </div>

            {statsLoading ? (
                <div className="flex items-center justify-center py-8">
                    <LoadingSpinner size="lg" />
                </div>
            ) : (
                <>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                        <StatBox label="Total Assigned" value={stats?.total_assigned_amount} tone="blue" subtitle="All-time, gross" icon={Wallet} />
                        <StatBox label="Total Paid" value={stats?.total_paid_amount} tone="green" subtitle="All-time" icon={TrendingUp} />
                        <StatBox label="Total Pending" value={stats?.total_pending_amount} tone="amber" subtitle="Assigned minus paid" icon={TrendingDown} />
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                        <StatBox label="Active Templates" value={stats?.total_active_templates} tone="neutral" subtitle="Currently active" isCount icon={Layers} />
                        <StatBox label="Active Monthly Obligation" value={stats?.total_active_monthly_obligation} tone="purple" subtitle="If everything were assigned this month" icon={CalendarRange} />
                        <StatBox label="Total Assignments" value={stats?.total_assignments_count} tone="neutral" subtitle="All-time count" isCount icon={ClipboardList} />
                    </div>
                </>
            )}

            <InlineAlert
                variant="info"
                message="Assigning a month's due never moves cash by itself — it only becomes a payable balance. Cash in hand only changes when a payment is actually recorded against it."
            />

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {navItems.map(({ to, title, icon: Icon, description, primary }) => (
                    <Card key={to} className="p-6 flex flex-col">
                        <div className={`w-11 h-11 rounded-xl flex items-center justify-center mb-4 ${primary ? 'bg-gradient-to-br from-primary-700 to-accent-600' : 'bg-primary-50'}`}>
                            <Icon className={`w-5 h-5 ${primary ? 'text-white' : 'text-primary-700'}`} />
                        </div>
                        <h3 className="font-semibold text-neutral-900 mb-1.5">{title}</h3>
                        <p className="text-sm text-neutral-500 mb-4 flex-1">{description}</p>
                        <Link to={to}>
                            <Button variant={primary ? 'primary' : 'secondary'} className="w-full sm:w-auto">
                                {title === 'Post Dues' ? 'Post Dues' : `View ${title}`}
                                <ArrowRight className="w-4 h-4" />
                            </Button>
                        </Link>
                    </Card>
                ))}
            </div>
        </div>
    );
};

export default RecurringExpensesPage;
