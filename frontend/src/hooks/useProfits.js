import { useState, useEffect, useCallback } from 'react';
import { profitsApi } from '../services/profitsApi';
import { usePaginatedList } from './usePaginatedList';

// Hook for the Business Worth breakdown + ownership split
export const useBusinessWorth = () => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchData = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const result = await profitsApi.businessWorth.get();
            setData(result);
        } catch (err) {
            setError(err.message || 'Failed to fetch business worth');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    return { data, loading, error, refetch: fetchData };
};

// Hook for lifetime profit totals (ProfitFlow)
export const useProfitFlowStats = () => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchData = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const result = await profitsApi.stats.get();
            setData(result);
        } catch (err) {
            setError(err.message || 'Failed to fetch profit stats');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    return { data, loading, error, refetch: fetchData };
};

// Hook for the Net Profit Trend dashboard chart
export const useNetProfitTrend = (months = 12) => {
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchData = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const result = await profitsApi.netProfitTrend.get(months);
            setData(result || []);
        } catch (err) {
            setError(err.message || 'Failed to fetch net profit trend');
            setData([]);
        } finally {
            setLoading(false);
        }
    }, [months]);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    return { data, loading, error, refetch: fetchData };
};

// Hook for the finalized Monthly Profits list (paginated)
export const useMonthlyProfits = () => {
    return usePaginatedList((params) => profitsApi.monthlyProfits.getAll(params), {});
};

// Hook for the live, provisional current-month figures
export const useCurrentMonthProfit = () => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchData = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const result = await profitsApi.monthlyProfits.getCurrent();
            setData(result);
        } catch (err) {
            setError(err.message || 'Failed to fetch current month profit');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    return { data, loading, error, refetch: fetchData };
};

// Hook for one finalized month's full breakdown + investor shares + payout history
export const useMonthlyProfitDetail = (period) => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchData = useCallback(async () => {
        if (!period) return;
        setLoading(true);
        setError(null);
        try {
            const result = await profitsApi.monthlyProfits.getByPeriod(period);
            setData(result);
        } catch (err) {
            setError(err.message || 'Failed to fetch monthly profit');
        } finally {
            setLoading(false);
        }
    }, [period]);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    return { data, loading, error, refetch: fetchData };
};

// Hook for the flat, all-investors, all-months payout list (newest first)
export const useInvestorProfitPayouts = () => {
    return usePaginatedList((params) => profitsApi.payouts.getAll(params), {});
};

// Hook for one investor's profit share across every finalized month
export const useInvestorMonthlyShares = (investorId) => {
    return usePaginatedList(
        (params) => profitsApi.investors.getShares(investorId, params),
        {},
    );
};
