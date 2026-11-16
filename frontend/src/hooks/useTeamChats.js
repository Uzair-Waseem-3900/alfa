import { useState, useEffect, useCallback } from 'react';
import { teamApi } from '../services/agentApi';
import { extractErrorMessage } from '../utils/errorMessage';

const PAGE_SIZE = 25;

// Generic "newest first, load more" list for a paginated team endpoint.
// `fetchPage(page)` is null while there is nothing to load (no user selected yet).
export const usePagedList = (fetchPage, key, errorText) => {
    const [items, setItems] = useState([]);
    const [page, setPage] = useState(0);
    const [totalPages, setTotalPages] = useState(1);
    const [loading, setLoading] = useState(false);
    const [loadingMore, setLoadingMore] = useState(false);
    const [error, setError] = useState(null);
    const [version, setVersion] = useState(0);

    useEffect(() => {
        setItems([]); setPage(0); setTotalPages(1); setError(null);
        if (!fetchPage) { setLoading(false); return undefined; }
        let cancelled = false;
        setLoading(true);
        fetchPage(1)
            .then((res) => {
                if (cancelled) return;
                setItems(res.results);
                setPage(1);
                setTotalPages(res.total_pages);
            })
            .catch((err) => { if (!cancelled) setError(extractErrorMessage(err, errorText)); })
            .finally(() => { if (!cancelled) setLoading(false); });
        return () => { cancelled = true; };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [key, version]);

    const loadMore = useCallback(async () => {
        if (!fetchPage || loadingMore || page >= totalPages) return;
        setLoadingMore(true);
        try {
            const res = await fetchPage(page + 1);
            setItems((prev) => [...prev, ...res.results]);
            setPage(page + 1);
            setTotalPages(res.total_pages);
        } catch (err) {
            setError(extractErrorMessage(err, errorText));
        } finally {
            setLoadingMore(false);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [key, loadingMore, page, totalPages]);

    const refresh = useCallback(() => setVersion((v) => v + 1), []);
    return { items, loading, loadingMore, error, hasMore: page > 0 && page < totalPages, loadMore, refresh };
};

export const useTeamOwners = () =>
    usePagedList((p) => teamApi.listOwners({ page: p, page_size: PAGE_SIZE }), 'owners', 'Could not load users');

export const useOwnerChats = (email) =>
    usePagedList(
        email ? (p) => teamApi.listChats(email, { page: p, page_size: PAGE_SIZE }) : null,
        email || '', 'Could not load chats',
    );

const toMessage = (m) => ({ id: m.id, role: m.role, text: m.text });

// One chat's messages, read only. Pages are newest first; shown oldest first.
export const useTeamConversation = (chatId) => {
    const [messages, setMessages] = useState([]);
    const [owner, setOwner] = useState(null);
    const [page, setPage] = useState(0);
    const [totalPages, setTotalPages] = useState(1);
    const [loading, setLoading] = useState(false);
    const [loadingEarlier, setLoadingEarlier] = useState(false);
    const [error, setError] = useState(null);

    useEffect(() => {
        setMessages([]); setOwner(null); setPage(0); setTotalPages(1); setError(null);
        if (!chatId) { setLoading(false); return undefined; }
        let cancelled = false;
        setLoading(true);
        Promise.all([teamApi.getChat(chatId), teamApi.getMessages(chatId, { page: 1, page_size: PAGE_SIZE })])
            .then(([chat, res]) => {
                if (cancelled) return;
                setOwner({ email: chat.owner_email, name: chat.owner_name, title: chat.title });
                setMessages(res.results.map(toMessage).reverse());
                setPage(1);
                setTotalPages(res.total_pages);
            })
            .catch((err) => { if (!cancelled) setError(extractErrorMessage(err, 'Could not load this conversation')); })
            .finally(() => { if (!cancelled) setLoading(false); });
        return () => { cancelled = true; };
    }, [chatId]);

    const loadEarlier = useCallback(async () => {
        if (!chatId || loadingEarlier || page >= totalPages) return;
        setLoadingEarlier(true);
        try {
            const res = await teamApi.getMessages(chatId, { page: page + 1, page_size: PAGE_SIZE });
            setMessages((prev) => {
                const byId = new Map();
                [...res.results.map(toMessage), ...prev].forEach((m) => byId.set(m.id, m));
                return [...byId.values()].sort((a, b) => a.id - b.id);
            });
            setPage(page + 1);
            setTotalPages(res.total_pages);
        } catch (err) {
            setError(extractErrorMessage(err, 'Could not load earlier messages'));
        } finally {
            setLoadingEarlier(false);
        }
    }, [chatId, loadingEarlier, page, totalPages]);

    return { messages, owner, loading, error, hasEarlier: page > 0 && page < totalPages, loadingEarlier, loadEarlier };
};
