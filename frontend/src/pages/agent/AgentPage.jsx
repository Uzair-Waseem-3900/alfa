import { useCallback, useEffect, useState } from 'react';
import { Navigate, useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useAgentChats, useChatConversation } from '../../hooks/useAgent';
import AgentHeader from '../../components/agent/AgentHeader';
import ChatSidebar from '../../components/agent/ChatSidebar';
import Composer from '../../components/agent/Composer';
import EmptyChat from '../../components/agent/EmptyChat';
import MessageList from '../../components/agent/MessageList';

const ASSISTANT_NAME = import.meta.env.VITE_ASSISTANT_NAME || 'Munshi';
const COMPANY_NAME = import.meta.env.VITE_APP_NAME || 'your business';
const MD_BREAKPOINT = 768;
const isMobile = () => window.innerWidth < MD_BREAKPOINT;

// Full-screen assistant. Deliberately NOT wrapped in the app <Layout>: it has
// its own chat-history sidebar and a "Back to software" button instead of the
// main navigation (the one exception to the "every route uses Layout" rule).
const AgentPage = () => {
    const { user } = useAuth();
    const { chatId } = useParams();
    const navigate = useNavigate();

    const chatList = useAgentChats();
    const convo = useChatConversation(chatId, { onRunFinished: chatList.refreshSilently });

    const [sidebarOpen, setSidebarOpen] = useState(() => !isMobile());
    const [creating, setCreating] = useState(false);
    // A first message typed with no chat selected: remembered while the chat is
    // created and routed to, then sent once that chat is the active one.
    const [pending, setPending] = useState(null);

    const send = convo.send;
    useEffect(() => {
        if (pending && pending.chatId === chatId) {
            setPending(null);
            send(pending.text);
        }
    }, [pending, chatId, send]);

    const closeOnMobile = () => { if (isMobile()) setSidebarOpen(false); };

    const handleNewChat = useCallback(() => {
        navigate('/agent');
        closeOnMobile();
    }, [navigate]);

    const handleSelect = (id) => {
        navigate(`/agent/${id}`);
        closeOnMobile();
    };

    const handleSend = async (text) => {
        if (chatId) {
            convo.send(text);
            return;
        }
        setCreating(true);
        const chat = await chatList.createChat();
        setCreating(false);
        if (!chat) return;
        setPending({ chatId: chat.id, text });
        navigate(`/agent/${chat.id}`, { replace: true });
    };

    const handleDelete = async (id) => {
        const ok = await chatList.deleteChat(id);
        if (ok && id === chatId) navigate('/agent', { replace: true });
        return ok;
    };

    // Same inline role check every admin page uses.
    if (user && user.role !== 'admin' && user.role !== 'superuser') {
        return <Navigate to="/dashboard" replace />;
    }

    const busy = convo.running || creating;

    return (
        <div className="flex h-dvh overflow-hidden bg-white">
            <ChatSidebar
                open={sidebarOpen}
                onClose={() => setSidebarOpen(false)}
                chats={chatList.chats}
                loading={chatList.loading}
                error={chatList.error}
                onRetry={chatList.refresh}
                activeId={chatId}
                hasMore={chatList.hasMore}
                loadingMore={chatList.loadingMore}
                onLoadMore={chatList.loadMore}
                onNewChat={handleNewChat}
                onSelect={handleSelect}
                onRename={chatList.renameChat}
                onDelete={handleDelete}
            />

            <div className="flex flex-1 min-w-0 flex-col">
                <AgentHeader
                    assistantName={ASSISTANT_NAME}
                    sidebarOpen={sidebarOpen}
                    onToggleSidebar={() => setSidebarOpen((o) => !o)}
                    onNewChat={handleNewChat}
                />

                <MessageList
                    messages={convo.messages}
                    assistantName={ASSISTANT_NAME}
                    loadingHistory={convo.loadingHistory}
                    historyError={convo.historyError}
                    hasEarlier={convo.hasEarlier}
                    loadingEarlier={convo.loadingEarlier}
                    onLoadEarlier={convo.loadEarlier}
                    onRetryLast={handleSend}
                    resetKey={chatId || 'new'}
                >
                    <EmptyChat
                        assistantName={ASSISTANT_NAME}
                        companyName={COMPANY_NAME}
                        onPick={handleSend}
                        disabled={busy}
                    />
                </MessageList>

                {/* Announces completion to screen readers without narrating every token. */}
                <p className="sr-only" role="status" aria-live="polite">
                    {convo.running ? `${ASSISTANT_NAME} is answering` : ''}
                </p>

                <Composer onSend={handleSend} busy={busy} assistantName={ASSISTANT_NAME} />
            </div>
        </div>
    );
};

export default AgentPage;
