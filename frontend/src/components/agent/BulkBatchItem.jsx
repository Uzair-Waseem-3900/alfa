import { useState } from 'react';
import PropTypes from 'prop-types';
import { format } from 'date-fns';
import { Check, Pencil, Trash2, X } from 'lucide-react';
import { defaultBatchLabel } from '../../utils/bulkBatch';

const when = (iso) => format(new Date(iso), 'd MMM, h:mm a');

const ICON_BTN = 'w-11 h-11 flex items-center justify-center rounded-lg cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500';

// One batch in the history sidebar: open it, rename it, or remove it.
const BulkBatchItem = ({ batch, active, onSelect, onRename, onAskDelete }) => {
    const [editing, setEditing] = useState(false);
    const [draft, setDraft] = useState('');
    const [saving, setSaving] = useState(false);

    const startEdit = () => { setDraft(batch.title || ''); setEditing(true); };

    const commit = async () => {
        const title = draft.trim();
        if (saving) return;
        if (!title || title === batch.title) { setEditing(false); return; }
        setSaving(true);
        const ok = await onRename(batch.id, title);
        setSaving(false);
        if (ok) setEditing(false);
    };

    if (editing) {
        return (
            <li className="flex items-center gap-1 rounded-lg bg-white border border-accent-500 px-2 py-1">
                <input
                    autoFocus
                    value={draft}
                    maxLength={120}
                    disabled={saving}
                    aria-label="Batch name"
                    placeholder={defaultBatchLabel(batch)}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === 'Enter') commit();
                        if (e.key === 'Escape') setEditing(false);
                    }}
                    className="flex-1 min-w-0 bg-transparent py-1.5 text-base sm:text-sm text-neutral-900 focus:outline-none"
                />
                <button type="button" onClick={commit} disabled={saving} aria-label="Save name"
                    className={`${ICON_BTN} text-success-700 hover:bg-success-50 disabled:opacity-50`}>
                    <Check className="w-4 h-4" />
                </button>
                <button type="button" onClick={() => setEditing(false)} disabled={saving} aria-label="Cancel rename"
                    className={`${ICON_BTN} text-neutral-500 hover:bg-neutral-100`}>
                    <X className="w-4 h-4" />
                </button>
            </li>
        );
    }

    return (
        <li className={`group flex items-center rounded-lg ${active ? 'bg-primary-100/70' : 'hover:bg-neutral-100'}`}>
            <button type="button" onClick={() => onSelect(batch.id)} aria-current={active ? 'page' : undefined}
                className="flex-1 min-w-0 text-left px-3 py-2 min-h-[56px] cursor-pointer rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500">
                <span className="block truncate text-sm font-medium text-neutral-800">{batch.title || defaultBatchLabel(batch)}</span>
                <span className="block truncate text-xs text-neutral-500">
                    {when(batch.created_at)} · {batch.done}/{batch.total} done{batch.attention ? ` · ${batch.attention} need you` : ''}{batch.working ? ' · working' : ''}
                </span>
            </button>
            <button type="button" onClick={startEdit} aria-label={`Rename ${batch.title || defaultBatchLabel(batch)}`}
                className={`${ICON_BTN} text-neutral-400 hover:text-neutral-700 hover:bg-neutral-200/70`}>
                <Pencil className="w-4 h-4" />
            </button>
            <button type="button" onClick={() => onAskDelete(batch)} disabled={batch.working > 0} aria-label={`Remove ${batch.title || defaultBatchLabel(batch)}`}
                className={`${ICON_BTN} text-neutral-400 hover:text-error-600 hover:bg-neutral-200/70 disabled:opacity-30 disabled:cursor-not-allowed`}>
                <Trash2 className="w-4 h-4" />
            </button>
        </li>
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
