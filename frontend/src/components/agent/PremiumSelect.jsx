import { useEffect, useId, useMemo, useRef, useState } from 'react';
import PropTypes from 'prop-types';
import { AnimatePresence, motion } from 'framer-motion';
import { Check, ChevronDown, Link2, Search } from 'lucide-react';
import { SPRING_SNAPPY } from '../../utils/motion';

const SEARCH_FROM = 7;   // show the search box once the list is long enough to need it

// Listbox replacement for a native <select>: the native menu cannot be styled and ignores the app's look.
// Options are { value, label, hint? }. Opens upward by default because the bulk composer sits at the page bottom.
const PremiumSelect = ({ id, label, value, options, onChange, placement = 'top', icon: Icon = Link2, className = '' }) => {
    const uid = useId();
    const listId = `${uid}-list`;
    const [open, setOpen] = useState(false);
    const [query, setQuery] = useState('');
    const [active, setActive] = useState(0);
    const rootRef = useRef(null);
    const listRef = useRef(null);
    const searchRef = useRef(null);
    const triggerRef = useRef(null);

    const selected = options.find((o) => String(o.value) === String(value)) || options[0];
    const searchable = options.length >= SEARCH_FROM;
    const shown = useMemo(() => {
        const q = query.trim().toLowerCase();
        return q ? options.filter((o) => `${o.label} ${o.hint || ''}`.toLowerCase().includes(q)) : options;
    }, [options, query]);

    const close = (refocus = true) => {
        setOpen(false);
        setQuery('');
        if (refocus) triggerRef.current?.focus();
    };

    const openList = () => {
        setActive(Math.max(0, options.findIndex((o) => String(o.value) === String(value))));
        setOpen(true);
    };

    const choose = (opt) => {
        onChange(opt.value);
        close();
    };

    // Close on outside press.
    useEffect(() => {
        if (!open) return undefined;
        const onDown = (e) => { if (!rootRef.current?.contains(e.target)) close(false); };
        document.addEventListener('mousedown', onDown);
        return () => document.removeEventListener('mousedown', onDown);
    }, [open]);

    // Focus the search box (or the list) as it opens; keep the highlighted option in view.
    useEffect(() => {
        if (open && searchable) searchRef.current?.focus();
    }, [open, searchable]);
    useEffect(() => {
        if (!open) return;
        listRef.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({ block: 'nearest' });
    }, [open, active]);

    const onKeyDown = (e) => {
        if (!open) {
            if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key)) { e.preventDefault(); openList(); }
            return;
        }
        if (e.key === 'Escape') { e.preventDefault(); close(); }
        else if (e.key === 'ArrowDown') { e.preventDefault(); setActive((i) => Math.min(shown.length - 1, i + 1)); }
        else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => Math.max(0, i - 1)); }
        else if (e.key === 'Home') { e.preventDefault(); setActive(0); }
        else if (e.key === 'End') { e.preventDefault(); setActive(shown.length - 1); }
        else if (e.key === 'Enter') { e.preventDefault(); if (shown[active]) choose(shown[active]); }
        else if (e.key === 'Tab') close(false);
    };

    const up = placement === 'top';

    return (
        <div ref={rootRef} className={`relative ${className}`} onKeyDown={onKeyDown}>
            <motion.button
                ref={triggerRef}
                id={id}
                type="button"
                role="combobox"
                aria-haspopup="listbox"
                aria-expanded={open}
                aria-controls={listId}
                aria-label={label}
                onClick={() => (open ? close() : openList())}
                whileTap={{ scale: 0.985 }}
                transition={SPRING_SNAPPY}
                className={`group flex w-full items-center gap-2.5 rounded-xl border bg-white pl-3 pr-2.5 min-h-[44px] text-left shadow-sm cursor-pointer transition-all duration-200 focus-visible:outline-none ${
                    open
                        ? 'border-accent-500 ring-4 ring-accent-500/15'
                        : 'border-neutral-300 hover:border-neutral-400 hover:shadow focus-visible:ring-2 focus-visible:ring-accent-500'
                }`}
            >
                <span className={`flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg transition-colors ${open ? 'bg-accent-100 text-accent-700' : 'bg-primary-50 text-primary-700 group-hover:bg-accent-50'}`}>
                    <Icon className="h-4 w-4" aria-hidden="true" />
                </span>
                <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-neutral-900">{selected?.label}</span>
                    {selected?.hint && <span className="block truncate text-xs text-neutral-500">{selected.hint}</span>}
                </span>
                <motion.span animate={{ rotate: open ? 180 : 0 }} transition={{ type: 'spring', stiffness: 400, damping: 26 }}
                    className="flex-shrink-0 text-neutral-400 group-hover:text-neutral-600">
                    <ChevronDown className="h-4 w-4" aria-hidden="true" />
                </motion.span>
            </motion.button>

            <AnimatePresence>
                {open && (
                    <motion.div
                        key="panel"
                        initial={{ opacity: 0, y: up ? 8 : -8, scale: 0.97 }}
                        animate={{ opacity: 1, y: 0, scale: 1, transition: { type: 'spring', stiffness: 420, damping: 30 } }}
                        exit={{ opacity: 0, y: up ? 6 : -6, scale: 0.98, transition: { duration: 0.12, ease: 'easeIn' } }}
                        style={{ transformOrigin: up ? 'bottom left' : 'top left' }}
                        className={`absolute left-0 z-30 w-full min-w-[16rem] overflow-hidden rounded-2xl border border-neutral-200 bg-white shadow-dropdown ${up ? 'bottom-full mb-2' : 'top-full mt-2'}`}
                    >
                        {searchable && (
                            <div className="flex items-center gap-2 border-b border-neutral-100 px-3">
                                <Search className="h-4 w-4 flex-shrink-0 text-neutral-400" aria-hidden="true" />
                                <input
                                    ref={searchRef}
                                    value={query}
                                    onChange={(e) => { setQuery(e.target.value); setActive(0); }}
                                    placeholder="Search link names…"
                                    aria-label="Search link names"
                                    aria-controls={listId}
                                    className="w-full bg-transparent py-3 text-base sm:text-sm text-neutral-900 placeholder:text-neutral-400 focus:outline-none"
                                />
                            </div>
                        )}

                        <ul ref={listRef} id={listId} role="listbox" aria-label={label}
                            className="max-h-64 overflow-y-auto overscroll-contain p-1.5">
                            {shown.length === 0 ? (
                                <li className="px-3 py-6 text-center text-sm text-neutral-500">No match</li>
                            ) : shown.map((o, i) => {
                                const isSel = String(o.value) === String(value);
                                const isActive = i === active;
                                return (
                                    <li key={o.value} role="option" aria-selected={isSel} data-index={i}
                                        onMouseEnter={() => setActive(i)}
                                        onMouseDown={(e) => e.preventDefault()}
                                        onClick={() => choose(o)}
                                        className={`relative flex cursor-pointer items-center gap-3 rounded-xl px-3 min-h-[44px] transition-colors ${isActive ? 'bg-primary-50' : ''}`}>
                                        <span className="min-w-0 flex-1">
                                            <span className={`block truncate text-sm ${isSel ? 'font-semibold text-primary-900' : 'text-neutral-800'}`}>{o.label}</span>
                                            {o.hint && <span className="block truncate text-xs text-neutral-500">{o.hint}</span>}
                                        </span>
                                        <AnimatePresence>
                                            {isSel && (
                                                <motion.span initial={{ scale: 0, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0, opacity: 0 }}
                                                    transition={{ type: 'spring', stiffness: 600, damping: 22 }}
                                                    className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-primary-700 text-white">
                                                    <Check className="h-3 w-3" aria-hidden="true" />
                                                </motion.span>
                                            )}
                                        </AnimatePresence>
                                    </li>
                                );
                            })}
                        </ul>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
};

PremiumSelect.propTypes = {
    id: PropTypes.string,
    label: PropTypes.string.isRequired,
    value: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
    options: PropTypes.arrayOf(PropTypes.shape({
        value: PropTypes.oneOfType([PropTypes.string, PropTypes.number]).isRequired,
        label: PropTypes.string.isRequired,
        hint: PropTypes.string,
    })).isRequired,
    onChange: PropTypes.func.isRequired,
    placement: PropTypes.oneOf(['top', 'bottom']),
    icon: PropTypes.elementType,
    className: PropTypes.string,
};

export default PremiumSelect;
