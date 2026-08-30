import { useState, useEffect, useCallback } from 'react';
import PropTypes from 'prop-types';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import Card from '../ui/Card';
import Select from '../ui/Select';
import LoadingSpinner from '../ui/LoadingSpinner';
import InlineAlert from '../ui/InlineAlert';
import { cashFlowApi } from '../../services/cashFlowApi';
import { toLocalDateString } from '../../utils/helpers';

const MONTHS_OPTIONS = [
    { value: '6', label: 'Last 6 months' },
    { value: '12', label: 'Last 12 months' },
    { value: '24', label: 'Last 24 months' },
];

const formatCurrency = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : value;
    if (isNaN(num)) return 'Rs. 0';
    if (Math.abs(num) >= 1000000) return `Rs. ${(num / 1000000).toFixed(1)}M`;
    if (Math.abs(num) >= 1000) return `Rs. ${(num / 1000).toFixed(1)}K`;
    return `Rs. ${num.toFixed(0)}`;
};

const formatMonthLabel = (month) => {
    const [year, m] = month.split('-');
    const date = new Date(Number(year), Number(m) - 1, 1);
    return date.toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
};

const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload || !payload.length) return null;
    const data = payload[0].payload;
    const netProfit = Number(data.net_gross_profit ?? data.gross_profit ?? 0);
    return (
        <div className="bg-white rounded-xl shadow-card-hover border border-neutral-200 p-3">
            <p className="text-sm font-semibold text-neutral-900">{formatMonthLabel(label)}</p>
            <p className="text-xs text-neutral-500 mt-1">
                Net Revenue: <span className="font-medium text-neutral-700">{formatCurrency(data.net_revenue)}</span>
            </p>
            <p className="text-xs text-neutral-500">
                Net COGS: <span className="font-medium text-neutral-700">{formatCurrency(data.net_cogs)}</span>
            </p>
            <p className={`text-xs font-semibold mt-1 ${netProfit >= 0 ? 'text-success-600' : 'text-error-600'}`}>
                Net Gross Profit: {formatCurrency(netProfit)}
            </p>
            <p className="text-xs text-neutral-400 mt-2 pt-2 border-t border-neutral-100">
                Before returns — Revenue: {formatCurrency(data.revenue)}, COGS: {formatCurrency(data.cogs)}, Gross Profit: {formatCurrency(data.gross_profit)}
            </p>
        </div>
    );
};

CustomTooltip.propTypes = {
    active: PropTypes.bool,
    payload: PropTypes.array,
    label: PropTypes.string,
};

const GrossProfitTrendChart = () => {
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [months, setMonths] = useState(6);

    const fetchTrend = useCallback(async () => {
        setLoading(true);
        setError('');
        try {
            const from = new Date();
            from.setMonth(from.getMonth() - (months - 1));
            from.setDate(1);
            const date_from = toLocalDateString(from);
            const result = await cashFlowApi.grossProfitTrend.get({ date_from });
            setData(result || []);
        } catch (err) {
            setError(err.message || 'Failed to load gross profit trend');
            setData([]);
        } finally {
            setLoading(false);
        }
    }, [months]);

    useEffect(() => {
        fetchTrend();
    }, [fetchTrend]);

    return (
        <Card className="p-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
                <div>
                    <h2 className="text-lg font-semibold text-neutral-900">Net Gross Profit Trend</h2>
                    <p className="text-sm text-neutral-500 mt-1">
                        After returns accepted each month — hover a point for the gross (before-returns) figures
                    </p>
                </div>
                <Select
                    value={String(months)}
                    onChange={(e) => setMonths(Number(e.target.value))}
                    options={MONTHS_OPTIONS}
                    className="w-44"
                />
            </div>

            {error && (
                <InlineAlert variant="error" message={error} onRetry={fetchTrend} className="mb-4" />
            )}

            {loading ? (
                <div className="flex items-center justify-center h-72">
                    <LoadingSpinner size="lg" />
                </div>
            ) : data.length === 0 ? (
                <div className="flex items-center justify-center h-72">
                    <p className="text-sm text-neutral-500">No data for this range</p>
                </div>
            ) : (
                <div className="h-72">
                    <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                            <defs>
                                <linearGradient id="grossProfitGradient" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#059669" stopOpacity={0.3} />
                                    <stop offset="95%" stopColor="#059669" stopOpacity={0} />
                                </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                            <XAxis
                                dataKey="month"
                                tickFormatter={formatMonthLabel}
                                tick={{ fill: '#64748b', fontSize: 12 }}
                                axisLine={{ stroke: '#e2e8f0' }}
                                tickLine={false}
                            />
                            <YAxis
                                tickFormatter={formatCurrency}
                                tick={{ fill: '#64748b', fontSize: 12 }}
                                axisLine={false}
                                tickLine={false}
                                width={70}
                            />
                            <Tooltip content={<CustomTooltip />} />
                            <Area
                                type="monotone"
                                dataKey="net_gross_profit"
                                stroke="#059669"
                                strokeWidth={2}
                                fill="url(#grossProfitGradient)"
                            />
                        </AreaChart>
                    </ResponsiveContainer>
                </div>
            )}
        </Card>
    );
};

export default GrossProfitTrendChart;
