import { fetchEventSource } from '@microsoft/fetch-event-source';
import { api, refreshAccessToken } from '../utils/api';
import { backendConfig } from '../config';

// Chats + history go through the shared axios client (auto token refresh).
export const agentApi = {
    listChats: (params = {}) => api.get('/agent/chats/', { params }),
    createChat: () => api.post('/agent/chats/', {}),
    renameChat: (id, title) => api.patch(`/agent/chats/${id}/`, { title }),
    deleteChat: (id) => api.delete(`/agent/chats/${id}/`),
    // newest first (page 1 = latest messages)
    getMessages: (id, params = {}) => api.get(`/agent/chats/${id}/messages/`, { params }),
    sendMessage: (id, content) => api.post(`/agent/chats/${id}/messages/`, { content }),
};

// Superuser-only, READ-ONLY view of every user's chats.
export const teamApi = {
    listOwners: (params = {}) => api.get('/agent/team/users/', { params }),
    listChats: (email, params = {}) => api.get(`/agent/team/users/${encodeURIComponent(email)}/chats/`, { params }),
    getChat: (id) => api.get(`/agent/team/chats/${id}/`),
    getMessages: (id, params = {}) => api.get(`/agent/team/chats/${id}/messages/`, { params }),
};

// Superuser-only, READ-ONLY view of every user's bulk-invoice batches.
export const teamBulkApi = {
    listOwners: (params = {}) => api.get('/agent/team/bulk/users/', { params }),
    listBatches: (email, params = {}) => api.get(`/agent/team/bulk/users/${encodeURIComponent(email)}/batches/`, { params }),
    getBatch: (id) => api.get(`/agent/team/bulk/batches/${id}/`),
};

// Bulk invoices: many prompts, one draft invoice each, worked one after another on the server.
export const bulkApi = {
    linkNames: (params = {}) => api.get('/agent/bulk/link-names/', { params }),
    listBatches: (params = {}) => api.get('/agent/bulk/batches/', { params }),
    createBatch: ({ prompts, linkNameId }) =>
        api.post('/agent/bulk/batches/', { prompts, link_name_id: linkNameId || null }),
    getBatch: (id) => api.get(`/agent/bulk/batches/${id}/`),
    deleteBatch: (id) => api.delete(`/agent/bulk/batches/${id}/`),
    renameBatch: (id, title) => api.patch(`/agent/bulk/batches/${id}/`, { title }),
    cancelBatch: (id) => api.post(`/agent/bulk/batches/${id}/cancel/`, {}),
    answer: (itemId, answer) => api.post(`/agent/bulk/items/${itemId}/answer/`, { answer }),
    skip: (itemId) => api.post(`/agent/bulk/items/${itemId}/skip/`, {}),
    retry: (itemId) => api.post(`/agent/bulk/items/${itemId}/retry/`, {}),
};

class AuthExpiredError extends Error {}
class FatalStreamError extends Error {}
class RetriableStreamError extends Error {}

const RUN_TERMINAL_EVENTS = new Set(['done', 'error']);
const BATCH_TERMINAL_EVENTS = new Set(['batch_idle']);

const openStream = async ({ path, terminalEvents, signal, onEvent }) => {
    let finished = false;
    await fetchEventSource(`${backendConfig.getAPIURL()}${path}`, {
        signal,
        headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}`, Accept: 'text/event-stream' },
        // Keep streaming if the user switches tabs mid-answer.
        openWhenHidden: true,
        async onopen(response) {
            if (response.ok && (response.headers.get('content-type') || '').startsWith('text/event-stream')) return;
            if (response.status === 401) throw new AuthExpiredError();
            throw new FatalStreamError(`Stream failed (${response.status})`);
        },
        onmessage(msg) {
            if (!msg.event) return;
            let data = {};
            try {
                data = JSON.parse(msg.data);
            } catch {
                return;
            }
            onEvent(msg.event, data);
            if (terminalEvents.has(msg.event)) finished = true;
        },
        // The server closes the stream right after a terminal event. Closing
        // earlier means a dropped connection -> throw so the library reconnects
        // (it resends Last-Event-ID and the server replays what was missed).
        onclose() {
            if (!finished) throw new RetriableStreamError();
        },
        onerror(err) {
            if (err instanceof AuthExpiredError || err instanceof FatalStreamError) throw err;
            return 1000; // retry in 1s
        },
    });
};

// One reconnect-aware stream; an expired token is refreshed once (shared with axios) and the stream reopened.
const stream = async (args) => {
    try {
        await openStream(args);
    } catch (err) {
        if (!(err instanceof AuthExpiredError)) throw err;
        await refreshAccessToken();
        await openStream(args);
    }
};

// Streams one run's events to `onEvent(type, data)`. Resolves after a terminal event; rejects on an unrecoverable failure.
export const streamRun = ({ runId, signal, onEvent }) =>
    stream({ path: `/agent/runs/${runId}/stream/`, terminalEvents: RUN_TERMINAL_EVENTS, signal, onEvent });

// Live row updates of a bulk batch (`item`, then `batch_idle` when nothing is queued or processing).
export const streamBatch = ({ batchId, signal, onEvent }) =>
    stream({ path: `/agent/bulk/batches/${batchId}/stream/`, terminalEvents: BATCH_TERMINAL_EVENTS, signal, onEvent });
