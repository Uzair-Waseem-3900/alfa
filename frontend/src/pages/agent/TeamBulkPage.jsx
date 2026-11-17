import { Link, Navigate, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, ChevronRight, Eye, Loader2, Receipt, User } from 'lucide-react';
import { format } from 'date-fns';
import { useAuth } from '../../context/AuthContext';
import { useTeamBulkBatch, useTeamBulkBatches, useTeamBulkOwners } from '../../hooks/useTeamBulk';
import { defaultBatchLabel } from '../../utils/bulkBatch';
import BulkRow, { StatusChip } from '../../components/agent/BulkRow';
import InlineAlert from '../../components/ui/InlineAlert';

const BATCH_STATUS_CHIP = { active: 'processing', waiting: 'needs_attention', finished: 'done', cancelled: 'cancelled' };
const when = (iso) => format(new Date(iso), 'd MMM yyyy, h:mm a');
const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

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

// Superuser-only, READ-ONLY view of everyone's bulk-invoice batches (nothing here can be answered, retried or removed).
//   /agent/bulk-team                   -> users who have batches
//   /agent/bulk-team/:email            -> that user's batches
//   /agent/bulk-team/:email/:batchId   -> the batch with every invoice row
const TeamBulkPage = () => {
    const { user } = useAuth();
    const { email, batchId } = useParams();
    const navigate = useNavigate();

    const owners = useTeamBulkOwners();
    const batches = useTeamBulkBatches(email);
    const view = useTeamBulkBatch(batchId);

    if (user && user.role !== 'superuser') return <Navigate to="/agent/bulk" replace />;

    const batch = view.batch;
    const ownerName = owners.items.find((o) => o.email === email)?.name || batch?.owner_name || email;
    const goUser = (e) => navigate(`/agent/bulk-team/${encodeURIComponent(e)}`);
    const goBatch = (id) => navigate(`/agent/bulk-team/${encodeURIComponent(email)}/${id}`);

    const back = batchId ? `/agent/bulk-team/${encodeURIComponent(email)}` : email ? '/agent/bulk-team' : '/agent/bulk';
    const backLabel = batchId ? 'All users' : email ? 'All users' : 'Bulk invoices';
    const panel = email ? batches : owners;

    const counts = batch ? batch.items.reduce((acc, r) => ({ ...acc, [r.status]: (acc[r.status] || 0) + 1 }), {}) : {};
    const working = (counts.queued || 0) + (counts.processing || 0);

    return (
        <div className="flex h-dvh overflow-hidden bg-white">
            {/* list panel (hidden on mobile while a batch is open) */}
            <aside className={`${batchId ? 'hidden md:flex' : 'flex'} w-full md:w-80 flex-shrink-0 flex-col border-r border-neutral-200 bg-neutral-50`}>
                <header className="flex-shrink-0 h-14 flex items-center gap-2 px-2 border-b border-neutral-200 bg-white">
                    <Link to={back} aria-label={`Back to ${backLabel}`}
                        className="agent-press inline-flex items-center gap-1.5 rounded-lg px-3 min-h-[44px] text-sm font-medium text-primary-700 hover:bg-primary-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500">
                        <ArrowLeft className="w-4 h-4" aria-hidden="true" /> {backLabel}
                    </Link>
                    <h1 className="flex-1 min-w-0 truncate text-sm font-semibold text-neutral-900 text-right pr-2">
                        {email ? ownerName : 'Team bulk invoices'}
                    </h1>
                </header>

                <nav className="flex-1 overflow-y-auto overscroll-contain p-2">
                    {panel.loading ? <Skeleton /> : panel.error ? (
                        <InlineAlert message={panel.error} className="m-1" />
                    ) : panel.items.length === 0 ? (
                        <div className="px-4 py-10 text-center">
                            <Receipt className="w-8 h-8 mx-auto text-neutral-300" aria-hidden="true" />
                            <p className="mt-3 text-sm font-medium text-neutral-700">{email ? 'No batches yet' : 'Nobody has created bulk invoices yet'}</p>
                        </div>
                    ) : (
                        <div className="space-y-0.5">
                            {email ? panel.items.map((b) => (
                                <Row key={b.id} icon={Receipt} active={b.id === batchId} onClick={() => goBatch(b.id)}
                                    title={b.title || defaultBatchLabel(b)}
                                    subtitle={`${when(b.created_at)} · ${b.done}/${b.total} done${b.attention ? ` · ${b.attention} waiting for answers` : ''}${b.working ? ' · working' : ''}`} />
                            )) : panel.items.map((o) => (
                                <Row key={o.email} icon={User} onClick={() => goUser(o.email)}
                                    title={o.name} subtitle={`${o.email} · ${plural(o.batch_count, 'batch')}`}
                                    trailing={<ChevronRight className="w-4 h-4 text-neutral-400" aria-hidden="true" />} />
                            ))}
                            {panel.hasMore && <LoadMore onClick={panel.loadMore} busy={panel.loadingMore} />}
                        </div>
                    )}
                </nav>
            </aside>

            {/* the batch, read only */}
            <section className={`${batchId ? 'flex' : 'hidden md:flex'} flex-1 min-w-0 flex-col`}>
                <header className="flex-shrink-0 h-14 flex items-center gap-2 px-2 sm:px-4 border-b border-neutral-200 bg-white">
                    <Link to={back} aria-label="Back" className="agent-press md:hidden w-11 h-11 flex items-center justify-center rounded-lg text-neutral-600 hover:bg-neutral-100">
                        <ArrowLeft className="w-5 h-5" />
                    </Link>
                    <div className="flex-1 min-w-0 leading-tight">
                        <p className="truncate text-sm font-semibold text-neutral-900">{batch ? (batch.title || defaultBatchLabel({ total: batch.items.length, link_name_label: batch.link_name_label })) : 'Team bulk invoices'}</p>
                        {batch && <p className="truncate text-xs text-neutral-500">{batch.owner_name} · {batch.owner_email}</p>}
                    </div>
                    <Link to="/dashboard"
                        className="agent-press inline-flex items-center gap-1.5 rounded-lg border border-primary-200 bg-primary-50 px-3 min-h-[44px] text-sm font-medium text-primary-700 hover:bg-primary-100">
                        <span className="sm:hidden">Back</span><span className="hidden sm:inline">Back to software</span>
                    </Link>
                </header>

                {!batchId ? (
                    <div className="flex-1 flex items-center justify-center px-6 text-center text-sm text-neutral-500">
                        {email ? 'Pick a batch to read it.' : 'Pick a user to see their bulk invoices.'}
                    </div>
                ) : view.loading && !batch ? (
                    <div className="max-w-3xl w-full mx-auto px-4 py-8 space-y-3" aria-hidden="true">
                        {[1, 2, 3].map((n) => <div key={n} className="h-24 rounded-2xl bg-neutral-100 animate-pulse motion-reduce:animate-none" />)}
                    </div>
                ) : view.error ? (
                    <div className="max-w-3xl w-full mx-auto px-4 py-8"><InlineAlert message={view.error} onRetry={view.reload} /></div>
                ) : batch && (
                    <>
                        <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain">
                            <div className="max-w-3xl mx-auto px-4 py-6 space-y-4">
                                <div className="flex flex-wrap items-center gap-3">
                                    <StatusChip status={BATCH_STATUS_CHIP[batch.status] || 'queued'} />
                                    <p className="flex-1 min-w-0 text-sm text-neutral-600">
                                        {counts.done || 0} of {batch.items.length} done
                                        {batch.link_name_label ? ` · customers from ${batch.link_name_label}` : ''}
                                        {working ? ` · ${working} still working` : ''}
                                    </p>
                                </div>
                                <ul className="space-y-3">
                                    {batch.items.map((row) => <BulkRow key={row.id} row={row} readOnly />)}
                                </ul>
                            </div>
                        </div>
                        <div className="flex-shrink-0 flex items-center justify-center gap-2 border-t border-neutral-200 bg-neutral-50 px-4 min-h-[56px] text-sm text-neutral-600">
                            <Eye className="w-4 h-4" aria-hidden="true" />
                            Read only — this is {batch.owner_name}'s batch
                        </div>
                    </>
                )}
            </section>
        </div>
    );
};

export default TeamBulkPage;
