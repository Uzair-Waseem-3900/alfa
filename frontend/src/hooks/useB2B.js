import { useState } from 'react';
import { b2bApi } from '../services/b2bApi';
import { usePaginatedList } from './usePaginatedList';

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
