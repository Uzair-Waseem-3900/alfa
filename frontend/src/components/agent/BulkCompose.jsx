import { useRef, useState } from 'react';
import PropTypes from 'prop-types';
import { ListPlus, Loader2, Play, X } from 'lucide-react';
import InlineAlert from '../ui/InlineAlert';

const MAX_CHARS = 2000;
const MAX_ROWS = 100;
const EXAMPLE = 'Uzair Waseem\nSatiana Road\nMAX BLUE 10@228\nMAX RED 5';

const BulkCompose = ({ linkNames, starting, error, onStart }) => {
    const [drafts, setDrafts] = useState([]);
    const [text, setText] = useState('');
    const [linkId, setLinkId] = useState('');
    const textareaRef = useRef(null);
    const full = drafts.length >= MAX_ROWS;
    const canAdd = !full && text.trim().length > 0;

    const add = () => {
        if (!canAdd) return;
        setDrafts((d) => [...d, text.trim()]);
        setText('');
        textareaRef.current?.focus();
    };

    return (
        <div className="flex-1 min-h-0 flex flex-col">
            <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain">
                <div className="max-w-3xl mx-auto px-4 py-6 space-y-4">
                    <section className="rounded-2xl border border-neutral-200 bg-neutral-50 p-4 text-sm text-neutral-700 space-y-2">
                        <h2 className="text-base font-semibold text-neutral-900">Create many invoices at once</h2>
                        <p>Add one request per invoice, then press Start. Each becomes a <strong>draft</strong> you confirm later in Billing. You can close this page while they are created.</p>
                        <p className="font-medium text-neutral-800">Suggested style (you can write it your own way):</p>
                        <pre className="whitespace-pre-wrap rounded-lg bg-white border border-neutral-200 p-3 font-sans text-sm">{`customer name\narea (address, optional)\nitem name quantity@rate`}</pre>
                        <p>Leave out <code>@rate</code> to use the rate list price. A lower rate becomes a line discount; a higher one, a surcharge.</p>
                    </section>

                    {drafts.length === 0 ? (
                        <p className="text-center text-sm text-neutral-500 py-6">No invoices added yet. Example:</p>
                    ) : (
                        <ol className="space-y-3" aria-label="Invoices to create">
                            {drafts.map((d, i) => (
                                <li key={`${i}-${d.slice(0, 12)}`} className="flex items-start gap-3 rounded-2xl border border-neutral-200 bg-white p-3">
                                    <span className="flex-shrink-0 w-7 h-7 rounded-full bg-primary-100 text-primary-800 text-xs font-semibold flex items-center justify-center">{i + 1}</span>
                                    <pre className="flex-1 min-w-0 whitespace-pre-wrap break-words font-sans text-sm text-neutral-800">{d}</pre>
                                    <button type="button" onClick={() => setDrafts((all) => all.filter((_, n) => n !== i))}
                                        aria-label={`Remove invoice ${i + 1}`}
                                        className="w-11 h-11 -m-2 flex items-center justify-center rounded-lg text-neutral-500 hover:bg-neutral-100 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500">
                                        <X className="w-4 h-4" />
                                    </button>
                                </li>
                            ))}
                        </ol>
                    )}
                    {drafts.length === 0 && (
                        <pre className="mx-auto max-w-sm whitespace-pre-wrap rounded-xl bg-neutral-100 p-3 font-sans text-sm text-neutral-600">{EXAMPLE}</pre>
                    )}
                </div>
            </div>

            <div className="px-3 sm:px-4 pt-2 pb-3 border-t border-neutral-200 bg-white">
                <div className="max-w-3xl mx-auto space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                        <label htmlFor="bulk-link-name" className="text-sm text-neutral-600">Customers from link name</label>
                        <select id="bulk-link-name" value={linkId} onChange={(e) => setLinkId(e.target.value)}
                            className="rounded-lg border border-neutral-300 bg-white px-3 min-h-[44px] text-base sm:text-sm focus:outline-none focus:ring-2 focus:ring-accent-500/40">
                            <option value="">All</option>
                            {linkNames.map((l) => <option key={l.id} value={l.id}>{l.name} ({l.sales_man})</option>)}
                        </select>
                    </div>

                    <div className="flex items-end gap-2 rounded-2xl border border-neutral-300 bg-white p-2 focus-within:border-accent-500 focus-within:ring-2 focus-within:ring-accent-500/25">
                        <label htmlFor="bulk-composer" className="sr-only">Invoice request</label>
                        <textarea id="bulk-composer" ref={textareaRef} rows={3} value={text} maxLength={MAX_CHARS} disabled={full}
                            onChange={(e) => setText(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); add(); } }}
                            placeholder={'Customer name\nArea (optional)\nItem name qty@rate'}
                            className="flex-1 resize-none bg-transparent px-2 py-2 text-base leading-6 text-neutral-900 placeholder:text-neutral-400 focus:outline-none" />
                        <button type="button" onClick={add} disabled={!canAdd}
                            className="flex-shrink-0 inline-flex items-center gap-1.5 rounded-xl border border-primary-200 bg-primary-50 px-3 min-h-[44px] text-sm font-semibold text-primary-800 hover:bg-primary-100 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500">
                            <ListPlus className="w-4 h-4" aria-hidden="true" /> Add
                        </button>
                    </div>
                    {full ? (
                        <p className="text-xs font-medium text-warning-700">You added the maximum of {MAX_ROWS} invoices for one batch. Start this batch, then create another.</p>
                    ) : (
                        <p className="text-xs text-neutral-500">Enter adds a new line. Press Add (or Ctrl+Enter) to put it in the list. Up to {MAX_ROWS} invoices per batch.</p>
                    )}
                    {error && <InlineAlert message={error} />}

                    <button type="button" disabled={drafts.length === 0 || starting}
                        onClick={() => onStart({ prompts: drafts, linkNameId: linkId ? Number(linkId) : null })}
                        className="w-full inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-primary-700 to-accent-600 text-white px-4 min-h-[48px] text-sm font-semibold cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed hover:from-primary-800 hover:to-accent-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 focus-visible:ring-offset-2">
                        {starting ? <Loader2 className="w-4 h-4 animate-spin motion-reduce:animate-none" /> : <Play className="w-4 h-4" aria-hidden="true" />}
                        {drafts.length === 0 ? 'Start' : `Start ${drafts.length} invoice${drafts.length === 1 ? '' : 's'}`}
                    </button>
                </div>
            </div>
        </div>
    );
};

BulkCompose.propTypes = {
    linkNames: PropTypes.array.isRequired,
    starting: PropTypes.bool,
    error: PropTypes.string,
    onStart: PropTypes.func.isRequired,
};

export default BulkCompose;
