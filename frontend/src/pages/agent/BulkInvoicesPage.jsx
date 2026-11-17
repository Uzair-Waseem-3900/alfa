import { useEffect, useRef, useState } from 'react';
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Loader2, Plus, Sparkles, Square, Users, X } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { bulkApi } from '../../services/agentApi';
import { useBulkBatch, useBulkBatches, useLinkNames } from '../../hooks/useBulkInvoices';
import { extractErrorMessage } from '../../utils/errorMessage';
import AgentHeader from '../../components/agent/AgentHeader';
import SidebarShell from '../../components/agent/SidebarShell';
import BulkBatchItem from '../../components/agent/BulkBatchItem';
import { defaultBatchLabel } from '../../utils/bulkBatch';
import BulkCompose from '../../components/agent/BulkCompose';
import BulkRow, { StatusChip } from '../../components/agent/BulkRow';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import InlineAlert from '../../components/ui/InlineAlert';

// Staggered entrance of the history entries: same as the assistant's chat list.
const listContainer = { hidden: {}, show: { transition: { staggerChildren: 0.045 } } };
const SIDEBAR_POLL_MS = 4000;
const MD_BREAKPOINT = 768;
const isMobile = () => window.innerWidth < MD_BREAKPOINT;
const BATCH_STATUS_CHIP = { active: 'processing', waiting: 'needs_attention', finished: 'done', cancelled: 'cancelled' };
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

    const [sidebarOpen, setSidebarOpen] = useState(() => !isMobile());   // open on desktop, closed drawer on mobile
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

    const renameBatch = async (id, title) => {
        try {
            await bulkApi.renameBatch(id, title);
            batches.refreshSilently();
            if (id === batchId) view.reload({ silent: true });
            return true;
        } catch (err) {
            toast.error(extractErrorMessage(err, 'Could not rename the batch'));
            return false;
        }
    };

    const goto = (path) => { navigate(path); if (isMobile()) setSidebarOpen(false); };
    const batch = view.batch;
    const counts = batch ? batch.items.reduce((acc, r) => ({ ...acc, [r.status]: (acc[r.status] || 0) + 1 }), {}) : {};
    const working = (counts.queued || 0) + (counts.processing || 0);
    const waiting = counts.needs_attention || 0;

    return (
        <div className="flex h-dvh overflow-hidden bg-white">
            <SidebarShell open={sidebarOpen} onClose={() => setSidebarOpen(false)} label="Bulk invoice history">
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
                {user?.role === 'superuser' && (
                    <div className="px-3 pb-2">
                        <button type="button" onClick={() => goto('/agent/bulk-team')}
                            className="w-full flex items-center gap-2 rounded-xl px-3 min-h-[44px] text-sm font-medium text-neutral-700 hover:bg-neutral-100 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500">
                            <Users className="w-4 h-4 text-neutral-500" aria-hidden="true" /> Team bulk invoices
                        </button>
                    </div>
                )}
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
                        <motion.ul className="space-y-0.5" variants={listContainer} initial="hidden" animate="show">
                            {batches.items.map((listed) => {
                                const b = listed.id === batchId && view.batch ? { ...listed, ...liveCounts(view.batch.items) } : listed;
                                return (
                                    <BulkBatchItem key={b.id} batch={b} active={b.id === batchId}
                                        onSelect={(id) => goto(`/agent/bulk/${id}`)} onRename={renameBatch} onAskDelete={setToDelete} />
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
                        </motion.ul>
                    )}
                </nav>
            </SidebarShell>

            <div className="flex flex-1 min-w-0 flex-col">
                <AgentHeader
                    assistantName="Bulk invoices"
                    subtitle="Create many draft invoices at once"
                    newLabel="New bulk batch"
                    sidebarOpen={sidebarOpen}
                    onToggleSidebar={() => setSidebarOpen((o) => !o)}
                    onNewChat={() => goto('/agent/bulk')}
                    actions={(
                        <Link to="/agent" aria-label="Switch to the assistant" title="Ask the assistant about your business"
                            className="inline-flex items-center gap-1.5 rounded-lg px-3 min-h-[44px] text-sm font-medium text-neutral-600 hover:bg-neutral-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500">
                            <Sparkles className="w-4 h-4" aria-hidden="true" />
                            <span className="hidden sm:inline">Assistant</span>
                        </Link>
                    )}
                />

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
                            {batch.title && <h2 className="text-lg font-semibold text-neutral-900 break-words">{batch.title}</h2>}
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
                title={toDelete ? `Remove "${toDelete.title || defaultBatchLabel(toDelete)}"?` : "Remove this batch?"}
                message="It disappears from your history. Draft invoices already created are not deleted."
                confirmText="Remove"
                loading={deleting}
            />
        </div>
    );
};

export default BulkInvoicesPage;
