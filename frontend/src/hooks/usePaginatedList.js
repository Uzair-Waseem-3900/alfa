import { useState, useEffect, useCallback, useRef } from 'react';
import { extractErrorMessage } from '../utils/errorMessage';

// Shared primitive: unwraps a {count, total_pages, current_page, page_size,
// results} paginated response and tracks page/filters state. Every list
// consumer in the app routes through this, directly or via a wrapping hook.
//
// `deps` — extra values that a caller's fetchFn closes over (e.g. a page's
// local searchTerm / activeTab). Listing them here re-runs the fetch when they
// change. It does NOT need to (and must not) include fetchFn itself: fetchFn is
// held in a ref so an inline arrow recreated every render doesn't retrigger the
// effect — that was previously causing an infinite refetch loop.
export const usePaginatedList = (fetchFn, initialFilters = {}, pageSize = 25, deps = []) => {
    const [results, setResults] = useState([]);
    const [meta, setMeta] = useState({ count: 0, totalPages: 1, currentPage: 1, pageSize });
    const [loading, setLoading] = useState(false);
    // True only until the FIRST fetch (success or failure) completes — a
    // page uses this to gate a full-page blocking spinner on first mount
    // only. `loading` stays true on every later refetch (filter/tab/page
    // change) too, but by then the page already has content to keep
    // showing instead of blanking to a spinner on every interaction.
    const [hasLoadedOnce, setHasLoadedOnce] = useState(false);
    const [error, setError] = useState(null);
    const [filters, setFiltersState] = useState(initialFilters);
    const [page, setPage] = useState(1);
    const [extra, setExtra] = useState({});

    // Keep the latest fetchFn without making it an effect dependency.
    const fetchFnRef = useRef(fetchFn);
    fetchFnRef.current = fetchFn;

    const fetchData = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            // Strip undefined/null filter values before they reach
            // URLSearchParams — otherwise `new URLSearchParams({x: undefined})`
            // serializes the literal string "x=undefined" instead of omitting
            // the key, which backend filters then match against (finding
            // nothing) instead of ignoring. Empty string is left as-is since
            // some callers intentionally send it.
            const cleanFilters = Object.fromEntries(
                Object.entries(filters).filter(([, v]) => v !== undefined && v !== null)
            );
            const response = await fetchFnRef.current({ ...cleanFilters, page, page_size: pageSize });
            // Some endpoints (e.g. Suppliers) are deliberately excluded from
            // pagination and still return a plain array — handle both shapes.
            if (Array.isArray(response)) {
                setResults(response);
                setMeta({ count: response.length, totalPages: 1, currentPage: 1, pageSize: response.length });
                setExtra({});
            } else {
                setResults(response?.results || []);
                setMeta({
                    count: response?.count ?? 0,
                    totalPages: response?.total_pages ?? 1,
                    currentPage: response?.current_page ?? page,
                    pageSize: response?.page_size ?? pageSize,
                });
                // Any extra top-level fields a view adds (e.g. "stats") pass through as-is.
                const { count, total_pages, current_page, page_size, results, ...rest } = response || {};
                setExtra(rest);
            }
        } catch (err) {
            setError(extractErrorMessage(err, 'Failed to fetch data'));
            setResults([]);
        } finally {
            setLoading(false);
            setHasLoadedOnce(true);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [filters, page, pageSize, ...deps]);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    // Changing filters always resets back to page 1.
    const setFilters = (newFilters) => {
        setFiltersState(newFilters);
        setPage(1);
    };

    return {
        data: results, meta, extra, loading, error, filters, setFilters, page, setPage, refetch: fetchData,
        // Only true before the very first fetch completes — use this (not
        // `loading`) to gate a full-page blocking spinner, so a filter/tab
        // change on page 2+ keeps the existing content visible instead of
        // blanking the whole page on every interaction.
        initialLoading: loading && !hasLoadedOnce,
    };
};
