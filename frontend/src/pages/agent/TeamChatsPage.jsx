import { Link, Navigate, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, ChevronRight, Eye, Loader2, MessageSquare, User } from 'lucide-react';
import { format } from 'date-fns';
import { useAuth } from '../../context/AuthContext';
import { useOwnerChats, useTeamConversation, useTeamOwners } from '../../hooks/useTeamChats';
import MessageList from '../../components/agent/MessageList';
import InlineAlert from '../../components/ui/InlineAlert';

const ASSISTANT_NAME = import.meta.env.VITE_AGENT_NAME || 'Assistant';
const when = (iso) => format(new Date(iso), 'd MMM yyyy, h:mm a');

const LoadMore = ({ onClick, busy }) => (
    <button type="button" onClick={onClick} disabled={busy}
        className="agent-press w-full flex items-center justify-center gap-2 rounded-lg min-h-[44px] text-sm font-medium text-primary-700 hover:bg-neutral-100 cursor-pointer disabled:opacity-60">
        {busy && <Loader2 className="w-4 h-4 animate-spin motion-reduce:animate-none" />}
        Show more
    </button>
);

const Skeleton = () => (
    <div className="space-y-2 p-3" aria-hidden="true">
        {[70, 55, 80, 50].map((w, i) => (
            <div key={i} className="h-11 rounded-lg bg-neutral-200/70 animate-pulse motion-reduce:animate-none" style={{ width: `${w}%` }} />
        ))}
    </div>
);

const Row = ({ onClick, active, icon: Icon, title, subtitle, trailing }) => (
    <button type="button" onClick={onClick} aria-current={active ? 'page' : undefined}
        className={`agent-press w-full flex items-center gap-3 px-3 min-h-[56px] text-left rounded-lg cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 ${active ? 'bg-primary-100/70' : 'hover:bg-neutral-100'}`}>
        <Icon className="w-5 h-5 flex-shrink-0 text-neutral-400" aria-hidden="true" />
        <span className="flex-1 min-w-0">
            <span className="block truncate text-sm font-medium text-neutral-800">{title}</span>
            <span className="block truncate text-xs text-neutral-500">{subtitle}</span>
        </span>
        {trailing}
    </button>
);

// Superuser-only, READ-ONLY view of everyone's assistant chats.
//   /agent/team                  -> list of users
//   /agent/team/:email           -> that user's chats
//   /agent/team/:email/:chatId   -> the conversation (no composer)
const TeamChatsPage = () => {
    const { user } = useAuth();
    const { email, chatId } = useParams();
    const navigate = useNavigate();

    const owners = useTeamOwners();
    const chats = useOwnerChats(email);
    const convo = useTeamConversation(chatId);

    if (user && user.role !== 'superuser') return <Navigate to="/agent" replace />;

    const ownerName = owners.items.find((o) => o.email === email)?.name || convo.owner?.name || email;
    const goUser = (e) => navigate(`/agent/team/${encodeURIComponent(e)}`);
    const goChat = (id) => navigate(`/agent/team/${encodeURIComponent(email)}/${id}`);

    const back = chatId ? `/agent/team/${encodeURIComponent(email)}` : email ? '/agent/team' : '/agent';
    const backLabel = chatId ? 'Chats' : email ? 'All users' : 'Assistant';

    const panel = email ? chats : owners;

    return (
        <div className="flex h-dvh overflow-hidden bg-white">
            {/* ── list panel (hidden on mobile while a chat is open) ───────── */}
            <aside className={`${chatId ? 'hidden md:flex' : 'flex'} w-full md:w-80 flex-shrink-0 flex-col border-r border-neutral-200 bg-neutral-50`}>
                <header className="flex-shrink-0 h-14 flex items-center gap-2 px-2 border-b border-neutral-200 bg-white">
                    <Link to={back} aria-label={`Back to ${backLabel}`}
                        className="agent-press inline-flex items-center gap-1.5 rounded-lg px-3 min-h-[44px] text-sm font-medium text-primary-700 hover:bg-primary-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500">
                        <ArrowLeft className="w-4 h-4" aria-hidden="true" /> {chatId ? 'All users' : backLabel}
                    </Link>
                    <h1 className="flex-1 min-w-0 truncate text-sm font-semibold text-neutral-900 text-right pr-2">
                        {email ? ownerName : 'Team chats'}
                    </h1>
                </header>

                <nav className="flex-1 overflow-y-auto overscroll-contain p-2">
                    {panel.loading ? <Skeleton /> : panel.error ? (
                        <InlineAlert message={panel.error} className="m-1" />
                    ) : panel.items.length === 0 ? (
                        <div className="px-4 py-10 text-center">
                            <MessageSquare className="w-8 h-8 mx-auto text-neutral-300" aria-hidden="true" />
                            <p className="mt-3 text-sm font-medium text-neutral-700">{email ? 'No chats yet' : 'Nobody has used the assistant yet'}</p>
                        </div>
                    ) : (
                        <div className="space-y-0.5">
                            {email ? panel.items.map((c) => (
                                <Row key={c.id} icon={MessageSquare} active={c.id === chatId} onClick={() => goChat(c.id)}
                                    title={c.title} subtitle={when(c.updated_at)} />
                            )) : panel.items.map((o) => (
                                <Row key={o.email} icon={User} onClick={() => goUser(o.email)}
                                    title={o.name} subtitle={`${o.email} · ${o.chat_count} chat${o.chat_count === 1 ? '' : 's'}`}
                                    trailing={<ChevronRight className="w-4 h-4 text-neutral-400" aria-hidden="true" />} />
                            ))}
                            {panel.hasMore && <LoadMore onClick={panel.loadMore} busy={panel.loadingMore} />}
                        </div>
                    )}
                </nav>
            </aside>

            {/* ── conversation (read only) ─────────────────────────────────── */}
            <section className={`${chatId ? 'flex' : 'hidden md:flex'} flex-1 min-w-0 flex-col`}>
                <header className="flex-shrink-0 h-14 flex items-center gap-2 px-2 sm:px-4 border-b border-neutral-200 bg-white">
                    <Link to={back} aria-label="Back" className="agent-press md:hidden w-11 h-11 flex items-center justify-center rounded-lg text-neutral-600 hover:bg-neutral-100">
                        <ArrowLeft className="w-5 h-5" />
                    </Link>
                    <div className="flex-1 min-w-0 leading-tight">
                        <p className="truncate text-sm font-semibold text-neutral-900">{convo.owner?.title || 'Team chats'}</p>
                        {convo.owner && <p className="truncate text-xs text-neutral-500">{convo.owner.name} · {convo.owner.email}</p>}
                    </div>
                    <Link to="/dashboard"
                        className="agent-press inline-flex items-center gap-1.5 rounded-lg border border-primary-200 bg-primary-50 px-3 min-h-[44px] text-sm font-medium text-primary-700 hover:bg-primary-100">
                        <span className="sm:hidden">Back</span><span className="hidden sm:inline">Back to software</span>
                    </Link>
                </header>

                {chatId ? (
                    <>
                        <MessageList
                            messages={convo.messages}
                            assistantName={ASSISTANT_NAME}
                            loadingHistory={convo.loading}
                            historyError={convo.error}
                            hasEarlier={convo.hasEarlier}
                            loadingEarlier={convo.loadingEarlier}
                            onLoadEarlier={convo.loadEarlier}
                            onRetryLast={() => {}}
                            resetKey={chatId}
                        />
                        <div className="flex-shrink-0 flex items-center justify-center gap-2 border-t border-neutral-200 bg-neutral-50 px-4 min-h-[56px] text-sm text-neutral-600">
                            <Eye className="w-4 h-4" aria-hidden="true" />
                            Read only{convo.owner ? ` — this is ${convo.owner.name}'s chat` : ''}
                        </div>
                    </>
                ) : (
                    <div className="flex-1 flex items-center justify-center px-6 text-center text-sm text-neutral-500">
                        {email ? 'Pick a chat to read it.' : 'Pick a user to see their chats.'}
                    </div>
                )}
            </section>
        </div>
    );
};

export default TeamChatsPage;
