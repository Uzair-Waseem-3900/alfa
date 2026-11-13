import { useState, useEffect, useCallback, useRef } from 'react';
import { agentApi, streamRun } from '../services/agentApi';
import { extractErrorMessage } from '../utils/errorMessage';
import { useToast } from '../context/ToastContext';

const PAGE_SIZE = 25;

// Newest-first page results -> keep chats in server order, dedupe by id.
const mergeChatsTop = (incoming, existing) => {
    const seen = new Set(incoming.map((c) => c.id));
    return [...incoming, ...existing.filter((c) => !seen.has(c.id))];
};

const toMessage = (m) => ({ id: m.id, role: m.role, text: m.text });

// Merge messages by id, ascending (oldest first). New messages shift page
// boundaries, so overlapping pages are expected — dedupe, never duplicate.
const mergeMessagesAsc = (a, b) => {
    const byId = new Map();
    [...a, ...b].forEach((m) => byId.set(m.id, m));
    return [...byId.values()].sort((x, y) => x.id - y.id);
};

/* ------------------------------------------------------------------ chats */

export const useAgentChats = () => {
    const toast = useToast();
    const [chats, setChats] = useState([]);
    const [loading, setLoading] = useState(true);
    const [loadingMore, setLoadingMore] = useState(false);
    const [error, setError] = useState(null);
    const [page, setPage] = useState(1);
    const [totalPages, setTotalPages] = useState(1);

    const fetchFirstPage = useCallback(async ({ silent = false } = {}) => {
        if (!silent) {
            setLoading(true);
            setError(null);
        }
        try {
            const res = await agentApi.listChats({ page: 1, page_size: PAGE_SIZE });
            setChats((prev) => (silent ? mergeChatsTop(res.results, prev) : res.results));
            setTotalPages(res.total_pages);
            if (!silent) setPage(1);
        } catch (err) {
            if (!silent) setError(extractErrorMessage(err, 'Could not load your chats'));
        } finally {
            if (!silent) setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchFirstPage();
    }, [fetchFirstPage]);

    const loadMore = useCallback(async () => {
        if (loadingMore || page >= totalPages) return;
        setLoadingMore(true);
        try {
            const res = await agentApi.listChats({ page: page + 1, page_size: PAGE_SIZE });
            setChats((prev) => {
                const seen = new Set(prev.map((c) => c.id));
                return [...prev, ...res.results.filter((c) => !seen.has(c.id))];
            });
            setPage(page + 1);
            setTotalPages(res.total_pages);
        } catch (err) {
            toast.error(extractErrorMessage(err, 'Could not load more chats'));
        } finally {
            setLoadingMore(false);
        }
    }, [loadingMore, page, totalPages, toast]);

    const createChat = useCallback(async () => {
        try {
            const chat = await agentApi.createChat();
            setChats((prev) => mergeChatsTop([chat], prev));
            return chat;
        } catch (err) {
            toast.error(extractErrorMessage(err, 'Could not start a new chat'));
            return null;
        }
    }, [toast]);

    const renameChat = useCallback(async (id, title) => {
        const previous = chats.find((c) => c.id === id)?.title;
        setChats((prev) => prev.map((c) => (c.id === id ? { ...c, title } : c)));
        try {
            await agentApi.renameChat(id, title);
        } catch (err) {
            setChats((prev) => prev.map((c) => (c.id === id ? { ...c, title: previous } : c)));
            toast.error(extractErrorMessage(err, 'Could not rename the chat'));
        }
    }, [chats, toast]);

    const deleteChat = useCallback(async (id) => {
        try {
            await agentApi.deleteChat(id);
            setChats((prev) => prev.filter((c) => c.id !== id));
            toast.success('Chat deleted');
            return true;
        } catch (err) {
            toast.error(extractErrorMessage(err, 'Could not delete the chat'));
            return false;
        }
    }, [toast]);

    return {
        chats, loading, loadingMore, error,
        hasMore: page < totalPages,
        loadMore, createChat, renameChat, deleteChat,
        refresh: fetchFirstPage,
        refreshSilently: () => fetchFirstPage({ silent: true }),
    };
};

/* ----------------------------------------------------------- conversation */

// One chat's messages + the live streaming turn.
//   history — real messages from the server, oldest first
//   live    — the optimistic user/assistant pair(s) for the current session;
//             replaced by server truth once a run succeeds
export const useChatConversation = (chatId, { onRunFinished } = {}) => {
    const toast = useToast();
    const [history, setHistory] = useState([]);
    const [live, setLive] = useState([]);
    const [loadingHistory, setLoadingHistory] = useState(false);
    const [historyError, setHistoryError] = useState(null);
    const [loadingEarlier, setLoadingEarlier] = useState(false);
    const [running, setRunning] = useState(false);
    const [pagesLoaded, setPagesLoaded] = useState(0);
    const [totalPages, setTotalPages] = useState(1);

    const chatIdRef = useRef(chatId);
    const runningRef = useRef(false);
    const abortRef = useRef(null);
    const tokenBuffer = useRef('');
    const rafRef = useRef(null);
    const onRunFinishedRef = useRef(onRunFinished);
    onRunFinishedRef.current = onRunFinished;

    // Load (or reset) when the selected chat changes.
    useEffect(() => {
        chatIdRef.current = chatId;
        abortRef.current?.abort();
        if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
        tokenBuffer.current = '';
        runningRef.current = false;
        setRunning(false);
        setHistory([]);
        setLive([]);
        setHistoryError(null);
        setPagesLoaded(0);
        setTotalPages(1);
        if (!chatId) {
            setLoadingHistory(false);
            return undefined;
        }

        let cancelled = false;
        setLoadingHistory(true);
        agentApi.getMessages(chatId, { page: 1, page_size: PAGE_SIZE })
            .then((res) => {
                if (cancelled) return;
                setHistory(res.results.map(toMessage).reverse());
                setPagesLoaded(1);
                setTotalPages(res.total_pages);
            })
            .catch((err) => {
                if (!cancelled) setHistoryError(extractErrorMessage(err, 'Could not load this conversation'));
            })
            .finally(() => {
                if (!cancelled) setLoadingHistory(false);
            });
        return () => {
            cancelled = true;
            abortRef.current?.abort();
        };
    }, [chatId]);

    const loadEarlier = useCallback(async () => {
        if (!chatId || loadingEarlier || pagesLoaded >= totalPages) return;
        setLoadingEarlier(true);
        try {
            const res = await agentApi.getMessages(chatId, { page: pagesLoaded + 1, page_size: PAGE_SIZE });
            if (chatIdRef.current !== chatId) return;
            setHistory((prev) => mergeMessagesAsc(prev, res.results.map(toMessage)));
            setPagesLoaded(pagesLoaded + 1);
            setTotalPages(res.total_pages);
        } catch (err) {
            toast.error(extractErrorMessage(err, 'Could not load earlier messages'));
        } finally {
            setLoadingEarlier(false);
        }
    }, [chatId, loadingEarlier, pagesLoaded, totalPages, toast]);

    // Replace the optimistic turn with what the server actually stored.
    const syncLatest = useCallback(async (forChatId) => {
        try {
            const res = await agentApi.getMessages(forChatId, { page: 1, page_size: PAGE_SIZE });
            if (chatIdRef.current !== forChatId) return;
            setHistory((prev) => mergeMessagesAsc(prev, res.results.map(toMessage)));
            setTotalPages(res.total_pages);
            setLive([]);
        } catch {
            // Keep showing the live turn; the next successful sync replaces it.
        }
    }, []);

    const send = useCallback(async (text) => {
        const content = (text || '').trim();
        if (!chatId || !content || runningRef.current) return false;

        runningRef.current = true;
        setRunning(true);
        const stamp = Date.now();
        const botId = `a-${stamp}`;
        setLive((prev) => [
            ...prev,
            { id: `u-${stamp}`, role: 'user', text: content },
            { id: botId, role: 'assistant', text: '', steps: [], status: 'streaming' },
        ]);

        const patchBot = (fn) => setLive((prev) => prev.map((m) => (m.id === botId ? fn(m) : m)));
        const flush = () => {
            rafRef.current = null;
            const chunk = tokenBuffer.current;
            if (!chunk) return;
            tokenBuffer.current = '';
            patchBot((m) => ({ ...m, text: m.text + chunk }));
        };
        const flushNow = () => {
            if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
            flush();
        };
        const pushToken = (chunk) => {
            tokenBuffer.current += chunk;
            if (rafRef.current == null) rafRef.current = requestAnimationFrame(flush);
        };

        const controller = new AbortController();
        abortRef.current = controller;
        let succeeded = false;
        try {
            const { run_id: runId } = await agentApi.sendMessage(chatId, content);
            await streamRun({
                runId,
                signal: controller.signal,
                onEvent: (type, data) => {
                    if (type === 'step') {
                        patchBot((m) => ({ ...m, steps: [...m.steps, { id: data.call_id, label: data.label, done: false }] }));
                    } else if (type === 'step_done') {
                        patchBot((m) => ({ ...m, steps: m.steps.map((s) => (s.id === data.call_id ? { ...s, done: true } : s)) }));
                    } else if (type === 'token') {
                        pushToken(data.text);
                    } else if (type === 'reset') {
                        // The model's answer was cut off mid-stream and the server is
                        // starting over: throw away the half-answer (and any tokens
                        // still buffered for it) so the retry streams into a clean bubble.
                        if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
                        rafRef.current = null;
                        tokenBuffer.current = '';
                        patchBot((m) => ({ ...m, text: '', steps: [] }));
                    } else if (type === 'done') {
                        flushNow();
                        patchBot((m) => ({ ...m, text: data.text || m.text, status: 'done' }));
                        succeeded = true;
                    } else if (type === 'error') {
                        flushNow();
                        patchBot((m) => ({ ...m, status: 'error', error: data.message }));
                    }
                },
            });
        } catch (err) {
            if (controller.signal.aborted) return false;   // user switched chats
            flushNow();
            const message = extractErrorMessage(err, 'Could not reach the assistant.');
            patchBot((m) => ({ ...m, status: 'error', error: message }));
            toast.error(message);
        } finally {
            if (chatIdRef.current === chatId) {
                runningRef.current = false;
                setRunning(false);
            }
        }

        onRunFinishedRef.current?.();
        if (succeeded) await syncLatest(chatId);
        return succeeded;
    }, [chatId, syncLatest, toast]);

    return {
        messages: [...history, ...live],
        historyCount: history.length,
        loadingHistory, historyError, running,
        hasEarlier: pagesLoaded > 0 && pagesLoaded < totalPages,
        loadingEarlier, loadEarlier, send,
    };
};
