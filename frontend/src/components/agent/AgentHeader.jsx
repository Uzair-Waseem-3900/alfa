import PropTypes from 'prop-types';
import { AnimatePresence, motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowLeft, PanelLeft, ReceiptText, SquarePen } from 'lucide-react';
import AgentIcon from './AgentIcon';
import { AssistantAvatar } from './MessageBubble';

// ─── variants ──────────────────────────────────────────────────────────────

const headerEntrance = {
    hidden: { opacity: 0, y: -10 },
    show: {
        opacity: 1, y: 0,
        transition: { type: 'spring', stiffness: 340, damping: 28, staggerChildren: 0.06 },
    },
};

const itemFade = {
    hidden: { opacity: 0, y: -6 },
    show:   { opacity: 1, y: 0, transition: { type: 'spring', stiffness: 380, damping: 26 } },
};

// ─── Assistant | Bulk switch ───────────────────────────────────────────────
// The two pages are separate routes, so the header is rebuilt on every switch. The highlight therefore starts
// where it was on the PREVIOUS page (module memory) and springs to its new slot: it reads as one control sliding.
let lastMode = null;
const TABS = [
    { key: 'assistant', to: '/agent',      label: 'Assistant',     icon: AgentIcon,    title: 'Ask the assistant about your business' },
    { key: 'bulk',      to: '/agent/bulk', label: 'Bulk invoices', icon: ReceiptText, title: 'Create many invoices at once' },
];

const ModeSwitch = ({ mode }) => {
    const from = lastMode && lastMode !== mode ? (lastMode === 'bulk' ? '100%' : '0%') : (mode === 'bulk' ? '100%' : '0%');
    lastMode = mode;
    return (
        <nav aria-label="Assistant mode" className="relative grid grid-cols-2 rounded-xl bg-neutral-100 p-0.5">
            <motion.span
                aria-hidden="true"
                className="absolute inset-y-0.5 left-0.5 w-[calc(50%-2px)] rounded-[10px] bg-white shadow-sm ring-1 ring-neutral-200"
                initial={{ x: from }}
                animate={{ x: mode === 'bulk' ? '100%' : '0%' }}
                transition={{ type: 'spring', stiffness: 380, damping: 30 }}
            />
            {TABS.map(({ key, to, label, icon: Icon, title }) => (
                <Link key={key} to={to} title={title} aria-current={key === mode ? 'page' : undefined}
                    aria-label={`Switch to ${label}`}
                    className={`relative z-10 inline-flex items-center justify-center gap-1.5 rounded-[10px] px-2.5 sm:px-3 min-h-[40px] text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 ${
                        key === mode ? 'text-primary-800' : 'text-neutral-500 hover:text-neutral-800'}`}>
                    <Icon className="w-4 h-4" aria-hidden="true" />
                    <span className="hidden sm:inline">{label}</span>
                </Link>
            ))}
        </nav>
    );
};

ModeSwitch.propTypes = { mode: PropTypes.oneOf(['assistant', 'bulk']).isRequired };

// ─── AgentHeader ───────────────────────────────────────────────────────────

const AgentHeader = ({
    assistantName, sidebarOpen, onToggleSidebar, onNewChat,
    subtitle = 'Business assistant', busy = false, newLabel = 'New chat', actions = null, mode = null,
}) => (
    <motion.header
        className="flex-shrink-0 h-14 flex items-center gap-1 sm:gap-2 px-2 sm:px-4 border-b border-neutral-200 bg-white/90 backdrop-blur"
        variants={headerEntrance}
        initial="hidden"
        animate="show"
    >
        {/* ── Sidebar toggle ─────────────────────────────────────────────── */}
        <motion.div variants={itemFade}>
            <motion.button
                type="button"
                onClick={onToggleSidebar}
                aria-label={sidebarOpen ? 'Hide chat history' : 'Show chat history'}
                aria-expanded={sidebarOpen}
                whileHover={{ backgroundColor: 'rgba(0,0,0,0.05)' }}
                whileTap={{ scale: 0.88 }}
                transition={{ type: 'spring', stiffness: 500, damping: 22 }}
                className="w-11 h-11 flex items-center justify-center rounded-lg text-neutral-600 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500"
            >
                {/* Icon rotates 180° when sidebar is closed so it always "points" toward the panel */}
                <motion.span
                    animate={{ rotate: sidebarOpen ? 0 : 180 }}
                    transition={{ type: 'spring', stiffness: 320, damping: 24 }}
                    className="inline-flex"
                >
                    <PanelLeft className="w-5 h-5" />
                </motion.span>
            </motion.button>
        </motion.div>

        {/* ── Assistant identity ─────────────────────────────────────────── */}
        <motion.div
            variants={itemFade}
            className="flex items-center gap-2.5 min-w-0"
        >
            <AssistantAvatar active={busy} />
            <div className="min-w-0 leading-tight">
                <h1 className="text-sm font-semibold text-neutral-900 truncate">{assistantName}</h1>
                <p className="hidden sm:block text-xs text-neutral-500">{subtitle}</p>
            </div>
        </motion.div>

        {/* ── Status dot — pulses while thinking ─────────────────────────── */}
        <AnimatePresence>
            <motion.span
                key="status-dot"
                className={`hidden sm:block w-2 h-2 rounded-full transition-colors duration-300 ${busy ? 'bg-accent-500' : 'bg-success-400'}`}
                animate={busy ? { scale: [1, 1.8, 1], opacity: [0.8, 1, 0.8] } : { scale: [1, 1.4, 1], opacity: [0.7, 1, 0.7] }}
                transition={{ duration: busy ? 0.9 : 2.4, repeat: Infinity, ease: 'easeInOut' }}
                aria-hidden="true"
            />
        </AnimatePresence>

        <div className="flex-1" />

        {/* ── New chat (mobile only) ─────────────────────────────────────── */}
        <motion.div variants={itemFade}>
            <motion.button
                type="button"
                onClick={onNewChat}
                aria-label={newLabel}
                whileHover={{ backgroundColor: 'rgba(0,0,0,0.05)' }}
                whileTap={{ scale: 0.88, rotate: 15 }}
                transition={{ type: 'spring', stiffness: 500, damping: 20 }}
                className="md:hidden w-11 h-11 flex items-center justify-center rounded-lg text-neutral-600 cursor-pointer"
            >
                <SquarePen className="w-5 h-5" />
            </motion.button>
        </motion.div>

        {mode && <motion.div variants={itemFade}><ModeSwitch mode={mode} /></motion.div>}

        {actions}

        {/* ── Back to software ──────────────────────────────────────────── */}
        <motion.div variants={itemFade}>
            <motion.div
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.96 }}
                transition={{ type: 'spring', stiffness: 500, damping: 22 }}
            >
                <Link
                    to="/dashboard"
                    className="inline-flex items-center gap-1.5 rounded-lg border border-primary-200 bg-primary-50 px-3 min-h-[44px] text-sm font-medium text-primary-700 hover:bg-primary-100 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500"
                >
                    <motion.span
                        animate={{ x: 0 }}
                        whileHover={{ x: -3 }}
                        transition={{ type: 'spring', stiffness: 500, damping: 20 }}
                        className="inline-flex"
                    >
                        <ArrowLeft className="w-4 h-4" aria-hidden="true" />
                    </motion.span>
                    <span className="sm:hidden">Back</span>
                    <span className="hidden sm:inline">Back to software</span>
                </Link>
            </motion.div>
        </motion.div>
    </motion.header>
);

AgentHeader.propTypes = {
    assistantName:   PropTypes.string.isRequired,
    sidebarOpen:     PropTypes.bool.isRequired,
    onToggleSidebar: PropTypes.func.isRequired,
    onNewChat:       PropTypes.func.isRequired,
    subtitle:        PropTypes.string,
    newLabel:        PropTypes.string,
    actions:         PropTypes.node,
    busy:            PropTypes.bool,
    mode:            PropTypes.oneOf(['assistant', 'bulk']),
};

export default AgentHeader;
