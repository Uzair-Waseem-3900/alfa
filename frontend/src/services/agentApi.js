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

class AuthExpiredError extends Error {}
class FatalStreamError extends Error {}
class RetriableStreamError extends Error {}

const TERMINAL_EVENTS = new Set(['done', 'error']);

const openStream = async ({ runId, signal, onEvent }) => {
    let finished = false;
    await fetchEventSource(`${backendConfig.getAPIURL()}/agent/runs/${runId}/stream/`, {
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
            if (TERMINAL_EVENTS.has(msg.event)) finished = true;
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

// Streams one run's events to `onEvent(type, data)`. Resolves after a terminal
// event; rejects on an unrecoverable failure. An expired token is refreshed
// once (shared with axios) and the stream reopened.
export const streamRun = async ({ runId, signal, onEvent }) => {
    try {
        await openStream({ runId, signal, onEvent });
    } catch (err) {
        if (!(err instanceof AuthExpiredError)) throw err;
        await refreshAccessToken();
        await openStream({ runId, signal, onEvent });
    }
};
