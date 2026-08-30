import { useMemo } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useBusinessWorth } from '../../hooks/useProfits';
import Card from '../../components/ui/Card';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import InlineAlert from '../../components/ui/InlineAlert';
import { Wallet, ShieldAlert } from 'lucide-react';
import {
    PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer,
    BarChart, Bar, XAxis, YAxis, CartesianGrid, ReferenceLine,
} from 'recharts';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const formatCompact = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    if (isNaN(num)) return 'Rs. 0';
    const abs = Math.abs(num);
    const sign = num < 0 ? '-' : '';
    if (abs >= 1000000) return `${sign}Rs. ${(abs / 1000000).toFixed(2)}M`;
    if (abs >= 1000) return `${sign}Rs. ${(abs / 1000).toFixed(1)}K`;
    return `${sign}Rs. ${abs.toFixed(0)}`;
};

const OWNERSHIP_COLORS = ['#6366f1', '#059669', '#d97706', '#dc2626', '#0891b2', '#7c3aed', '#db2777', '#65a30d'];
const ASSET_COLOR = '#059669';
const LIABILITY_COLOR = '#dc2626';

const StatBox = ({ label, value, tone = 'neutral', subtitle, sign }) => {
    const tones = {
        neutral: 'text-neutral-900',
        green: 'text-success-600',
        red: 'text-error-600',
        blue: 'text-info-600',
        purple: 'text-purple-600',
    };
    return (
        <Card className="p-4">
            <p className="text-xs text-neutral-500 mb-1">{label}</p>
            <p className={`text-xl font-bold ${tones[tone]}`}>
                {sign ? `${sign} Rs. ${fmt(value)}` : `Rs. ${fmt(value)}`}
            </p>
            {subtitle && <p className="text-xs text-neutral-400 mt-1">{subtitle}</p>}
        </Card>
    );
};

const OwnershipTooltip = ({ active, payload }) => {
    if (!active || !payload || !payload.length) return null;
    const row = payload[0].payload;
    return (
        <div className="bg-white rounded-xl shadow-card-hover border border-neutral-200 p-3">
            <p className="text-sm font-semibold text-neutral-900">{row.name}</p>
            <p className="text-xs text-neutral-500 mt-1">Worth: <span className="font-medium text-neutral-700">Rs. {fmt(row.worth)}</span></p>
            <p className="text-xs text-neutral-500">Share: <span className="font-medium text-neutral-700">{fmt(row.value)}%</span></p>
        </div>
    );
};

const BreakdownTooltip = ({ active, payload }) => {
    if (!active || !payload || !payload.length) return null;
    const row = payload[0].payload;
    return (
        <div className="bg-white rounded-xl shadow-card-hover border border-neutral-200 p-3">
            <p className="text-sm font-semibold text-neutral-900">{row.name}</p>
            <p className={`text-xs mt-1 font-medium ${row.type === 'asset' ? 'text-success-600' : 'text-error-600'}`}>
                {row.type === 'asset' ? '+ ' : '− '}Rs. {fmt(Math.abs(row.value))}
            </p>
        </div>
    );
};

const BusinessWorthPage = () => {
    const { user } = useAuth();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';
    const { data, loading, error, refetch } = useBusinessWorth();

    const ownershipData = useMemo(() => {
        if (!data) return [];
        const rows = (data.investors || []).map((inv) => ({
            name: inv.name,
            value: Math.max(0, parseFloat(inv.share_percent)),
            worth: inv.current_worth,
        }));
        rows.push({
            name: 'Owner',
            value: Math.max(0, parseFloat(data.owner_share_percent)),
            worth: data.owner_worth,
        });
        return rows.filter((r) => r.value > 0);
    }, [data]);

    const worthBreakdownData = useMemo(() => {
        if (!data) return [];
        return [
            { name: 'Cash in Hand', value: parseFloat(data.cash_in_hand), type: 'asset' },
            { name: 'Inventory Value', value: parseFloat(data.inventory_value), type: 'asset' },
            { name: 'Assets Worth', value: parseFloat(data.assets_current_worth), type: 'asset' },
            { name: 'Customer Outstanding', value: parseFloat(data.customer_outstanding), type: 'asset' },
            { name: 'Supplier Payable', value: -parseFloat(data.supplier_payable_outstanding), type: 'liability' },
            // Sales Tax Outstanding and WHT Outstanding temporarily excluded — see
            // backend/profits/how_to_restore_tax_outstanding_in_business_worth.md to reverse.
            // { name: 'Sales Tax Outstanding', value: -parseFloat(data.sales_tax_outstanding), type: 'liability' },
            // { name: 'WHT Outstanding', value: -parseFloat(data.wht_outstanding), type: 'liability' },
            { name: 'Recurring Exp. Pending', value: -parseFloat(data.recurring_expense_pending), type: 'liability' },
        ];
    }, [data]);

    if (!isAdmin) {
        return (
            <div className="text-center py-12">
                <ShieldAlert className="w-10 h-10 text-neutral-300 mx-auto mb-3" />
                <h2 className="text-2xl font-semibold text-neutral-900">Access Denied</h2>
                <p className="text-neutral-500 mt-2">Only admins or superusers can view business worth.</p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <InlineAlert
                variant="warning"
                title="This is an internal estimate, not a certified valuation."
                message="Computed live from cash, inventory, assets, receivables, payables, and tax figures already tracked elsewhere in this system. Review with an accountant before using it to actually distribute profit. The developer is not responsible at all for decisions made from this page."
            />

            <div className="flex items-center gap-3">
                <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-primary-600 to-accent-600 flex items-center justify-center shadow-lg shadow-primary-900/20 flex-shrink-0">
                    <Wallet className="w-5 h-5 text-white" />
                </div>
                <div>
                    <h1 className="text-3xl font-bold text-neutral-900">Business Worth</h1>
                    <p className="text-neutral-500 mt-0.5">
                        Everything the business owns, minus everything it owes — and how that worth is split
                        between the owner and every investor.
                    </p>
                </div>
            </div>

            {loading ? (
                <div className="flex items-center justify-center py-16">
                    <LoadingSpinner size="lg" />
                </div>
            ) : error ? (
                <InlineAlert variant="error" message={error} onRetry={refetch} />
            ) : (
                <>
                    {/* Hero total */}
                    <Card className="p-4 bg-gradient-to-br from-primary-600 to-primary-700 text-white">
                        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                            <div className="flex items-baseline gap-3">
                                <p className="text-sm text-primary-100 uppercase tracking-wide font-medium">Total Business Worth</p>
                                <p className="text-xl font-bold">Rs. {fmt(data.total_business_worth)}</p>
                            </div>
                            <p className="text-sm text-primary-100">
                                Assets − Liabilities · computed live, never stored
                            </p>
                        </div>
                    </Card>

                    {/* Charts */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <Card className="p-6">
                            <h3 className="font-semibold text-neutral-900 mb-1">Ownership Split</h3>
                            <p className="text-sm text-neutral-500 mb-4">
                                Each investor's share by their contracted growth worth; the owner keeps the residual.
                            </p>
                            {ownershipData.length === 0 ? (
                                <div className="flex items-center justify-center h-64 text-sm text-neutral-400">
                                    No positive shares to display
                                </div>
                            ) : (
                                <div className="h-72">
                                    <ResponsiveContainer width="100%" height="100%">
                                        <PieChart>
                                            <Pie
                                                data={ownershipData}
                                                dataKey="value"
                                                nameKey="name"
                                                cx="50%"
                                                cy="50%"
                                                innerRadius={60}
                                                outerRadius={100}
                                                paddingAngle={2}
                                                label={({ name, value }) => `${name} ${value.toFixed(1)}%`}
                                            >
                                                {ownershipData.map((_entry, index) => (
                                                    <Cell key={index} fill={OWNERSHIP_COLORS[index % OWNERSHIP_COLORS.length]} />
                                                ))}
                                            </Pie>
                                            <Tooltip content={<OwnershipTooltip />} />
                                            <Legend />
                                        </PieChart>
                                    </ResponsiveContainer>
                                </div>
                            )}
                            {parseFloat(data.owner_share_percent) < 0 && (
                                <div className="mt-3 p-3 bg-error-50 border border-error-200 rounded-lg">
                                    <p className="text-xs text-error-600">
                                        Owner's share is actually negative ({fmt(data.owner_share_percent)}%) — investors'
                                        combined contracted worth currently exceeds total business worth. Not shown on
                                        the chart since shares can't render below 0%.
                                    </p>
                                </div>
                            )}
                        </Card>

                        <Card className="p-6">
                            <h3 className="font-semibold text-neutral-900 mb-1">Worth Breakdown</h3>
                            <p className="text-sm text-neutral-500 mb-4">
                                <span className="text-success-600 font-medium">Green</span> adds to worth ·{' '}
                                <span className="text-error-600 font-medium">red</span> subtracts from it.
                            </p>
                            <div className="h-72">
                                <ResponsiveContainer width="100%" height="100%">
                                    <BarChart data={worthBreakdownData} layout="vertical" margin={{ top: 5, left: 10, right: 20, bottom: 5 }}>
                                        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
                                        <XAxis type="number" tickFormatter={formatCompact} tick={{ fill: '#64748b', fontSize: 11 }} />
                                        <YAxis type="category" dataKey="name" width={140} tick={{ fill: '#64748b', fontSize: 11 }} />
                                        <ReferenceLine x={0} stroke="#94a3b8" />
                                        <Tooltip content={<BreakdownTooltip />} cursor={{ fill: '#f1f5f9' }} />
                                        <Bar dataKey="value" radius={[4, 4, 4, 4]} barSize={20} isAnimationActive={false}>
                                            {worthBreakdownData.map((entry, index) => (
                                                <Cell key={index} fill={entry.type === 'asset' ? ASSET_COLOR : LIABILITY_COLOR} />
                                            ))}
                                        </Bar>
                                    </BarChart>
                                </ResponsiveContainer>
                            </div>
                        </Card>
                    </div>

                    {/* Component detail */}
                    <div>
                        <h2 className="text-lg font-semibold text-neutral-900 mb-3">Assets (added)</h2>
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                            <StatBox label="Cash in Hand" value={data.cash_in_hand} tone="green" sign="+" subtitle="Physical/bank cash held now" />
                            <StatBox label="Inventory Value" value={data.inventory_value} tone="green" sign="+" subtitle="Unsold stock, at FIFO cost" />
                            <StatBox label="Assets' Current Worth" value={data.assets_current_worth} tone="green" sign="+" subtitle="Equipment/fixtures, depreciated" />
                            <StatBox label="Customer Outstanding" value={data.customer_outstanding} tone="green" sign="+" subtitle="Owed by customers (receivable)" />
                        </div>
                    </div>

                    <div>
                        <h2 className="text-lg font-semibold text-neutral-900 mb-3">Liabilities (subtracted)</h2>
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                            <StatBox label="Supplier Payable" value={data.supplier_payable_outstanding} tone="red" sign="−" subtitle="Owed to suppliers (payable)" />
                            {/* Sales Tax Outstanding and WHT Outstanding temporarily excluded — see
                                backend/profits/how_to_restore_tax_outstanding_in_business_worth.md to reverse. */}
                            {/* <StatBox label="Sales Tax Outstanding" value={data.sales_tax_outstanding} tone="red" sign="−" subtitle="GST still owed to FBR" /> */}
                            {/* <StatBox label="WHT Outstanding" value={data.wht_outstanding} tone="red" sign="−" subtitle="Withheld from suppliers, not deposited" /> */}
                            <StatBox label="Recurring Exp. Pending" value={data.recurring_expense_pending} tone="red" sign="−" subtitle="Assigned dues, not yet paid" />
                        </div>
                    </div>

                    {/* Investor table */}
                    <Card className="p-6">
                        <h3 className="font-semibold text-neutral-900 mb-4">Ownership Detail</h3>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="text-left text-neutral-500 border-b border-neutral-200">
                                        <th className="pb-2 font-medium">Name</th>
                                        <th className="pb-2 font-medium">Current Worth (PKR)</th>
                                        <th className="pb-2 font-medium">Share %</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {(data.investors || []).map((inv) => (
                                        <tr key={inv.id} className="border-b border-neutral-100">
                                            <td className="py-2 text-neutral-900">{inv.name}</td>
                                            <td className="py-2 text-neutral-700">Rs. {fmt(inv.current_worth)}</td>
                                            <td className="py-2 text-neutral-700">{fmt(inv.share_percent)}%</td>
                                        </tr>
                                    ))}
                                    <tr>
                                        <td className="py-2 font-semibold text-neutral-900">Owner</td>
                                        <td className="py-2 font-semibold text-neutral-900">Rs. {fmt(data.owner_worth)}</td>
                                        <td className={`py-2 font-semibold ${parseFloat(data.owner_share_percent) < 0 ? 'text-error-600' : 'text-neutral-900'}`}>
                                            {fmt(data.owner_share_percent)}%
                                        </td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                        <p className="text-xs text-neutral-400 mt-4">
                            Total Investor Net Worth: Rs. {fmt(data.total_investor_net_worth)} — each investor's stake
                            compounded by their own contracted growth rate, not a share of actual business
                            performance. The owner absorbs everything above (or below) that.
                        </p>
                    </Card>
                </>
            )}
        </div>
    );
};

export default BusinessWorthPage;
