import { useState, useEffect, useCallback } from 'react';
import { cashManagementApi } from '../services/cashManagementApi';
import { usePaginatedList } from './usePaginatedList';

// Hook for the cash-management stats (lost/found cash, investor capital)
export const useCashManagementStats = () => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchStats = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const result = await cashManagementApi.stats.get();
            setData(result);
        } catch (err) {
            setError(err.message || 'Failed to fetch cash management stats');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchStats();
    }, [fetchStats]);

    return { data, loading, error, refetch: fetchStats };
};

// Hook for cash adjustment management (create + delete only — no update endpoint).
export const useCashAdjustments = (initialFilters = {}) => {
    const {
        data, meta, loading: listLoading, error: listError,
        filters, setFilters, page, setPage, refetch,
    } = usePaginatedList((params) => cashManagementApi.adjustments.getAll(params), initialFilters);

    const [mutating, setMutating] = useState(false);
    const [mutationError, setMutationError] = useState(null);

    const create = async (payload) => {
        setMutating(true);
        try {
            const result = await cashManagementApi.adjustments.create(payload);
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
        try {
            await cashManagementApi.adjustments.delete(id);
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
        data, meta, page, setPage,
        loading: listLoading || mutating,
        error: listError || mutationError,
        filters, setFilters, refetch,
        create, delete: deleteItem,
    };
};

// Hook for investor management (create + update + delete).
export const useInvestors = (initialFilters = {}) => {
    const {
        data, meta, loading: listLoading, error: listError,
        filters, setFilters, page, setPage, refetch,
    } = usePaginatedList((params) => cashManagementApi.investors.getAll(params), initialFilters);

    const [mutating, setMutating] = useState(false);
    const [mutationError, setMutationError] = useState(null);

    const create = async (payload) => {
        setMutating(true);
        try {
            const result = await cashManagementApi.investors.create(payload);
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
        try {
            const result = await cashManagementApi.investors.update(id, payload);
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
        try {
            await cashManagementApi.investors.delete(id);
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
        data, meta, page, setPage,
        loading: listLoading || mutating,
        error: listError || mutationError,
        filters, setFilters, refetch,
        create, update, delete: deleteItem,
    };
};

// Hook for a single investor's growth history, scoped via initialFilters={ investor_id }.
export const useInvestorValuationEntries = (initialFilters = {}) => {
    const {
        data, meta, loading, error, filters, setFilters, page, setPage, refetch,
    } = usePaginatedList((params) => cashManagementApi.investorValuationEntries.getAll(params), initialFilters);

    return { data, meta, loading, error, filters, setFilters, page, setPage, refetch };
};

// Hook for investor transaction management (create + delete only), optionally
// scoped to a single investor via initialFilters={ investor_id }.
export const useInvestorTransactions = (initialFilters = {}) => {
    const {
        data, meta, loading: listLoading, error: listError,
        filters, setFilters, page, setPage, refetch,
    } = usePaginatedList((params) => cashManagementApi.investorTransactions.getAll(params), initialFilters);

    const [mutating, setMutating] = useState(false);
    const [mutationError, setMutationError] = useState(null);

    const create = async (payload) => {
        setMutating(true);
        try {
            const result = await cashManagementApi.investorTransactions.create(payload);
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
        try {
            await cashManagementApi.investorTransactions.delete(id);
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
        data, meta, page, setPage,
        loading: listLoading || mutating,
        error: listError || mutationError,
        filters, setFilters, refetch,
        create, delete: deleteItem,
    };
};

// Hook for owner transaction management (create + delete only — no update endpoint).
export const useOwnerTransactions = (initialFilters = {}) => {
    const {
        data, meta, loading: listLoading, error: listError,
        filters, setFilters, page, setPage, refetch,
    } = usePaginatedList((params) => cashManagementApi.ownerTransactions.getAll(params), initialFilters);

    const [mutating, setMutating] = useState(false);
    const [mutationError, setMutationError] = useState(null);

    const create = async (payload) => {
        setMutating(true);
        try {
            const result = await cashManagementApi.ownerTransactions.create(payload);
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
        try {
            await cashManagementApi.ownerTransactions.delete(id);
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
        data, meta, page, setPage,
        loading: listLoading || mutating,
        error: listError || mutationError,
        filters, setFilters, refetch,
        create, delete: deleteItem,
    };
};
