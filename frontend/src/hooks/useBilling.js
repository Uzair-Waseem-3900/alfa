import { useState, useEffect, useCallback, useRef } from 'react';
import { billingApi } from '../services/billingApi';
import { extractErrorMessage } from '../utils/errorMessage';
import { usePaginatedList } from './usePaginatedList';

// Generic CRUD hook for billing resources — thin wrapper around usePaginatedList.
export const useBillingCRUD = (service, initialFilters = {}) => {
    const {
        data, meta, loading: listLoading, initialLoading, error: listError,
        filters, setFilters, page, setPage, refetch,
    } = usePaginatedList((params) => service.getAll(params), initialFilters);

    const [mutating, setMutating] = useState(false);
    const [mutationError, setMutationError] = useState(null);

    const create = async (payload) => {
        setMutating(true);
        try {
            const result = await service.create(payload);
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
            const result = await service.update(id, payload);
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
            await service.delete(id);
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

    const resetFilters = () => setFilters(initialFilters);

    return {
        data,
        meta,
        page,
        setPage,
        loading: listLoading || mutating,
        // Full-page spinner gate — true only before the very first load
        // completes. Mutations (create/update/delete) never re-trigger this,
        // only the initial mount does.
        initialLoading,
        error: listError || mutationError,
        filters,
        appliedFilters: filters,
        setFilters,
        resetFilters,
        refetch,
        create,
        update,
        delete: deleteItem,
    };
};

const isFilterValueSet = (v) => v !== '' && v !== null && v !== undefined;

// Filtered count + total outstanding for the Invoices page's current tab.
// `filters` is the list hook's filters object and `searchTerm` the page's
// search box (the page sends it to the list as `bill_number`, so it's merged
// the same way here). Fetches independently of the list so rows render
// without waiting on it, and only runs while a filter/search is active —
// `active` tells the page whether to show the card at all.
export const useInvoicesSummary = (scope, filters, searchTerm) => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    // Ignore a slow earlier response arriving after a newer request started.
    const requestId = useRef(0);

    const cleaned = Object.fromEntries(
        Object.entries(filters || {}).filter(([, v]) => isFilterValueSet(v))
    );
    if (searchTerm) cleaned.bill_number = searchTerm;
    const active = Object.keys(cleaned).length > 0;
    const requestKey = JSON.stringify({ scope, params: cleaned });

    const fetchSummary = useCallback(async () => {
        const id = ++requestId.current;
        if (!active) {
            setData(null);
            setError(null);
            setLoading(false);
            return;
        }
        setLoading(true);
        setError(null);
        try {
            const { scope: s, params } = JSON.parse(requestKey);
            const result = await billingApi.invoices.getSummary({ ...params, scope: s });
            if (id === requestId.current) setData(result);
        } catch (err) {
            if (id === requestId.current) setError(extractErrorMessage(err, 'Failed to load invoice totals'));
        } finally {
            if (id === requestId.current) setLoading(false);
        }
    }, [requestKey, active]);

    useEffect(() => {
        fetchSummary();
    }, [fetchSummary]);

    return { data, loading, error, active, refetch: fetchSummary };
};

// Recovery session status (active flag, running total, record count). Fetches
// on mount, independent of any list on the page it's used in. start()/stop()
// throw on failure so the caller can toast the error; the local state is
// updated from the response so no second round trip is needed.
export const useRecovery = () => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [mutating, setMutating] = useState(false);

    const fetchState = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            setData(await billingApi.recovery.getState());
        } catch (err) {
            setError(extractErrorMessage(err, 'Failed to load recovery status'));
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchState();
    }, [fetchState]);

    const start = async () => {
        setMutating(true);
        try {
            const state = await billingApi.recovery.start();
            setData(state);
            return state;
        } finally {
            setMutating(false);
        }
    };

    const stop = async () => {
        setMutating(true);
        try {
            await billingApi.recovery.stop();
            setData({ is_active: false, started_at: null, total_amount: '0', record_count: 0 });
        } finally {
            setMutating(false);
        }
    };

    return { data, loading, error, mutating, refetch: fetchState, start, stop };
};

// Paginated details of the active recovery session. Only mount the component
// that calls this while the details are actually open — it fetches on mount.
export const useRecoveryRecords = () => {
    const {
        data, meta, loading, error, page, setPage, refetch,
    } = usePaginatedList((params) => billingApi.recovery.getRecords(params));

    return { data, meta, loading, error, page, setPage, refetch };
};

// Hook for invoice detail with payment summary
export const useInvoiceDetail = (invoiceId) => {
    const [invoice, setInvoice] = useState(null);
    const [paymentSummary, setPaymentSummary] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const fetchDetail = useCallback(async () => {
        if (!invoiceId) return;
        setLoading(true);
        setError(null);
        try {
            const [invoiceData, summaryData] = await Promise.all([
                billingApi.invoices.getById(invoiceId),
                billingApi.invoices.getPaymentSummary(invoiceId),
            ]);
            setInvoice(invoiceData);
            setPaymentSummary(summaryData);
        } catch (err) {
            setError(err.message || 'Failed to fetch invoice details');
        } finally {
            setLoading(false);
        }
    }, [invoiceId]);

    useEffect(() => {
        fetchDetail();
    }, [fetchDetail]);

    return { invoice, paymentSummary, loading, error, refetch: fetchDetail };
};
