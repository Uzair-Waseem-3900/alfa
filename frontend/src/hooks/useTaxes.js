import { useState, useEffect, useCallback } from 'react';
import { taxesApi } from '../services/taxesApi';
import { usePaginatedList } from './usePaginatedList';

// Hook for the tax-position stats (Input/Output tax, net payable, WHT info)
export const useTaxesStats = () => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchStats = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const result = await taxesApi.stats.get();
            setData(result);
        } catch (err) {
            setError(err.message || 'Failed to fetch tax stats');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchStats();
    }, [fetchStats]);

    return { data, loading, error, refetch: fetchStats };
};

// Hook for tax payment management (create + delete only — no update endpoint).
export const useTaxPayments = (initialFilters = {}) => {
    const {
        data, meta, loading: listLoading, error: listError,
        filters, setFilters, page, setPage, refetch,
    } = usePaginatedList((params) => taxesApi.payments.getAll(params), initialFilters);

    const [mutating, setMutating] = useState(false);
    const [mutationError, setMutationError] = useState(null);

    const create = async (payload) => {
        setMutating(true);
        try {
            const result = await taxesApi.payments.create(payload);
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
            await taxesApi.payments.delete(id);
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
        loading: listLoading || mutating,
        error: listError || mutationError,
        filters,
        setFilters,
        refetch,
        create,
        delete: deleteItem,
    };
};

// Hook for WHT payment management (create + delete only — no update endpoint).
export const useWHTPayments = (initialFilters = {}) => {
    const {
        data, meta, loading: listLoading, error: listError,
        filters, setFilters, page, setPage, refetch,
    } = usePaginatedList((params) => taxesApi.whtPayments.getAll(params), initialFilters);

    const [mutating, setMutating] = useState(false);
    const [mutationError, setMutationError] = useState(null);

    const create = async (payload) => {
        setMutating(true);
        try {
            const result = await taxesApi.whtPayments.create(payload);
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
            await taxesApi.whtPayments.delete(id);
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
        loading: listLoading || mutating,
        error: listError || mutationError,
        filters,
        setFilters,
        refetch,
        create,
        delete: deleteItem,
    };
};
