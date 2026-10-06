import { useState, useEffect, useCallback } from 'react';
import { b2bApi } from '../services/b2bApi';
import { usePaginatedList } from './usePaginatedList';
import { extractErrorMessage } from '../utils/errorMessage';

// The partner softwares this one is configured to read a rate list from.
export const useProviders = () => {
    const { data, loading, initialLoading, error, refetch } =
        usePaginatedList((params) => b2bApi.providers.getAll(params), {}, 25);
    return { providers: data, loading, initialLoading, error, refetch };
};

// One partner's live rate list. Every call goes to the partner (no cache, no
// stored copy). `status` is the partner's answer about OUR access
// (not_requested / pending / approved / rejected / revoked / not_configured);
// rows only arrive when approved. `provider` is a dep so switching partners refetches.
export const usePartnerRateList = (provider, initialFilters = {}) => {
    const {
        data, meta, extra, loading, initialLoading, error, filters, setFilters, page, setPage, refetch,
    } = usePaginatedList(
        (params) => (provider
            ? b2bApi.providers.rateList(provider, params)
            : Promise.resolve({ results: [], status: 'none' })),
        initialFilters,
        25,
        [provider],
    );

    return {
        data, meta, loading, initialLoading, error, filters, setFilters, page, setPage, refetch,
        status: extra?.status ?? null,
        detail: extra?.detail ?? '',
    };
};

// Ask (or ask again) for access. The page owns the toast and the refetch.
export const useRequestAccess = () => {
    const [mutating, setMutating] = useState(false);

    const requestAccess = async (provider) => {
        setMutating(true);
        try {
            return await b2bApi.providers.request(provider);
        } finally {
            setMutating(false);
        }
    };

    return { requestAccess, mutating };
};

// Purchase requests THIS software has made to partners, newest first.
export const usePurchaseRequests = (initialFilters = {}) => {
    const {
        data, meta, loading, initialLoading, error, filters, setFilters, page, setPage, refetch,
    } = usePaginatedList((params) => b2bApi.purchaseRequests.getAll(params), initialFilters);

    return { data, meta, loading, initialLoading, error, filters, setFilters, page, setPage, refetch };
};

// One request with its items and this software's own shelf plan. Hand-rolled (not list-shaped).
export const usePurchaseRequestDetail = (id) => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchDetail = useCallback(async ({ silent = false } = {}) => {
        if (!silent) setLoading(true);
        setError(null);
        try {
            setData(await b2bApi.purchaseRequests.getById(id));
        } catch (err) {
            setError(extractErrorMessage(err, 'Failed to load the request'));
            if (!silent) setData(null);
        } finally {
            setLoading(false);
        }
    }, [id]);

    useEffect(() => {
        fetchDetail();
    }, [fetchDetail]);

    return { data, loading, error, refetch: fetchDetail };
};

// Create / cancel / sync. The pages own the toasts and the refetch.
export const usePurchaseRequestActions = () => {
    const [mutating, setMutating] = useState(false);

    const run = async (fn) => {
        setMutating(true);
        try {
            return await fn();
        } finally {
            setMutating(false);
        }
    };

    return {
        create: (payload) => run(() => b2bApi.purchaseRequests.create(payload)),
        cancel: (id) => run(() => b2bApi.purchaseRequests.cancel(id)),
        sync: () => run(() => b2bApi.purchaseRequests.sync()),
        mutating,
    };
};
