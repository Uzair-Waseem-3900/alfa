import { useState, useEffect, useCallback } from 'react';
import { ratesApi } from '../services/ratesApi';
import { purchasesApi } from '../services/purchasesApi';
import { usePaginatedList } from './usePaginatedList';

export const useRates = (initialFilters = {}) => {
    // Priced rates — paginated (25/page) and backend-searched, like every
    // other list endpoint. No client-side merging with the product catalog
    // here — see useUnpricedProducts for the "needs a price" queue.
    const {
        data: rates, meta, loading: listLoading, error: listError,
        filters, setFilters, page, setPage, refetch,
    } = usePaginatedList(ratesApi.getAll, initialFilters);

    const data = rates.map(rate => ({ product: rate.product, rate }));

    // Category filter dropdown — small, bounded list (same pattern as
    // Suppliers/Products elsewhere), fetched once rather than derived from
    // a full product prefetch.
    const [categories, setCategories] = useState([]);
    useEffect(() => {
        let cancelled = false;
        purchasesApi.categories.getAll({ page_size: 500 })
            .then(res => {
                if (cancelled) return;
                const cats = res?.results || res || [];
                setCategories(cats.filter(c => !c.is_deleted));
            })
            .catch(() => { if (!cancelled) setCategories([]); });
        return () => { cancelled = true; };
    }, []);

    const [mutating, setMutating] = useState(false);
    const [mutationError, setMutationError] = useState(null);

    const create = async (payload) => {
        setMutating(true);
        try {
            const result = await ratesApi.create(payload);
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
            const result = await ratesApi.update(id, payload);
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
        data,
        meta,
        page,
        setPage,
        loading: listLoading || mutating,
        error: listError || mutationError,
        filters,
        setFilters,
        categories,
        refetch,
        create,
        update,
    };
};

// Products with no rate set yet — paginated + backend-searched independently
// of the priced-rates list above, instead of being merged into it via a
// full-catalog prefetch.
export const useUnpricedProducts = (initialFilters = {}) => {
    const {
        data, meta, loading, error,
        filters, setFilters, page, setPage, refetch,
    } = usePaginatedList(ratesApi.getUnpriced, initialFilters);

    return { data, meta, page, setPage, loading, error, filters, setFilters, refetch };
};

export const useRateHistory = (productId) => {
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const fetchHistory = useCallback(async () => {
        if (!productId) return;
        setLoading(true);
        setError(null);
        try {
            const result = await ratesApi.getHistory(productId, { page_size: 500 });
            setData(result?.results ?? result ?? []);
        } catch (err) {
            setError(err.message || 'Failed to fetch history');
            setData([]);
        } finally {
            setLoading(false);
        }
    }, [productId]);

    useEffect(() => {
        fetchHistory();
    }, [fetchHistory]);

    return { data, loading, error, refetch: fetchHistory };
};
