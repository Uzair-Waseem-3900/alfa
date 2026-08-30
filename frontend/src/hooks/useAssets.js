import { useState, useEffect, useCallback } from 'react';
import { assetsApi } from '../services/assetsApi';
import { usePaginatedList } from './usePaginatedList';

// Hook for the asset stats (cost, current worth, accumulated depreciation, disposals)
export const useAssetStats = () => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchStats = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const result = await assetsApi.stats.get();
            setData(result);
        } catch (err) {
            setError(err.message || 'Failed to fetch asset stats');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchStats();
    }, [fetchStats]);

    return { data, loading, error, refetch: fetchStats };
};

// Hook for asset category management (create + update — valuation_method is immutable, no delete endpoint).
export const useAssetCategories = (initialFilters = {}) => {
    const {
        data, meta, loading: listLoading, error: listError,
        filters, setFilters, page, setPage, refetch,
    } = usePaginatedList((params) => assetsApi.categories.getAll(params), initialFilters);

    const [mutating, setMutating] = useState(false);
    const [mutationError, setMutationError] = useState(null);

    const create = async (payload) => {
        setMutating(true);
        try {
            const result = await assetsApi.categories.create(payload);
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
            const result = await assetsApi.categories.update(id, payload);
            await refetch();
            return result;
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
        create, update,
    };
};

// Hook for asset (item) management — create only here; revalue/dispose are
// separate actions performed from the detail page.
export const useAssets = (initialFilters = {}) => {
    const {
        data, meta, loading: listLoading, error: listError,
        filters, setFilters, page, setPage, refetch,
    } = usePaginatedList((params) => assetsApi.items.getAll(params), initialFilters);

    const [mutating, setMutating] = useState(false);
    const [mutationError, setMutationError] = useState(null);

    const create = async (payload) => {
        setMutating(true);
        try {
            const result = await assetsApi.items.create(payload);
            await refetch();
            return result;
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
        create,
    };
};

// Hook for a single asset's valuation history, scoped via initialFilters={ asset_id }.
export const useAssetValuationEntries = (initialFilters = {}) => {
    const {
        data, meta, loading, error, filters, setFilters, page, setPage, refetch,
    } = usePaginatedList((params) => assetsApi.valuationEntries.getAll(params), initialFilters);

    return { data, meta, loading, error, filters, setFilters, page, setPage, refetch };
};

// Hook for the disposals list (read-only audit trail).
export const useAssetDisposals = (initialFilters = {}) => {
    const {
        data, meta, loading, error, filters, setFilters, page, setPage, refetch,
    } = usePaginatedList((params) => assetsApi.disposals.getAll(params), initialFilters);

    return { data, meta, loading, error, filters, setFilters, page, setPage, refetch };
};

// Hook for the unified asset payments feed (purchases + sales, read-only).
export const useAssetPayments = (initialFilters = {}) => {
    const {
        data, meta, loading, error, filters, setFilters, page, setPage, refetch,
    } = usePaginatedList((params) => assetsApi.payments.getAll(params), initialFilters);

    return { data, meta, loading, error, filters, setFilters, page, setPage, refetch };
};
