import { useState, useEffect, useCallback } from 'react';
import { recurringExpensesApi } from '../services/recurringExpensesApi';
import { usePaginatedList } from './usePaginatedList';

// Hook for the all-time RecurringExpenseFlow singleton stats.
export const useRecurringExpenseFlowStats = () => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchStats = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const result = await recurringExpensesApi.flowStats.get();
            setData(result);
        } catch (err) {
            setError(err.message || 'Failed to fetch recurring expense stats');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchStats();
    }, [fetchStats]);

    return { data, loading, error, refetch: fetchStats };
};

// Hook for the paginated list of per-month synced stats rows.
export const useRecurringExpenseMonthlyStats = (initialFilters = {}) => {
    const {
        data, meta, loading, error, filters, setFilters, page, setPage, refetch,
    } = usePaginatedList((params) => recurringExpensesApi.monthlyStats.getAll(params), initialFilters);

    return { data, meta, loading, error, filters, setFilters, page, setPage, refetch };
};

// Hook for a single month's synced stats (assigned/paid/pending/is_fully_paid).
export const useRecurringExpenseMonthlyStatsDetail = (period) => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchStats = useCallback(async () => {
        if (!period) return;
        setLoading(true);
        setError(null);
        try {
            const result = await recurringExpensesApi.monthlyStats.getByPeriod(period);
            setData(result);
        } catch (err) {
            setError(err.message || 'Failed to fetch monthly stats');
        } finally {
            setLoading(false);
        }
    }, [period]);

    useEffect(() => {
        fetchStats();
    }, [fetchStats]);

    return { data, loading, error, refetch: fetchStats };
};

// Hook for category management (create + update + soft-delete).
export const useRecurringExpenseCategories = (initialFilters = {}) => {
    const {
        data, meta, loading: listLoading, error: listError,
        filters, setFilters, page, setPage, refetch,
    } = usePaginatedList((params) => recurringExpensesApi.categories.getAll(params), initialFilters);

    const [mutating, setMutating] = useState(false);
    const [mutationError, setMutationError] = useState(null);

    const create = async (payload) => {
        setMutating(true);
        try {
            const result = await recurringExpensesApi.categories.create(payload);
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
            const result = await recurringExpensesApi.categories.update(id, payload);
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
            await recurringExpensesApi.categories.delete(id);
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
        data, meta, page, setPage,
        loading: listLoading || mutating,
        error: listError || mutationError,
        filters, setFilters, refetch,
        create, update, delete: deleteItem,
    };
};

// Hook for template management (create + update + soft-delete).
export const useRecurringExpenseTemplates = (initialFilters = {}) => {
    const {
        data, meta, loading: listLoading, error: listError,
        filters, setFilters, page, setPage, refetch,
    } = usePaginatedList((params) => recurringExpensesApi.templates.getAll(params), initialFilters);

    const [mutating, setMutating] = useState(false);
    const [mutationError, setMutationError] = useState(null);

    const create = async (payload) => {
        setMutating(true);
        try {
            const result = await recurringExpensesApi.templates.create(payload);
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
            const result = await recurringExpensesApi.templates.update(id, payload);
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
            await recurringExpensesApi.templates.delete(id);
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
        data, meta, page, setPage,
        loading: listLoading || mutating,
        error: listError || mutationError,
        filters, setFilters, refetch,
        create, update, delete: deleteItem,
    };
};

// Hook for the Post Dues screen — active templates not yet assigned for a period.
export const useRecurringExpensePendingDues = (initialFilters = {}) => {
    const {
        data, meta, loading, error, filters, setFilters, page, setPage, refetch,
    } = usePaginatedList((params) => recurringExpensesApi.pendingDues.getAll(params), initialFilters);

    return { data, meta, loading, error, filters, setFilters, page, setPage, refetch };
};

// Hook for assignments (single create + bulk create — assignments are never updated/deleted).
export const useRecurringExpenseAssignments = (initialFilters = {}) => {
    const {
        data, meta, loading: listLoading, error: listError,
        filters, setFilters, page, setPage, refetch,
    } = usePaginatedList((params) => recurringExpensesApi.assignments.getAll(params), initialFilters);

    const [mutating, setMutating] = useState(false);
    const [mutationError, setMutationError] = useState(null);

    const create = async (payload) => {
        setMutating(true);
        try {
            const result = await recurringExpensesApi.assignments.create(payload);
            await refetch();
            return result;
        } catch (err) {
            setMutationError(err.message);
            throw err;
        } finally {
            setMutating(false);
        }
    };

    const bulkCreate = async (payload) => {
        setMutating(true);
        try {
            const result = await recurringExpensesApi.assignments.bulkCreate(payload);
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
        create, bulkCreate,
    };
};

// Hook for payments against a single assignment (create + delete), scoped via
// initialFilters={ assignment_id }.
export const useRecurringExpensePayments = (initialFilters = {}) => {
    const {
        data, meta, loading: listLoading, error: listError,
        filters, setFilters, page, setPage, refetch,
    } = usePaginatedList((params) => recurringExpensesApi.payments.getAll(params), initialFilters);

    const [mutating, setMutating] = useState(false);
    const [mutationError, setMutationError] = useState(null);

    const create = async (payload) => {
        setMutating(true);
        try {
            const result = await recurringExpensesApi.payments.create(payload);
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
            await recurringExpensesApi.payments.delete(id);
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
        data, meta, page, setPage,
        loading: listLoading || mutating,
        error: listError || mutationError,
        filters, setFilters, refetch,
        create, delete: deleteItem,
    };
};
