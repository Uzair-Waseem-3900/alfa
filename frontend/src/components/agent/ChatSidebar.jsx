import { useEffect, useMemo, useRef, useState } from 'react';
import PropTypes from 'prop-types';
import { AnimatePresence, motion } from 'framer-motion';
import { differenceInCalendarDays, isToday, isYesterday } from 'date-fns';
import { Check, Loader2, MessageSquare, MoreHorizontal, Pencil, Plus, Trash2, X } from 'lucide-react';
import ConfirmDialog from '../ui/ConfirmDialog';
import InlineAlert from '../ui/InlineAlert';

const GROUP_ORDER = ['Today', 'Yesterday', 'Previous 7 days', 'Older'];

const groupLabel = (isoDate) => {
    const d = new Date(isoDate);
    if (isToday(d)) return 'Today';
    if (isYesterday(d)) return 'Yesterday';
    return differenceInCalendarDays(new Date(), d) <= 7 ? 'Previous 7 days' : 'Older';
};

// ─── animation variants ────────────────────────────────────────────────────

// Mobile: slides in/out from left
const mobileVariants = {
    open:   { x: 0,      transition: { type: 'spring', stiffness: 320, damping: 30 } },
    closed: { x: '-100%', transition: { type: 'spring', stiffness: 320, damping: 32 } },
};

const listContainer = {
    hidden: {},
    show: { transition: { staggerChildren: 0.045 } },
};

const listItem = {
    hidden: { opacity: 0, x: -14 },
    show:   { opacity: 1, x: 0, transition: { type: 'spring', stiffness: 380, damping: 28 } },
};

const dropdownVariants = {
    hidden: { opacity: 0, scale: 0.88, y: -6 },
    show:   { opacity: 1, scale: 1,    y: 0,  transition: { type: 'spring', stiffness: 420, damping: 26 } },
    exit:   { opacity: 0, scale: 0.88, y: -6, transition: { duration: 0.14, ease: 'easeIn' } },
};

// ─── ChatItem ──────────────────────────────────────────────────────────────

const ChatItem = ({ chat, active, onSelect, onRename, onAskDelete }) => {
    const [menuOpen, setMenuOpen] = useState(false);
    const [editing, setEditing]   = useState(false);
    const [draft, setDraft]       = useState(chat.title);
    const menuRef = useRef(null);

    useEffect(() => {
        if (!menuOpen) return undefined;
        const close = (e) => { if (!menuRef.current?.contains(e.target)) setMenuOpen(false); };
        const onKey  = (e) => { if (e.key === 'Escape') setMenuOpen(false); };
        document.addEventListener('mousedown', close);
        document.addEventListener('keydown',   onKey);
        return () => {
            document.removeEventListener('mousedown', close);
            document.removeEventListener('keydown',   onKey);
        };
    }, [menuOpen]);

    const commitRename = () => {
        const title = draft.trim();
        setEditing(false);
        if (title && title !== chat.title) onRename(chat.id, title);
    };

    if (editing) {
        return (
            <motion.div
                initial={{ opacity: 0, scale: 0.97 }}
                animate={{ opacity: 1, scale: 1 }}
                className="flex items-center gap-1 rounded-lg bg-white border border-accent-500 px-2 py-1"
            >
                <input
                    autoFocus
                    value={draft}
                    maxLength={120}
                    aria-label="Chat name"
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === 'Enter')  commitRename();
                        if (e.key === 'Escape') setEditing(false);
                    }}
                    className="flex-1 min-w-0 bg-transparent py-1.5 text-base sm:text-sm text-neutral-900 focus:outline-none"
                />
                <motion.button whileTap={{ scale: 0.88 }} type="button" onClick={commitRename} aria-label="Save name"
                    className="w-9 h-9 flex items-center justify-center rounded-md text-success-700 hover:bg-success-50 cursor-pointer">
                    <Check className="w-4 h-4" />
                </motion.button>
                <motion.button whileTap={{ scale: 0.88 }} type="button" onClick={() => setEditing(false)} aria-label="Cancel rename"
                    className="w-9 h-9 flex items-center justify-center rounded-md text-neutral-500 hover:bg-neutral-100 cursor-pointer">
                    <X className="w-4 h-4" />
                </motion.button>
            </motion.div>
        );
    }

    return (
        <motion.div
            variants={listItem}
            layout
            className={`group relative flex items-center rounded-lg transition-colors ${active ? 'bg-primary-100/70' : 'hover:bg-neutral-100'}`}
        >
            {/* Animated active bar */}
            <AnimatePresence>
                {active && (
                    <motion.span
                        layoutId="active-chat-bar"
                        initial={{ scaleY: 0, opacity: 0 }}
                        animate={{ scaleY: 1, opacity: 1 }}
                        exit={{    scaleY: 0, opacity: 0 }}
                        transition={{ type: 'spring', stiffness: 500, damping: 32 }}
                        className="absolute left-0 inset-y-2 w-[3px] rounded-full bg-primary-600"
                        aria-hidden="true"
                    />
                )}
            </AnimatePresence>

            <motion.button
                whileTap={{ scale: 0.97 }}
                type="button"
                onClick={() => onSelect(chat.id)}
                aria-current={active ? 'page' : undefined}
                className="flex-1 min-w-0 flex items-center gap-2.5 px-3 min-h-[44px] text-left cursor-pointer rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500"
            >
                <MessageSquare className={`w-4 h-4 flex-shrink-0 ${active ? 'text-primary-700' : 'text-neutral-400'}`} aria-hidden="true" />
                <span className={`truncate text-sm ${active ? 'font-semibold text-primary-900' : 'text-neutral-700'}`}>{chat.title}</span>
            </motion.button>

            <div ref={menuRef} className="relative">
                <motion.button
                    whileTap={{ scale: 0.88, rotate: 90 }}
                    transition={{ type: 'spring', stiffness: 500, damping: 20 }}
                    type="button"
                    aria-label={`Options for ${chat.title}`}
                    aria-haspopup="menu"
                    aria-expanded={menuOpen}
                    onClick={() => setMenuOpen((o) => !o)}
                    className={`w-11 h-11 flex items-center justify-center rounded-lg text-neutral-500 hover:bg-neutral-200/70 cursor-pointer transition-opacity md:opacity-0 md:group-hover:opacity-100 md:focus-visible:opacity-100 ${menuOpen ? 'md:!opacity-100' : ''}`}
                >
                    <MoreHorizontal className="w-5 h-5" />
                </motion.button>

                <AnimatePresence>
                    {menuOpen && (
                        <motion.div
                            role="menu"
                            variants={dropdownVariants}
                            initial="hidden"
                            animate="show"
                            exit="exit"
                            className="absolute right-0 top-11 z-20 w-40 rounded-xl border border-neutral-200 bg-white p-1 shadow-dropdown"
                        >
                            <motion.button whileTap={{ scale: 0.96 }} type="button" role="menuitem"
                                onClick={() => { setMenuOpen(false); setDraft(chat.title); setEditing(true); }}
                                className="flex w-full items-center gap-2 rounded-lg px-3 min-h-[44px] text-sm text-neutral-700 hover:bg-neutral-100 cursor-pointer">
                                <Pencil className="w-4 h-4" /> Rename
                            </motion.button>
                            <motion.button whileTap={{ scale: 0.96 }} type="button" role="menuitem"
                                onClick={() => { setMenuOpen(false); onAskDelete(chat); }}
                                className="flex w-full items-center gap-2 rounded-lg px-3 min-h-[44px] text-sm text-error-600 hover:bg-error-50 cursor-pointer">
                                <Trash2 className="w-4 h-4" /> Delete
                            </motion.button>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>
        </motion.div>
    );
};

ChatItem.propTypes = {
    chat: PropTypes.shape({ id: PropTypes.string.isRequired, title: PropTypes.string.isRequired }).isRequired,
    active: PropTypes.bool,
    onSelect:    PropTypes.func.isRequired,
    onRename:    PropTypes.func.isRequired,
    onAskDelete: PropTypes.func.isRequired,
};

// ─── ChatSidebar ───────────────────────────────────────────────────────────

const ChatSidebar = ({
    open, onClose, chats, loading, error, onRetry, activeId, hasMore, loadingMore, onLoadMore,
    onNewChat, onSelect, onRename, onDelete,
}) => {
    const [toDelete, setToDelete] = useState(null);
    const [deleting, setDeleting] = useState(false);

    const groups = useMemo(() => {
        const map = new Map();
        chats.forEach((c) => {
            const label = groupLabel(c.updated_at);
            if (!map.has(label)) map.set(label, []);
            map.get(label).push(c);
        });
        return GROUP_ORDER.filter((l) => map.has(l)).map((l) => ({ label: l, items: map.get(l) }));
    }, [chats]);

    const confirmDelete = async () => {
        setDeleting(true);
        const ok = await onDelete(toDelete.id);
        setDeleting(false);
        if (ok) setToDelete(null);
    };

    const sidebarContent = (
        <>
            {/* New chat + close (mobile) */}
            <div className="flex items-center gap-2 p-3">
                <motion.button
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.96 }}
                    transition={{ type: 'spring', stiffness: 500, damping: 22 }}
                    type="button"
                    onClick={onNewChat}
                    className="flex-1 flex items-center justify-center gap-2 rounded-xl border border-neutral-300 bg-white px-4 min-h-[44px] text-sm font-semibold text-neutral-800 hover:bg-neutral-50 hover:border-neutral-400 shadow-sm cursor-pointer transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500"
                >
                    <motion.span
                        whileTap={{ rotate: 90 }}
                        transition={{ type: 'spring', stiffness: 600, damping: 18 }}
                        className="inline-flex"
                    >
                        <Plus className="w-4 h-4" />
                    </motion.span>
                    New chat
                </motion.button>

                <motion.button
                    whileTap={{ scale: 0.9 }}
                    type="button" onClick={onClose} aria-label="Close chat history"
                    className="md:hidden w-11 h-11 flex items-center justify-center rounded-xl text-neutral-500 hover:bg-neutral-100 cursor-pointer"
                >
                    <X className="w-5 h-5" />
                </motion.button>
            </div>

            {/* Chat list */}
            <nav className="flex-1 overflow-y-auto overscroll-contain px-2 pb-4">
                {loading ? (
                    <div className="space-y-2 px-1 pt-2" aria-hidden="true">
                        {[70, 55, 80, 50, 65].map((w, i) => (
                            <motion.div
                                key={i}
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                transition={{ delay: i * 0.06 }}
                                className="h-9 rounded-lg bg-neutral-200/70 animate-pulse motion-reduce:animate-none"
                                style={{ width: `${w}%` }}
                            />
                        ))}
                    </div>
                ) : error ? (
                    <InlineAlert message={error} onRetry={onRetry} className="mx-1" />
                ) : chats.length === 0 ? (
                    <motion.div
                        initial={{ opacity: 0, y: 12 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.1 }}
                        className="px-4 py-10 text-center"
                    >
                        <MessageSquare className="w-8 h-8 mx-auto text-neutral-300" aria-hidden="true" />
                        <p className="mt-3 text-sm font-medium text-neutral-700">No conversations yet</p>
                        <p className="mt-1 text-xs text-neutral-500">Start a new chat and ask about your business.</p>
                    </motion.div>
                ) : (
                    <>
                        {groups.map(({ label, items }) => (
                            <section key={label} className="mb-3">
                                <h3 className="px-3 pt-2 pb-1 text-xs font-semibold uppercase tracking-wide text-neutral-500">{label}</h3>
                                <motion.div
                                    className="space-y-0.5"
                                    variants={listContainer}
                                    initial="hidden"
                                    animate="show"
                                >
                                    {items.map((chat) => (
                                        <ChatItem
                                            key={chat.id}
                                            chat={chat}
                                            active={chat.id === activeId}
                                            onSelect={onSelect}
                                            onRename={onRename}
                                            onAskDelete={setToDelete}
                                        />
                                    ))}
                                </motion.div>
                            </section>
                        ))}
                        {hasMore && (
                            <motion.button
                                whileTap={{ scale: 0.97 }}
                                type="button" onClick={onLoadMore} disabled={loadingMore}
                                className="w-full flex items-center justify-center gap-2 rounded-lg min-h-[44px] text-sm font-medium text-primary-700 hover:bg-neutral-100 cursor-pointer disabled:opacity-60"
                            >
                                {loadingMore && <Loader2 className="w-4 h-4 animate-spin motion-reduce:animate-none" />}
                                Show older chats
                            </motion.button>
                        )}
                    </>
                )}
            </nav>
        </>
    );

    return (
        <>
            {/* ── Mobile scrim ─────────────────────────────────────────────── */}
            <AnimatePresence>
                {open && (
                    <motion.div
                        key="scrim"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="fixed inset-0 z-30 bg-black/50 md:hidden"
                        onClick={onClose}
                        aria-hidden="true"
                    />
                )}
            </AnimatePresence>

            {/* ── Mobile drawer (position:fixed, slides over content) ───────── */}
            <motion.aside
                aria-label="Chat history"
                variants={mobileVariants}
                animate={open ? 'open' : 'closed'}
                className="md:hidden fixed inset-y-0 left-0 z-40 w-[85vw] max-w-xs flex flex-col bg-neutral-50 border-r border-neutral-200"
            >
                {sidebarContent}
            </motion.aside>

            {/* ── Desktop sidebar (in-flow, animates width) ─────────────────── */}
            <motion.aside
                aria-label="Chat history"
                aria-hidden={!open}
                // Animate width so the content area smoothly gains/loses space
                animate={{
                    width: open ? 288 : 0,         // 288px = w-72
                    opacity: open ? 1 : 0,
                }}
                transition={{ type: 'spring', stiffness: 300, damping: 32 }}
                className="hidden md:flex flex-col bg-neutral-50 border-r border-neutral-200 overflow-hidden flex-shrink-0"
            >
                {/* Inner wrapper keeps content at full 288px so text doesn't reflow during collapse */}
                <div className="w-72 flex flex-col h-full">
                    {sidebarContent}
                </div>
            </motion.aside>

            <ConfirmDialog
                isOpen={!!toDelete}
                onClose={() => !deleting && setToDelete(null)}
                onConfirm={confirmDelete}
                title="Delete this chat?"
                message={toDelete ? `"${toDelete.title}" and its messages will be removed from your history.` : ''}
                confirmText="Delete"
                loading={deleting}
            />
        </>
    );
};

ChatSidebar.propTypes = {
    open:         PropTypes.bool.isRequired,
    onClose:      PropTypes.func.isRequired,
    chats:        PropTypes.array.isRequired,
    loading:      PropTypes.bool,
    error:        PropTypes.string,
    onRetry:      PropTypes.func,
    activeId:     PropTypes.string,
    hasMore:      PropTypes.bool,
    loadingMore:  PropTypes.bool,
    onLoadMore:   PropTypes.func.isRequired,
    onNewChat:    PropTypes.func.isRequired,
    onSelect:     PropTypes.func.isRequired,
    onRename:     PropTypes.func.isRequired,
    onDelete:     PropTypes.func.isRequired,
};

export default ChatSidebar;
