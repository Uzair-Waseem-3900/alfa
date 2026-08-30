import { useState, useEffect, useCallback } from 'react';
import { cashFlowApi } from '../services/cashFlowApi';
import { profitsApi } from '../services/profitsApi';
import { usePaginatedList } from './usePaginatedList';

// Hook for dashboard stats
export const useCashFlowStats = () => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchStats = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const result = await cashFlowApi.stats.get();
            setData(result);
        } catch (err) {
            setError(err.message || 'Failed to fetch stats');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchStats();
    }, [fetchStats]);

    return { data, loading, error, refetch: fetchStats };
};

// Hook for breakdown data. Every breakdown endpoint returns the standard
// paginated shape plus a `totals` block (exact sums over the full filtered
// set, computed server-side — not just the current page) which passes
// through as `extra.totals` via usePaginatedList's generic extra-fields capture.
export const useBreakdown = (type, initialFilters = {}) => {
    const cleanFilters = (raw) => {
        const cleaned = {};
        Object.keys(raw).forEach(key => {
            if (raw[key] !== '' && raw[key] !== null && raw[key] !== undefined) {
                cleaned[key] = raw[key];
            }
        });
        return cleaned;
    };

    const fetchBreakdownPage = (params) => {
        const { page, page_size, ...rest } = params;
        const filterParams = { ...cleanFilters(rest), page, page_size };
        switch (type) {
            case 'cashInHand':
                return cashFlowApi.breakdowns.cashInHand(filterParams);
            case 'invoicesCash':
                return cashFlowApi.breakdowns.invoicesCash(filterParams);
            case 'customerOutstanding':
                return cashFlowApi.breakdowns.customerOutstanding(filterParams);
            case 'paidPayables':
                return cashFlowApi.breakdowns.paidPayables(filterParams);
            case 'supplierOutstanding':
                return cashFlowApi.breakdowns.supplierOutstanding(filterParams);
            case 'invoices':
                return cashFlowApi.breakdowns.invoices(filterParams);
            case 'purchases':
                return cashFlowApi.breakdowns.purchases(filterParams);
            case 'expenses':
                return cashFlowApi.breakdowns.expenses(filterParams);
            case 'lostInventory':
                return cashFlowApi.breakdowns.lostInventory(filterParams);
            case 'purchaseReturns':
                return cashFlowApi.breakdowns.purchaseReturns(filterParams);
            case 'customerReturns':
                return cashFlowApi.breakdowns.customerReturns(filterParams);
            case 'profit':
                return cashFlowApi.breakdowns.profit(filterParams);
            case 'monthlyProfit':
                return profitsApi.monthlyProfits.getAll(filterParams);
            default:
                return Promise.resolve([]);
        }
    };

    const { data, meta, extra, loading, error, filters, setFilters, page, setPage, refetch } =
        usePaginatedList(fetchBreakdownPage, initialFilters);

    return { data, meta, extra, page, setPage, loading, error, filters, setFilters, refetch };
};

// Hook for expense management — thin wrapper around usePaginatedList.
export const useExpenses = (initialFilters = {}) => {
    const {
        data, meta, loading: listLoading, error: listError,
        filters, setFilters, page, setPage, refetch,
    } = usePaginatedList((params) => cashFlowApi.expenses.getAll(params), initialFilters);

    const [mutating, setMutating] = useState(false);
    const [mutationError, setMutationError] = useState(null);

    const create = async (payload) => {
        setMutating(true);
        setMutationError(null);
        try {
            const result = await cashFlowApi.expenses.create(payload);
            await refetch();
            return result;
        } catch (err) {
            setMutationError(err.message);
            throw err;
        } finally {
            setMutating(false);
        }
    };

    const update = async (id, payload) => {
        setMutating(true);
        setMutationError(null);
        try {
            const result = await cashFlowApi.expenses.update(id, payload);
            await refetch();
            return result;
        } catch (err) {
            setMutationError(err.message);
            throw err;
        } finally {
            setMutating(false);
        }
    };

    const deleteItem = async (id) => {
        setMutating(true);
        setMutationError(null);
        try {
            await cashFlowApi.expenses.delete(id);
            if (data.length === 1 && page > 1) {
                setPage(page - 1);
            } else {
                await refetch();
            }
        } catch (err) {
            setMutationError(err.message);
            throw err;
        } finally {
            setMutating(false);
        }
    };

    return {
        data,
        meta,
        page,
        setPage,
        // Only the list fetch gates a full-page spinner — a create/update/
        // delete in flight (`mutating`) must not blank the whole page out
        // from under the user, since callers already show their own
        // form/button-level loading state for that.
        loading: listLoading,
        mutating,
        error: listError || mutationError,
        filters,
        setFilters,
        refetch,
        create,
        update,
        delete: deleteItem,
    };
};

// Hook for expense categories — thin wrapper around usePaginatedList.
export const useExpenseCategories = (initialFilters = {}) => {
    const {
        data, meta, loading: listLoading, error: listError,
        filters, setFilters, page, setPage, refetch,
    } = usePaginatedList((params) => cashFlowApi.categories.getAll(params), initialFilters);

    const [mutating, setMutating] = useState(false);
    const [mutationError, setMutationError] = useState(null);

    const create = async (payload) => {
        setMutating(true);
        setMutationError(null);
        try {
            const result = await cashFlowApi.categories.create(payload);
            await refetch();
            return result;
        } catch (err) {
            setMutationError(err.message);
            throw err;
        } finally {
            setMutating(false);
        }
    };

    const update = async (id, payload) => {
        setMutating(true);
        setMutationError(null);
        try {
            const result = await cashFlowApi.categories.update(id, payload);
            await refetch();
            return result;
        } catch (err) {
            setMutationError(err.message);
            throw err;
        } finally {
            setMutating(false);
        }
    };

    const deleteItem = async (id) => {
        setMutating(true);
        setMutationError(null);
        try {
            await cashFlowApi.categories.delete(id);
            if (data.length === 1 && page > 1) {
                setPage(page - 1);
            } else {
                await refetch();
            }
        } catch (err) {
            setMutationError(err.message);
            throw err;
        } finally {
            setMutating(false);
        }
    };

    return {
        data,
        meta,
        page,
        setPage,
        // Only the list fetch gates a full-page spinner — a create/update/
        // delete in flight (`mutating`) must not blank the whole page out
        // from under the user, since callers already show their own
        // form/button-level loading state for that.
        loading: listLoading,
        mutating,
        error: listError || mutationError,
        filters,
        setFilters,
        refetch,
        create,
        update,
        delete: deleteItem,
    };
};

// Full (page_size:500) expense category list — for dropdown population
// (e.g. the expense form/filter select), decoupled from the paginated
// management table above.
export const useAllExpenseCategories = () => {
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(false);

    const fetchData = useCallback(async () => {
        setLoading(true);
        try {
            const result = await cashFlowApi.categories.getAll({ page_size: 500 });
            setData(result?.results || result || []);
        } catch (err) {
            setData([]);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    return { data, loading, refetch: fetchData };
};