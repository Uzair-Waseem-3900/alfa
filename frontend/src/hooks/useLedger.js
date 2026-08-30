import { useState, useEffect, useCallback } from 'react';
import { ledgerApi } from '../services/ledgerApi';
import { usePaginatedList } from './usePaginatedList';

// Hook for ledger list — thin wrapper around usePaginatedList.
// `api` defaults to the supplier ledger client; pass `customerLedgerApi` to
// reuse this same hook for customer ledgers instead of duplicating it.
// `deps` is forwarded to usePaginatedList so a caller switching api clients
// (e.g. a tab toggle) can force a refetch even when filters/page haven't
// changed themselves.
export const useLedgerList = (initialFilters = {}, api = ledgerApi, deps = []) => {
    const { data, meta, loading, initialLoading, error, filters, setFilters, page, setPage, refetch } =
        usePaginatedList((params) => api.getAll(params), initialFilters, 25, deps);

    return { data, meta, page, setPage, loading, initialLoading, error, filters, setFilters, refetch };
};

// Hook for ledger detail — entries come back paginated (manually, on the
// backend, since running balance is computed over the full history first).
// `api` defaults to the supplier ledger client; pass `customerLedgerApi` for
// the customer ledger detail page.
export const useLedgerDetail = (ledgerId, initialFilters = {}, pageSize = 25, api = ledgerApi) => {
    const [ledger, setLedger] = useState(null);
    const [entries, setEntries] = useState([]);
    const [meta, setMeta] = useState({ count: 0, totalPages: 1, currentPage: 1, pageSize });
    const [closingBalance, setClosingBalance] = useState(0);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [filters, setFiltersState] = useState(initialFilters);
    const [page, setPage] = useState(1);

    const fetchData = useCallback(async () => {
        if (!ledgerId) return;
        setLoading(true);
        setError(null);
        try {
            const cleanFilters = {};
            Object.keys(filters).forEach(key => {
                if (filters[key] !== '' && filters[key] !== null && filters[key] !== undefined) {
                    cleanFilters[key] = filters[key];
                }
            });
            const result = await api.getById(ledgerId, { ...cleanFilters, page, page_size: pageSize });
            setLedger(result.ledger);
            setEntries(result.results || []);
            setClosingBalance(result.closing_balance || 0);
            setMeta({
                count: result.count ?? 0,
                totalPages: result.total_pages ?? 1,
                currentPage: result.current_page ?? page,
                pageSize: result.page_size ?? pageSize,
            });
        } catch (err) {
            setError(err.message || 'Failed to fetch ledger details');
            setEntries([]);
        } finally {
            setLoading(false);
        }
    }, [ledgerId, filters, page, pageSize, api]);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    const setFilters = (newFilters) => {
        setFiltersState(newFilters);
        setPage(1);
    };

    return {
        ledger,
        entries,
        meta,
        page,
        setPage,
        closingBalance,
        loading,
        error,
        filters,
        setFilters,
        refetch: fetchData
    };
};

// Hook for saved PDFs — `api` defaults to the supplier ledger client; pass
// `customerLedgerApi` for the customer ledger detail page.
export const useSavedPDFs = (ledgerId, api = ledgerApi) => {
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const fetchData = useCallback(async () => {
        if (!ledgerId) return;
        setLoading(true);
        setError(null);
        try {
            const result = await api.getSavedPDFs(ledgerId, { page_size: 500 });
            setData(result?.results ?? result ?? []);
        } catch (err) {
            setError(err.message || 'Failed to fetch saved PDFs');
            setData([]);
        } finally {
            setLoading(false);
        }
    }, [ledgerId, api]);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    const deletePDF = async (pdfId) => {
        setLoading(true);
        try {
            await api.deleteSavedPDF(pdfId);
            await fetchData();
        } catch (err) {
            setError(err.message);
            throw err;
        } finally {
            setLoading(false);
        }
    };

    return { data, loading, error, refetch: fetchData, deletePDF };
};