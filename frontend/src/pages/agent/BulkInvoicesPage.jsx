import { useEffect, useRef, useState } from 'react';
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom';
import { format } from 'date-fns';
import { ArrowLeft, Loader2, PanelLeft, Plus, Square, Trash2, X } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { bulkApi } from '../../services/agentApi';
import { useBulkBatch, useBulkBatches, useLinkNames } from '../../hooks/useBulkInvoices';
import { extractErrorMessage } from '../../utils/errorMessage';
import BulkCompose from '../../components/agent/BulkCompose';
import BulkRow, { StatusChip } from '../../components/agent/BulkRow';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import InlineAlert from '../../components/ui/InlineAlert';

const SIDEBAR_POLL_MS = 4000;
const BATCH_STATUS_CHIP = { active: 'processing', waiting: 'needs_attention', finished: 'done', cancelled: 'cancelled' };
const when = (iso) => format(new Date(iso), 'd MMM, h:mm a');
const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

// The sidebar's counts come from the list API (loaded once). For the batch that is open, use the live rows instead,
// so "0/2" turns into "2/2" as each invoice finishes.
const liveCounts = (items) => items.reduce((acc, r) => ({
    total: acc.total + 1,
    done: acc.done + (r.status === 'done' ? 1 : 0),
    attention: acc.attention + (r.status === 'needs_attention' ? 1 : 0),
    working: acc.working + (r.status === 'queued' || r.status === 'processing' ? 1 : 0),
}), { total: 0, done: 0, attention: 0, working: 0 });

// Bulk invoice creation: many prompts, one DRAFT invoice each, worked one after another on the server.
//   /agent/bulk            -> add prompts and start
//   /agent/bulk/:batchId   -> live progress, answer the agent's questions
// Like the assistant page it sits outside <Layout> (own history sidebar + "Back to software").
const BulkInvoicesPage = () => {
    const { user } = useAuth();
    const { toast } = useToast();
    const navigate = useNavigate();
    const { batchId } = useParams();

    const batches = useBulkBatches();
    const linkNames = useLinkNames();
    const view = useBulkBatch(batchId);

    // When the open batch settles (stops working), re-read the list quietly so its sidebar numbers are the stored ones.
    const batchStatus = view.batch?.status;
    const lastStatus = useRef(batchStatus);
    const { refreshSilently } = batches;
    useEffect(() => {
        if (lastStatus.current === 'active' && batchStatus && batchStatus !== 'active') refreshSilently();
        lastStatus.current = batchStatus;
    }, [batchStatus, refreshSilently]);

    const startingRef = useRef(false);
    // Whatever the live events do, the sidebar re-reads its numbers from the server every few seconds while any
    // listed batch is still working (one grouped query), so it always ends up matching the database.
    const anyWorking = batches.items.some((b) => b.working > 0) || view.batch?.status === 'active';
    useEffect(() => {
        if (!anyWorking) return undefined;
        const timer = setInterval(refreshSilently, SIDEBAR_POLL_MS);
        return () => clearInterval(timer);
    }, [anyWorking, refreshSilently]);

    const [sidebarOpen, setSidebarOpen] = useState(false);
    const [starting, setStarting] = useState(false);
    const [startError, setStartError] = useState(null);
    const [toDelete, setToDelete] = useState(null);
    const [deleting, setDeleting] = useState(false);

    // Same inline role check every admin page uses.
    if (user && user.role !== 'admin' && user.role !== 'superuser') return <Navigate to="/dashboard" replace />;

    // The ref (not the state) blocks a double click: two clicks can land before React re-renders the disabled button,
    // and each accepted call would create a whole batch of drafts.
    const start = async ({ prompts, linkNameId }) => {
        if (startingRef.current) return;
        startingRef.current = true;
        setStarting(true);
        setStartError(null);
        try {
            const batch = await bulkApi.createBatch({ prompts, linkNameId });
            batches.refresh();
            navigate(`/agent/bulk/${batch.id}`);
        } catch (err) {
            const message = extractErrorMessage(err, 'Could not start the batch');
            setStartError(message);          // stays visible next to the Start button (limits, validation)
            toast.error(message);
        } finally {
            startingRef.current = false;
            setStarting(false);
        }
    };

    const confirmDelete = async () => {
        setDeleting(true);
        try {
            await bulkApi.deleteBatch(toDelete.id);
            toast.success('Batch removed from your history');
            if (toDelete.id === batchId) navigate('/agent/bulk', { replace: true });
            setToDelete(null);
            batches.refresh();
        } catch (err) {
            toast.error(extractErrorMessage(err, 'Could not remove the batch'));
        } finally {
            setDeleting(false);
        }
    };

    const goto = (path) => { navigate(path); setSidebarOpen(false); };
    const batch = view.batch;
    const counts = batch ? batch.items.reduce((acc, r) => ({ ...acc, [r.status]: (acc[r.status] || 0) + 1 }), {}) : {};
    const working = (counts.queued || 0) + (counts.processing || 0);
    const waiting = counts.needs_attention || 0;

    return (
        <div className="flex h-dvh overflow-hidden bg-white">
            {sidebarOpen && <div className="fixed inset-0 z-30 bg-black/50 md:hidden" onClick={() => setSidebarOpen(false)} aria-hidden="true" />}

            <aside aria-label="Bulk invoice history"
                className={`${sidebarOpen ? 'flex' : 'hidden'} md:flex fixed inset-y-0 left-0 z-40 w-[85vw] max-w-xs md:static md:w-72 md:max-w-none flex-shrink-0 flex-col border-r border-neutral-200 bg-neutral-50`}>
                <div className="flex items-center gap-2 p-3">
                    <button type="button" onClick={() => goto('/agent/bulk')}
                        className="flex-1 inline-flex items-center justify-center gap-2 rounded-xl border border-neutral-300 bg-white px-4 min-h-[44px] text-sm font-semibold text-neutral-800 hover:bg-neutral-50 shadow-sm cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500">
                        <Plus className="w-4 h-4" aria-hidden="true" /> New bulk
                    </button>
                    <button type="button" onClick={() => setSidebarOpen(false)} aria-label="Close history"
                        className="md:hidden w-11 h-11 flex items-center justify-center rounded-xl text-neutral-500 hover:bg-neutral-100 cursor-pointer">
                        <X className="w-5 h-5" />
                    </button>
                </div>
                <nav className="flex-1 overflow-y-auto overscroll-contain px-2 pb-4">
                    {batches.loading ? (
                        <div className="space-y-2 px-1 pt-2" aria-hidden="true">
                            {[70, 55, 80].map((w, i) => <div key={i} className="h-14 rounded-lg bg-neutral-200/70 animate-pulse motion-reduce:animate-none" style={{ width: `${w}%` }} />)}
                        </div>
                    ) : batches.error ? (
                        <InlineAlert message={batches.error} onRetry={batches.refresh} className="mx-1" />
                    ) : batches.items.length === 0 ? (
                        <p className="px-4 py-10 text-center text-sm text-neutral-500">No bulk invoices yet.</p>
                    ) : (
                        <ul className="space-y-0.5">
                            {batches.items.map((listed) => {
                                const b = listed.id === batchId && view.batch ? { ...listed, ...liveCounts(view.batch.items) } : listed;
                                return (
                                <li key={b.id} className={`group flex items-center rounded-lg ${b.id === batchId ? 'bg-primary-100/70' : 'hover:bg-neutral-100'}`}>
                                    <button type="button" onClick={() => goto(`/agent/bulk/${b.id}`)} aria-current={b.id === batchId ? 'page' : undefined}
                                        className="flex-1 min-w-0 text-left px-3 py-2 min-h-[56px] cursor-pointer rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500">
                                        <span className="block truncate text-sm font-medium text-neutral-800">
                                            {plural(b.total, 'invoice')}{b.link_name_label ? ` · ${b.link_name_label}` : ''}
                                        </span>
                                        <span className="block truncate text-xs text-neutral-500">
                                            {when(b.created_at)} · {b.done}/{b.total} done{b.attention ? ` · ${b.attention} need you` : ''}{b.working ? ' · working' : ''}
                                        </span>
                                    </button>
                                    <button type="button" onClick={() => setToDelete(b)} disabled={b.working > 0} aria-label={`Remove batch from ${when(b.created_at)}`}
                                        className="w-11 h-11 flex items-center justify-center rounded-lg text-neutral-400 hover:text-error-600 hover:bg-neutral-200/70 cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed">
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                </li>
                                );
                            })}
                            {batches.hasMore && (
                                <li>
                                    <button type="button" onClick={batches.loadMore} disabled={batches.loadingMore}
                                        className="w-full flex items-center justify-center gap-2 rounded-lg min-h-[44px] text-sm font-medium text-primary-700 hover:bg-neutral-100 cursor-pointer disabled:opacity-60">
                                        {batches.loadingMore && <Loader2 className="w-4 h-4 animate-spin motion-reduce:animate-none" />} Show older
                                    </button>
                                </li>
                            )}
                        </ul>
                    )}
                </nav>
            </aside>

            <div className="flex flex-1 min-w-0 flex-col">
                <header className="flex-shrink-0 h-14 flex items-center gap-1 sm:gap-2 px-2 sm:px-4 border-b border-neutral-200 bg-white">
                    <button type="button" onClick={() => setSidebarOpen(true)} aria-label="Show bulk invoice history"
                        className="md:hidden w-11 h-11 flex items-center justify-center rounded-lg text-neutral-600 hover:bg-neutral-100 cursor-pointer">
                        <PanelLeft className="w-5 h-5" />
                    </button>
                    <div className="flex-1 min-w-0 leading-tight">
                        <h1 className="truncate text-sm font-semibold text-neutral-900">Bulk invoices</h1>
                        <p className="hidden sm:block text-xs text-neutral-500">Create many draft invoices at once</p>
                    </div>
                    <Link to="/agent" className="hidden sm:inline-flex items-center rounded-lg px-3 min-h-[44px] text-sm font-medium text-neutral-600 hover:bg-neutral-100">Assistant</Link>
                    <Link to="/dashboard"
                        className="inline-flex items-center gap-1.5 rounded-lg border border-primary-200 bg-primary-50 px-3 min-h-[44px] text-sm font-medium text-primary-700 hover:bg-primary-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500">
                        <ArrowLeft className="w-4 h-4" aria-hidden="true" />
                        <span className="sm:hidden">Back</span><span className="hidden sm:inline">Back to software</span>
                    </Link>
                </header>

                {!batchId ? (
                    <BulkCompose linkNames={linkNames} starting={starting} error={startError} onStart={start} />
                ) : view.loading && !batch ? (
                    <div className="max-w-3xl w-full mx-auto px-4 py-8 space-y-3" aria-hidden="true">
                        {[1, 2, 3].map((n) => <div key={n} className="h-24 rounded-2xl bg-neutral-100 animate-pulse motion-reduce:animate-none" />)}
                    </div>
                ) : view.error ? (
                    <div className="max-w-3xl w-full mx-auto px-4 py-8"><InlineAlert message={view.error} onRetry={view.reload} /></div>
                ) : batch && (
                    <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain">
                        <div className="max-w-3xl mx-auto px-4 py-6 space-y-4">
                            <div className="flex flex-wrap items-center gap-3">
                                <StatusChip status={BATCH_STATUS_CHIP[batch.status] || 'queued'} />
                                <p className="flex-1 min-w-0 text-sm text-neutral-600">
                                    {counts.done || 0} of {batch.items.length} done
                                    {batch.link_name_label ? ` · customers from ${batch.link_name_label}` : ''}
                                    {working ? ` · ${working} still working` : ''}
                                </p>
                                {working > 0 && batch.status !== 'cancelled' && (
                                    <button type="button" onClick={view.cancel}
                                        className="inline-flex items-center gap-1.5 rounded-lg border border-neutral-300 bg-white px-3 min-h-[44px] text-sm font-medium text-neutral-700 hover:bg-neutral-50 cursor-pointer">
                                        <Square className="w-4 h-4" aria-hidden="true" /> Stop remaining
                                    </button>
                                )}
                            </div>

                            {working > 0 && (
                                <InlineAlert variant="info" message="You can leave this page. The invoices keep being created and you will find the results here." />
                            )}
                            {working === 0 && waiting > 0 && (
                                <InlineAlert variant="warning" title={`${plural(waiting, 'invoice')} need${waiting === 1 ? 's' : ''} your answer`}
                                    message="Answer each question below. Only that invoice is tried again, or choose “I will do it myself”." />
                            )}

                            <ul className="space-y-3">
                                {batch.items.map((row) => (
                                    <BulkRow key={row.id} row={row} busy={!!view.busyRows[row.id]}
                                        onAnswer={view.answer} onSkip={view.skip} onRetry={view.retry} />
                                ))}
                            </ul>
                        </div>
                    </div>
                )}
            </div>

            <ConfirmDialog
                isOpen={!!toDelete}
                onClose={() => !deleting && setToDelete(null)}
                onConfirm={confirmDelete}
                title="Remove this batch?"
                message="It disappears from your history. Draft invoices already created are not deleted."
                confirmText="Remove"
                loading={deleting}
            />
        </div>
    );
};

export default BulkInvoicesPage;
