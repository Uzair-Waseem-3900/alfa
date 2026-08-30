import { useState, useEffect, useCallback } from 'react';
import { backupsApi } from '../services/backupsApi';
import { usePaginatedList } from './usePaginatedList';

// Hook for the two backup watermarks (last local/remote backup time)
export const useBackupStats = () => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchStats = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const result = await backupsApi.stats.get();
            setData(result);
        } catch (err) {
            setError(err.message || 'Failed to fetch backup stats');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchStats();
    }, [fetchStats]);

    return { data, loading, error, refetch: fetchStats };
};

// Hook for the backup history list — thin wrapper around usePaginatedList.
export const useBackupHistory = () => {
    const { data, meta, loading, error, page, setPage, refetch } =
        usePaginatedList(backupsApi.history.getAll, {});

    return { data, meta, loading, error, page, setPage, refetch };
};
