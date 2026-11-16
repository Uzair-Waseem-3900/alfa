import { useCallback, useEffect, useRef, useState } from 'react';
import { bulkApi, streamBatch } from '../services/agentApi';
import { extractErrorMessage } from '../utils/errorMessage';
import { useToast } from '../context/ToastContext';
import { usePagedList } from './useTeamChats';

const PAGE_SIZE = 25;
const POLL_MS = 5000;
export const ACTIVE = 'active';

export const useBulkBatches = () =>
    usePagedList((p) => bulkApi.listBatches({ page: p, page_size: PAGE_SIZE }), 'batches', 'Could not load your bulk invoices');

export const useLinkNames = () => {
    const [options, setOptions] = useState([]);
    useEffect(() => {
        let cancelled = false;
        bulkApi.linkNames({ page: 1, page_size: 100 })
            .then((res) => { if (!cancelled) setOptions(res.results); })
            .catch(() => { /* the dropdown simply stays on "All" */ });
        return () => { cancelled = true; };
    }, []);
    return options;
};

// A live `item` event carries the row's full state: replace the row, keep what the event does not carry (the prompt).
const applyEvent = (items, d) =>
    items.map((row) => (row.id === d.item_id ? {
        ...row,
        status: d.status, attempts: d.attempts, question: d.question, options: d.options, message: d.message,
        bill_number: d.bill_number, invoice_id: d.invoice_id, customer_label: d.customer_label,
    } : row));

const replaceRow = (items, updated) => items.map((row) => (row.id === updated.id ? { ...row, ...updated } : row));

// One batch: loaded from the database (source of truth), then followed live over SSE while rows are working.
export const useBulkBatch = (batchId) => {
    const { toast } = useToast();
    const [batch, setBatch] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [pollFallback, setPollFallback] = useState(false);
    const [busyRows, setBusyRows] = useState({});
    const idRef = useRef(batchId);
    idRef.current = batchId;

    const load = useCallback(async ({ silent = false } = {}) => {
        if (!batchId) return;
        if (!silent) { setLoading(true); setError(null); }
        try {
            const data = await bulkApi.getBatch(batchId);
            if (idRef.current === batchId) setBatch(data);
        } catch (err) {
            if (!silent) setError(extractErrorMessage(err, 'Could not load this batch'));
        } finally {
            if (!silent) setLoading(false);
        }
    }, [batchId]);

    useEffect(() => {
        setBatch(null); setError(null); setPollFallback(false); setBusyRows({});
        if (batchId) load();
    }, [batchId, load]);

    const working = batch?.status === ACTIVE;

    // Live updates while any row is queued/processing.
    useEffect(() => {
        if (!batchId || !working) return undefined;
        const controller = new AbortController();
        streamBatch({
            batchId,
            signal: controller.signal,
            onEvent: (type, data) => {
                if (type === 'item') {
                    setBatch((prev) => (prev ? { ...prev, items: applyEvent(prev.items, data) } : prev));
                } else if (type === 'batch_idle') {
                    load({ silent: true });          // picks up the batch's own final status
                }
            },
        }).catch(() => {
            if (!controller.signal.aborted) setPollFallback(true);   // SSE unavailable: poll the database instead
        });
        return () => controller.abort();
    }, [batchId, working, load]);

    useEffect(() => {
        if (!pollFallback || !working) return undefined;
        const timer = setInterval(() => load({ silent: true }), POLL_MS);
        return () => clearInterval(timer);
    }, [pollFallback, working, load]);

    const act = useCallback(async (itemId, call, failText) => {
        setBusyRows((b) => ({ ...b, [itemId]: true }));
        try {
            const row = await call();
            setBatch((prev) => (prev ? {
                ...prev,
                status: row.status === 'queued' ? ACTIVE : prev.status,
                items: replaceRow(prev.items, row),
            } : prev));
            if (row.status !== 'queued') load({ silent: true });
            return true;
        } catch (err) {
            toast.error(extractErrorMessage(err, failText));
            return false;
        } finally {
            setBusyRows((b) => { const { [itemId]: _gone, ...rest } = b; return rest; });
        }
    }, [load, toast]);

    const answer = useCallback((itemId, text) => act(itemId, () => bulkApi.answer(itemId, text), 'Could not send your answer'), [act]);
    const skip = useCallback((itemId) => act(itemId, () => bulkApi.skip(itemId), 'Could not skip this invoice'), [act]);
    const retry = useCallback((itemId) => act(itemId, () => bulkApi.retry(itemId), 'Could not retry this invoice'), [act]);

    const cancel = useCallback(async () => {
        try {
            const data = await bulkApi.cancelBatch(batchId);
            setBatch(data);
            toast.success('Batch cancelled. The invoice being worked on will finish.');
        } catch (err) {
            toast.error(extractErrorMessage(err, 'Could not cancel the batch'));
        }
    }, [batchId, toast]);

    return { batch, loading, error, reload: load, busyRows, answer, skip, retry, cancel };
};
