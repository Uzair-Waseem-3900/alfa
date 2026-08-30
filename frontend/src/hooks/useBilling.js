import { useState, useEffect, useCallback } from 'react';
import { billingApi } from '../services/billingApi';
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
