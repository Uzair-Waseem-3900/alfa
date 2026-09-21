import { useState, useEffect, useCallback } from 'react';
import { salesManApi } from '../services/salesManApi';
import { usePaginatedList } from './usePaginatedList';

export const useSalesManList = (initialFilters = {}) => {
    const {
        data, meta, loading, initialLoading, error,
        filters, setFilters, page, setPage, refetch,
    } = usePaginatedList((params) => salesManApi.salesMen.getAll(params), initialFilters);

    return { data, meta, loading, initialLoading, error, filters, setFilters, page, setPage, refetch };
};

export const useSalesManDetail = (salesManId) => {
    const [salesMan, setSalesMan] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const fetchDetail = useCallback(async () => {
        if (!salesManId) return;
        setLoading(true);
        setError(null);
        try {
            const data = await salesManApi.salesMen.getById(salesManId);
            setSalesMan(data);
        } catch (err) {
            setError(err.message || 'Failed to fetch sales man details');
        } finally {
            setLoading(false);
        }
    }, [salesManId]);

    useEffect(() => {
        fetchDetail();
    }, [fetchDetail]);

    return { salesMan, loading, error, refetch: fetchDetail };
};

export const useSalesManCustomers = (salesManId, filters = {}, deps = []) => {
    return usePaginatedList(
        (params) => salesManApi.customers.getAll(salesManId, params),
        filters, 25, [salesManId, ...deps],
    );
};

export const useSalesManInvoices = (salesManId, filters = {}, deps = []) => {
    return usePaginatedList(
        (params) => salesManApi.invoices.getAll(salesManId, params),
        filters, 25, [salesManId, ...deps],
    );
};

// Flat dropdown source for CustomerForm — every active link name across all
// sales men. Not paginated (small, bounded dataset).
export const useSalesManLinkNameOptions = () => {
    const [linkNames, setLinkNames] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const fetchOptions = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await salesManApi.linkNames.getAllOptions();
            setLinkNames(Array.isArray(data) ? data : data?.results || []);
        } catch (err) {
            setError(err.message || 'Failed to fetch sales man link names');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchOptions();
    }, [fetchOptions]);

    return { linkNames, loading, error, refetch: fetchOptions };
};

export const useSalesManLinkNames = (salesManId) => {
    const [linkNames, setLinkNames] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const fetchLinkNames = useCallback(async () => {
        if (!salesManId) return;
        setLoading(true);
        setError(null);
        try {
            const data = await salesManApi.linkNames.getAll(salesManId);
            setLinkNames(Array.isArray(data) ? data : data?.results || []);
        } catch (err) {
            setError(err.message || 'Failed to fetch link names');
        } finally {
            setLoading(false);
        }
    }, [salesManId]);

    useEffect(() => {
        fetchLinkNames();
    }, [fetchLinkNames]);

    return { linkNames, loading, error, refetch: fetchLinkNames };
};
