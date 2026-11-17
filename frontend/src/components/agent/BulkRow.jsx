import { useState } from 'react';
import PropTypes from 'prop-types';
import { Link } from 'react-router-dom';
import {
    AlertTriangle, Ban, CheckCircle2, Clock, ExternalLink, Loader2, MinusCircle, RotateCw, Send, XCircle,
} from 'lucide-react';

// One chip per row status (colours are semantic tokens only).
const STATUS = {
    queued:          { label: 'Queued',            icon: Clock,         chip: 'bg-neutral-100 text-neutral-600' },
    processing:      { label: 'Processing',        icon: Loader2,       chip: 'bg-info-50 text-info-700', spin: true },
    done:            { label: 'Draft created',     icon: CheckCircle2,  chip: 'bg-success-50 text-success-700' },
    needs_attention: { label: 'Needs your answer', icon: AlertTriangle, chip: 'bg-warning-50 text-warning-700' },
    not_invoice:     { label: 'Not an invoice',    icon: Ban,           chip: 'bg-neutral-100 text-neutral-600' },
    failed:          { label: 'Failed',            icon: XCircle,       chip: 'bg-error-50 text-error-700' },
    skipped:         { label: 'Left for you',      icon: MinusCircle,   chip: 'bg-neutral-100 text-neutral-500' },
    cancelled:       { label: 'Cancelled',         icon: MinusCircle,   chip: 'bg-neutral-100 text-neutral-500' },
};

export const StatusChip = ({ status }) => {
    const cfg = STATUS[status] || STATUS.queued;
    const Icon = cfg.icon;
    return (
        <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${cfg.chip}`}>
            <Icon className={`w-3.5 h-3.5 ${cfg.spin ? 'animate-spin motion-reduce:animate-none' : ''}`} aria-hidden="true" />
            {cfg.label}
        </span>
    );
};

StatusChip.propTypes = { status: PropTypes.string.isRequired };

const rs = (v) => (v == null ? 'N/A' : `Rs ${Number(v).toLocaleString('en-PK', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);

// What was created: every line (quantity x the rate charged per unit) and the grand total, as billing calculated them.
const DraftSummary = ({ summary }) => (
    <div className="ml-10 rounded-xl border border-neutral-200 bg-neutral-50 overflow-hidden text-sm">
        <div className="overflow-x-auto">
            <table className="w-full">
                <caption className="sr-only">Items on this draft invoice</caption>
                <thead>
                    <tr className="text-left text-xs text-neutral-500">
                        <th scope="col" className="px-3 py-2 font-medium">Item</th>
                        <th scope="col" className="px-3 py-2 font-medium text-right">Qty</th>
                        <th scope="col" className="px-3 py-2 font-medium text-right">Rate</th>
                        <th scope="col" className="px-3 py-2 font-medium text-right">Total</th>
                    </tr>
                </thead>
                <tbody>
                    {summary.lines.map((l, i) => (
                        <tr key={`${l.code}-${i}`} className="border-t border-neutral-200">
                            <td className="px-3 py-2 text-neutral-800 min-w-[8rem]">{l.product}</td>
                            <td className="px-3 py-2 text-right tabular-nums">{l.quantity}</td>
                            <td className="px-3 py-2 text-right tabular-nums whitespace-nowrap">
                                {rs(l.rate)}
                                {l.list_rate && l.rate && Number(l.list_rate) !== Number(l.rate) && (
                                    <span className="block text-xs text-neutral-500">list {rs(l.list_rate)}</span>
                                )}
                            </td>
                            <td className="px-3 py-2 text-right tabular-nums whitespace-nowrap">{rs(l.line_total)}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
        <div className="border-t border-neutral-200 px-3 py-2 space-y-0.5">
            {summary.invoice_discount && (
                <p className="flex justify-between text-neutral-600">
                    <span>Invoice discount{summary.invoice_discount_percent ? ` (${summary.invoice_discount_percent}%)` : ''}</span>
                    <span className="tabular-nums">- {rs(summary.invoice_discount)}</span>
                </p>
            )}
            <p className="flex justify-between font-semibold text-neutral-900">
                <span>Grand total</span><span className="tabular-nums">{rs(summary.grand_total)}</span>
            </p>
        </div>
    </div>
);

DraftSummary.propTypes = {
    summary: PropTypes.shape({
        lines: PropTypes.array, invoice_discount: PropTypes.string, invoice_discount_percent: PropTypes.string, grand_total: PropTypes.string,
    }).isRequired,
};

const BTN = 'inline-flex items-center justify-center gap-1.5 rounded-lg px-3 min-h-[44px] text-sm font-medium cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500';

const BulkRow = ({ row, busy, readOnly = false, onAnswer, onSkip, onRetry }) => {
    const [text, setText] = useState('');
    const send = async (answer) => {
        const value = (answer ?? text).trim();
        if (!value || busy) return;
        const ok = await onAnswer(row.id, value);
        if (ok) setText('');
    };

    return (
        <li className="rounded-2xl border border-neutral-200 bg-white p-3 sm:p-4 space-y-3">
            <div className="flex items-start gap-3">
                <span className="flex-shrink-0 w-7 h-7 rounded-full bg-neutral-100 text-neutral-600 text-xs font-semibold flex items-center justify-center" aria-hidden="true">
                    {row.position}
                </span>
                <pre className="flex-1 min-w-0 whitespace-pre-wrap break-words font-sans text-sm text-neutral-800">{row.prompt}</pre>
                <StatusChip status={row.status} />
            </div>

            {row.status === 'done' && (
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pl-10 text-sm">
                    <span className="font-semibold text-neutral-900">{row.bill_number}</span>
                    {row.customer_label && <span className="text-neutral-600">for {row.customer_label}</span>}
                    {row.invoice_id && (
                        <Link to={`/billing/invoices/${row.invoice_id}`} target="_blank" rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-primary-700 hover:underline min-h-[44px]">
                            Open draft <ExternalLink className="w-3.5 h-3.5" aria-hidden="true" />
                        </Link>
                    )}
                </div>
            )}

            {row.status === 'done' && row.summary?.lines?.length > 0 && <DraftSummary summary={row.summary} />}

            {readOnly && row.status === 'needs_attention' && (
                <div className="pl-10 space-y-2">
                    <p className="text-sm font-medium text-neutral-900 whitespace-pre-wrap">{row.question}</p>
                    {row.options?.length > 0 && <p className="text-xs text-neutral-500">Options offered: {row.options.join(' · ')}</p>}
                    <p className="text-xs text-neutral-500">Waiting for the owner to answer.</p>
                </div>
            )}

            {readOnly && (row.status === 'failed' || row.status === 'not_invoice') && (
                <p className="pl-10 text-sm text-neutral-700 whitespace-pre-wrap">{row.message}</p>
            )}

            {!readOnly && row.status === 'needs_attention' && (
                <div className="pl-10 space-y-3">
                    <p className="text-sm font-medium text-neutral-900 whitespace-pre-wrap">{row.question}</p>
                    {row.options?.length > 0 && (
                        <div className="flex flex-wrap gap-2">
                            {row.options.map((opt) => (
                                <button key={opt} type="button" disabled={busy} onClick={() => send(opt)}
                                    className={`${BTN} border border-primary-200 bg-primary-50 text-primary-800 hover:bg-primary-100 text-left`}>
                                    {opt}
                                </button>
                            ))}
                        </div>
                    )}
                    <form onSubmit={(e) => { e.preventDefault(); send(); }} className="flex gap-2">
                        <label htmlFor={`answer-${row.id}`} className="sr-only">Your answer for invoice {row.position}</label>
                        <input id={`answer-${row.id}`} value={text} maxLength={500} onChange={(e) => setText(e.target.value)}
                            placeholder="Type your answer…" disabled={busy}
                            className="flex-1 min-w-0 rounded-lg border border-neutral-300 bg-white px-3 min-h-[44px] text-base focus:outline-none focus:ring-2 focus:ring-accent-500/40 focus:border-accent-500" />
                        <button type="submit" disabled={busy || !text.trim()} aria-label="Send answer"
                            className={`${BTN} bg-primary-700 text-white hover:bg-primary-800`}>
                            {busy ? <Loader2 className="w-4 h-4 animate-spin motion-reduce:animate-none" /> : <Send className="w-4 h-4" />}
                        </button>
                    </form>
                    <button type="button" disabled={busy} onClick={() => onSkip(row.id)}
                        className={`${BTN} text-neutral-600 hover:bg-neutral-100`}>
                        I will do it myself
                    </button>
                </div>
            )}

            {!readOnly && (row.status === 'failed' || row.status === 'not_invoice') && (
                <div className="pl-10 space-y-2">
                    <p className="text-sm text-neutral-700 whitespace-pre-wrap">{row.message}</p>
                    {row.status === 'not_invoice' && (
                        <p className="text-sm text-neutral-600">
                            This screen only creates invoices. For questions about your business use the{' '}
                            <Link to="/agent" className="text-primary-700 hover:underline">Assistant</Link>.
                        </p>
                    )}
                    <div className="flex flex-wrap gap-2">
                        <button type="button" disabled={busy} onClick={() => onRetry(row.id)}
                            className={`${BTN} border border-neutral-300 bg-white text-neutral-800 hover:bg-neutral-50`}>
                            <RotateCw className="w-4 h-4" aria-hidden="true" /> Retry
                        </button>
                        <button type="button" disabled={busy} onClick={() => onSkip(row.id)}
                            className={`${BTN} text-neutral-600 hover:bg-neutral-100`}>
                            I will do it myself
                        </button>
                    </div>
                </div>
            )}
        </li>
    );
};

BulkRow.propTypes = {
    row: PropTypes.shape({
        id: PropTypes.number.isRequired, position: PropTypes.number.isRequired, prompt: PropTypes.string.isRequired,
        status: PropTypes.string.isRequired, question: PropTypes.string, options: PropTypes.array, message: PropTypes.string,
        bill_number: PropTypes.string, invoice_id: PropTypes.number, customer_label: PropTypes.string, summary: PropTypes.object,
    }).isRequired,
    busy: PropTypes.bool,
    readOnly: PropTypes.bool,
    onAnswer: PropTypes.func,
    onSkip: PropTypes.func,
    onRetry: PropTypes.func,
};

export default BulkRow;
