import { useEffect, useRef, useState } from 'react';
import PropTypes from 'prop-types';
import { format } from 'date-fns';
import { AnimatePresence, motion } from 'framer-motion';
import { Check, MoreHorizontal, Pencil, Receipt, Trash2, X } from 'lucide-react';
import { defaultBatchLabel } from '../../utils/bulkBatch';

const when = (iso) => format(new Date(iso), 'd MMM, h:mm a');

// Same motion as the assistant's chat items (ChatSidebar), so both history lists feel identical.
const listItem = {
    hidden: { opacity: 0, x: -14 },
    show:   { opacity: 1, x: 0, transition: { type: 'spring', stiffness: 380, damping: 28 } },
};

const dropdownVariants = {
    hidden: { opacity: 0, scale: 0.88, y: -6 },
    show:   { opacity: 1, scale: 1,    y: 0,  transition: { type: 'spring', stiffness: 420, damping: 26 } },
    exit:   { opacity: 0, scale: 0.88, y: -6, transition: { duration: 0.14, ease: 'easeIn' } },
};

// One batch in the bulk-invoice history: open it, rename it, or delete it (same ⋯ menu as a chat in the assistant).
const BulkBatchItem = ({ batch, active, onSelect, onRename, onAskDelete }) => {
    const [menuOpen, setMenuOpen] = useState(false);
    const [editing, setEditing] = useState(false);
    const [draft, setDraft] = useState('');
    const [saving, setSaving] = useState(false);
    const menuRef = useRef(null);
    const label = batch.title || defaultBatchLabel(batch);

    useEffect(() => {
        if (!menuOpen) return undefined;
        const close = (e) => { if (!menuRef.current?.contains(e.target)) setMenuOpen(false); };
        const onKey = (e) => { if (e.key === 'Escape') setMenuOpen(false); };
        document.addEventListener('mousedown', close);
        document.addEventListener('keydown', onKey);
        return () => {
            document.removeEventListener('mousedown', close);
            document.removeEventListener('keydown', onKey);
        };
    }, [menuOpen]);

    const commitRename = async () => {
        if (saving) return;
        const title = draft.trim();
        if (!title || title === batch.title) { setEditing(false); return; }
        setSaving(true);
        const ok = await onRename(batch.id, title);
        setSaving(false);
        if (ok) setEditing(false);
    };

    if (editing) {
        return (
            <motion.li
                initial={{ opacity: 0, scale: 0.97 }}
                animate={{ opacity: 1, scale: 1 }}
                className="flex items-center gap-1 rounded-lg bg-white border border-accent-500 px-2 py-1"
            >
                <input
                    autoFocus
                    value={draft}
                    maxLength={120}
                    disabled={saving}
                    aria-label="Batch name"
                    placeholder={defaultBatchLabel(batch)}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === 'Enter') commitRename();
                        if (e.key === 'Escape') setEditing(false);
                    }}
                    className="flex-1 min-w-0 bg-transparent py-1.5 text-base sm:text-sm text-neutral-900 focus:outline-none"
                />
                <motion.button whileTap={{ scale: 0.88 }} type="button" onClick={commitRename} disabled={saving} aria-label="Save name"
                    className="w-9 h-9 flex items-center justify-center rounded-md text-success-700 hover:bg-success-50 cursor-pointer disabled:opacity-50">
                    <Check className="w-4 h-4" />
                </motion.button>
                <motion.button whileTap={{ scale: 0.88 }} type="button" onClick={() => setEditing(false)} disabled={saving} aria-label="Cancel rename"
                    className="w-9 h-9 flex items-center justify-center rounded-md text-neutral-500 hover:bg-neutral-100 cursor-pointer">
                    <X className="w-4 h-4" />
                </motion.button>
            </motion.li>
        );
    }

    return (
        <motion.li
            variants={listItem}
            layout
            className={`group relative flex items-center rounded-lg transition-colors ${active ? 'bg-primary-100/70' : 'hover:bg-neutral-100'}`}
        >
            {/* Animated active bar */}
            <AnimatePresence>
                {active && (
                    <motion.span
                        layoutId="active-bulk-bar"
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
                onClick={() => onSelect(batch.id)}
                aria-current={active ? 'page' : undefined}
                className="flex-1 min-w-0 flex items-center gap-2.5 px-3 min-h-[44px] text-left cursor-pointer rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500"
            >
                <Receipt className={`w-4 h-4 flex-shrink-0 ${active ? 'text-primary-700' : 'text-neutral-400'}`} aria-hidden="true" />
                <span className="min-w-0">
                    <span className={`block truncate text-sm ${active ? 'font-semibold text-primary-900' : 'text-neutral-700'}`}>{label}</span>
                    <span className="block truncate text-xs text-neutral-500">
                        {when(batch.created_at)} · {batch.done}/{batch.total} done{batch.attention ? ` · ${batch.attention} need you` : ''}{batch.working ? ' · working' : ''}
                    </span>
                </span>
            </motion.button>

            <div ref={menuRef} className="relative">
                <motion.button
                    whileTap={{ scale: 0.88, rotate: 90 }}
                    transition={{ type: 'spring', stiffness: 500, damping: 20 }}
                    type="button"
                    aria-label={`Options for ${label}`}
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
                                onClick={() => { setMenuOpen(false); setDraft(batch.title || ''); setEditing(true); }}
                                className="flex w-full items-center gap-2 rounded-lg px-3 min-h-[44px] text-sm text-neutral-700 hover:bg-neutral-100 cursor-pointer">
                                <Pencil className="w-4 h-4" /> Rename
                            </motion.button>
                            <motion.button whileTap={{ scale: 0.96 }} type="button" role="menuitem"
                                disabled={batch.working > 0}
                                title={batch.working > 0 ? 'Stop the running invoices first' : undefined}
                                onClick={() => { setMenuOpen(false); onAskDelete(batch); }}
                                className="flex w-full items-center gap-2 rounded-lg px-3 min-h-[44px] text-sm text-error-600 hover:bg-error-50 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent">
                                <Trash2 className="w-4 h-4" /> Delete
                            </motion.button>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>
        </motion.li>
    );
};

BulkBatchItem.propTypes = {
    batch: PropTypes.shape({
        id: PropTypes.string.isRequired, title: PropTypes.string, created_at: PropTypes.string.isRequired,
        total: PropTypes.number, done: PropTypes.number, attention: PropTypes.number, working: PropTypes.number,
        link_name_label: PropTypes.string,
    }).isRequired,
    active: PropTypes.bool,
    onSelect: PropTypes.func.isRequired,
    onRename: PropTypes.func.isRequired,
    onAskDelete: PropTypes.func.isRequired,
};

export default BulkBatchItem;
