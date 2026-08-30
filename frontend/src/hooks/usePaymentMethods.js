import { useState, useEffect, useCallback } from 'react';
import { paymentMethodsApi } from '../services/paymentMethodsApi';
import { usePaginatedList } from './usePaginatedList';
import { extractErrorMessage } from '../utils/errorMessage';

// Paginated list of payment methods (Cash, JazzCash, Easypaisa, or any
// user-created account). Mirrors every other list-hook in the app.
export const usePaymentMethods = (initialFilters = {}) => {
    const {
        data, meta, loading, error, filters, setFilters, page, setPage, refetch,
    } = usePaginatedList((params) => paymentMethodsApi.methods.getAll(params), initialFilters);

    return { data, meta, loading, error, filters, setFilters, page, setPage, refetch };
};

// Single payment method's own detail — hand-rolled state since there's no
// list-shaped sub-resource backing it (same shape as useLedgerDetail).
export const usePaymentMethod = (id) => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [notFound, setNotFound] = useState(false);

    const fetchMethod = useCallback(async () => {
        if (!id) return;
        setLoading(true);
        setError(null);
        setNotFound(false);
        try {
            const result = await paymentMethodsApi.methods.getById(id);
            setData(result);
        } catch (err) {
            if (err?.response?.status === 404) {
                setNotFound(true);
            } else {
                setError(extractErrorMessage(err, 'Failed to load payment method'));
            }
            setData(null);
        } finally {
            setLoading(false);
        }
    }, [id]);

    useEffect(() => {
        fetchMethod();
    }, [fetchMethod]);

    return { data, loading, error, notFound, refetch: fetchMethod };
};

// Paginated transaction history for a single payment method.
export const useMethodAllocations = (methodId, initialFilters = {}) => {
    const {
        data, meta, loading, error, filters, setFilters, page, setPage, refetch,
    } = usePaginatedList(
        (params) => paymentMethodsApi.allocations.getForMethod(methodId, params),
        initialFilters,
        25,
        [methodId]
    );

    return { data, meta, loading, error, filters, setFilters, page, setPage, refetch };
};

// Paginated list of account transfers (between two payment methods).
export const useAccountTransfers = (initialFilters = {}) => {
    const {
        data, meta, loading, error, filters, setFilters, page, setPage, refetch,
    } = usePaginatedList((params) => paymentMethodsApi.transfers.getAll(params), initialFilters);

    return { data, meta, loading, error, filters, setFilters, page, setPage, refetch };
};

// ==================== MUTATION HOOKS ====================
// Standalone (not list-owning) mutation hooks — each follows the same
// mutating + try/catch/finally shape as useCashManagement.js's embedded
// mutations, but since they don't own a list here, callers are responsible
// for calling their own list hook's refetch() after a successful mutation
// (and for stepping back a page on the last-row-deleted case).

export const useCreateMethod = () => {
    const [mutating, setMutating] = useState(false);
    const [error, setError] = useState(null);

    const create = async (payload) => {
        setMutating(true);
        setError(null);
        try {
            return await paymentMethodsApi.methods.create(payload);
        } catch (err) {
            setError(extractErrorMessage(err, 'Failed to create payment method'));
            throw err;
        } finally {
            setMutating(false);
        }
    };

    return { create, mutating, error };
};

export const useUpdateMethod = () => {
    const [mutating, setMutating] = useState(false);
    const [error, setError] = useState(null);

    const update = async (id, payload) => {
        setMutating(true);
        setError(null);
        try {
            return await paymentMethodsApi.methods.update(id, payload);
        } catch (err) {
            setError(extractErrorMessage(err, 'Failed to update payment method'));
            throw err;
        } finally {
            setMutating(false);
        }
    };

    return { update, mutating, error };
};

export const useDeleteMethod = () => {
    const [mutating, setMutating] = useState(false);
    const [error, setError] = useState(null);

    const deleteMethod = async (id) => {
        setMutating(true);
        setError(null);
        try {
            return await paymentMethodsApi.methods.delete(id);
        } catch (err) {
            setError(extractErrorMessage(err, 'Failed to delete payment method'));
            throw err;
        } finally {
            setMutating(false);
        }
    };

    return { delete: deleteMethod, mutating, error };
};

export const useCreateTransfer = () => {
    const [mutating, setMutating] = useState(false);
    const [error, setError] = useState(null);

    const create = async (payload) => {
        setMutating(true);
        setError(null);
        try {
            return await paymentMethodsApi.transfers.create(payload);
        } catch (err) {
            setError(extractErrorMessage(err, 'Failed to create transfer'));
            throw err;
        } finally {
            setMutating(false);
        }
    };

    return { create, mutating, error };
};

export const useDeleteTransfer = () => {
    const [mutating, setMutating] = useState(false);
    const [error, setError] = useState(null);

    const deleteTransfer = async (id) => {
        setMutating(true);
        setError(null);
        try {
            return await paymentMethodsApi.transfers.delete(id);
        } catch (err) {
            setError(extractErrorMessage(err, 'Failed to reverse transfer'));
            throw err;
        } finally {
            setMutating(false);
        }
    };

    return { delete: deleteTransfer, mutating, error };
};
