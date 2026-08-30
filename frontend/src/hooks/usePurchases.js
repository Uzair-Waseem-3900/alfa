import { useState } from 'react';
import { purchasesApi } from '../services/purchasesApi';
import { usePaginatedList } from './usePaginatedList';

// Generic hook for CRUD operations — thin wrapper around usePaginatedList.
export const useCRUD = (service, initialFilters = {}) => {
    const {
        data, meta, loading: listLoading, error: listError,
        filters, setFilters, page, setPage, refetch,
    } = usePaginatedList((params) => service.getAll(params), initialFilters);

    const [mutating, setMutating] = useState(false);
    const [mutationError, setMutationError] = useState(null);

    const create = async (payload) => {
        setMutating(true);
        setMutationError(null);
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
        setMutationError(null);
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
        setMutationError(null);
        try {
            await service.delete(id);
            // Deleted the last item on a page beyond page 1 — step back a page.
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
        // Only the list fetch gates a full-page spinner — a create/update/
        // delete in flight (`mutating`) must not blank the whole page out
        // from under the user, since callers already show their own
        // form/button-level loading state for that.
        loading: listLoading,
        mutating,
        error: listError || mutationError,
        filters,
        setFilters,
        refetch,
        create,
        update,
        delete: deleteItem,
    };
};

// Hook for supplier outstanding — Suppliers are excluded from pagination
// (client confirmed there are only ~10-15), so this stays a plain list fetch.
// The suppliers-outstanding endpoint IS paginated (only the plain suppliers
// list is excluded), so this wraps usePaginatedList like the other lists.
export const useSuppliersOutstanding = (initialFilters = {}) => {
    const { data, meta, loading, error, filters, setFilters, page, setPage, refetch } =
        usePaginatedList((params) => purchasesApi.suppliers.getOutstanding(params), initialFilters);

    return { data, meta, page, setPage, loading, error, filters, setFilters, refetch };
};
