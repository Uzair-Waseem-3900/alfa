import { useState, useEffect, useCallback } from 'react';
import { activityLogApi } from '../services/activityLogApi';
import { usePaginatedList } from './usePaginatedList';

// Paginated, filterable event feed — routes through the shared
// usePaginatedList primitive like every other list page in this app.
// `searchTerm`/`highRisk` are folded into the request params on top of
// whatever's in `filters` (set via the returned `setFilters`), and are
// listed as extra deps so changing either triggers a refetch.
export const useActivityLogEvents = (searchTerm = '', highRisk = false) => {
    const fetchEvents = (params) => {
        const p = { ...params };
        if (searchTerm) p.search = searchTerm;
        if (highRisk) p.high_risk = 'true';
        return activityLogApi.events.getAll(p);
    };

    return usePaginatedList(fetchEvents, {}, 25, [searchTerm, highRisk]);
};

// O(1) singleton stats header — not paginated, its own tiny fetch.
export const useActivityLogStats = () => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchData = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const result = await activityLogApi.stats.get();
            setData(result);
        } catch (err) {
            setError(err.message || 'Failed to fetch activity stats');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    return { data, loading, error, refetch: fetchData };
};
