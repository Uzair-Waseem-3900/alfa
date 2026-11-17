import { useCallback, useEffect, useState } from 'react';
import { teamBulkApi } from '../services/agentApi';
import { extractErrorMessage } from '../utils/errorMessage';
import { usePagedList } from './useTeamChats';

const PAGE_SIZE = 25;
const POLL_MS = 5000;

export const useTeamBulkOwners = () =>
    usePagedList((p) => teamBulkApi.listOwners({ page: p, page_size: PAGE_SIZE }), 'bulk-owners', 'Could not load users');

export const useTeamBulkBatches = (email) =>
    usePagedList(
        email ? (p) => teamBulkApi.listBatches(email, { page: p, page_size: PAGE_SIZE }) : null,
        `bulk:${email || ''}`, 'Could not load batches',
    );

// One batch, read only. While its invoices are still being created the page re-reads it every few seconds
// (a viewer has no live stream: the database is the truth).
export const useTeamBulkBatch = (batchId) => {
    const [batch, setBatch] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const load = useCallback(async (silent) => {
        if (!batchId) return;
        if (!silent) { setLoading(true); setError(null); }
        try {
            setBatch(await teamBulkApi.getBatch(batchId));
        } catch (err) {
            if (!silent) setError(extractErrorMessage(err, 'Could not load this batch'));
        } finally {
            if (!silent) setLoading(false);
        }
    }, [batchId]);

    useEffect(() => {
        setBatch(null); setError(null);
        load(false);
    }, [load]);

    const active = batch?.status === 'active';
    useEffect(() => {
        if (!active) return undefined;
        const timer = setInterval(() => load(true), POLL_MS);
        return () => clearInterval(timer);
    }, [active, load]);

    return { batch, loading, error, reload: () => load(false) };
};
