import { useState, useEffect, useCallback } from 'react';
import { accountingApi } from '../services/accountingApi';
import { extractErrorMessage } from '../utils/errorMessage';

// Shared shape for the 3 single-object statement endpoints (not paginated
// lists) — refetches whenever `params` changes (period/date range).
const useStatement = (fetchFn, params) => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const paramsKey = JSON.stringify(params);

    const fetchData = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const result = await fetchFn(params);
            setData(result);
        } catch (err) {
            setData(null);
            setError(extractErrorMessage(err, 'Failed to load statement'));
        } finally {
            setLoading(false);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [paramsKey]);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    return { data, loading, error, refetch: fetchData };
};

export const useCashFlowStatement = (params) => useStatement(accountingApi.cashFlowStatement.get, params);
export const useIncomeStatement = (params) => useStatement(accountingApi.incomeStatement.get, params);
export const useBalanceSheet = (params) => useStatement(accountingApi.balanceSheet.get, params);
