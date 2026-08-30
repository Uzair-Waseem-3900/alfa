import { useState, useMemo, useCallback, useRef } from 'react';
import { motion } from 'framer-motion';
import { Landmark, Coins, RotateCcw } from 'lucide-react';
import Button from '../../components/ui/Button';

// All denominations in order — used to navigate between rows with arrow keys
const NOTES = [
    { label: 'Rs. 5,000', value: 5000 },
    { label: 'Rs. 1,000', value: 1000 },
    { label: 'Rs. 500',   value: 500  },
    { label: 'Rs. 100',   value: 100  },
    { label: 'Rs. 50',    value: 50   },
    { label: 'Rs. 20',    value: 20   },
    { label: 'Rs. 10',    value: 10   },
];

const COINS = [
    { label: 'Rs. 5',  value: 5 },
    { label: 'Rs. 2',  value: 2 },
    { label: 'Rs. 1',  value: 1 },
];

const ALL_DENOMS = [...NOTES, ...COINS];

/** Pakistani lakh notation: 123500 → "Rs. 1,23,500" */
function formatPKR(amount) {
    if (amount === 0) return 'Rs. 0';
    const str = String(Math.floor(amount));
    if (str.length <= 3) return `Rs. ${str}`;
    const last3 = str.slice(-3);
    const rest   = str.slice(0, -3);
    const groups = [];
    for (let i = rest.length; i > 0; i -= 2) {
        groups.unshift(rest.slice(Math.max(0, i - 2), i));
    }
    return `Rs. ${groups.join(',')},${last3}`;
}

function parseQty(raw) {
    const n = parseInt(raw, 10);
    return Number.isFinite(n) && n >= 0 ? n : 0;
}

// ── animation variants ──────────────────────────────────────────────────────
const containerVariants = {
    hidden:  { opacity: 0, y: 16 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: 'easeOut', staggerChildren: 0.04 } },
};
const cardVariants = {
    hidden:  { opacity: 0, y: 12 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.3, ease: 'easeOut' } },
};
const rowVariants = {
    hidden:  { opacity: 0, x: -10 },
    visible: { opacity: 1, x: 0, transition: { duration: 0.25, ease: 'easeOut' } },
};

// ── main component ───────────────────────────────────────────────────────────
export default function CashCalculatorPage() {
    const [quantities, setQuantities] = useState(() =>
        Object.fromEntries(ALL_DENOMS.map(d => [d.value, '']))
    );

    // refs to all inputs, indexed by denomination value — for arrow-key navigation
    const inputRefs = useRef({});

    const handleChange = useCallback((denomValue, raw) => {
        setQuantities(prev => ({ ...prev, [denomValue]: raw.replace(/[^0-9]/g, '') }));
    }, []);

    const handleStep = useCallback((denomValue, delta) => {
        setQuantities(prev => {
            const next = Math.max(0, parseQty(prev[denomValue]) + delta);
            return { ...prev, [denomValue]: next === 0 ? '' : String(next) };
        });
    }, []);

    const handleKeyDown = useCallback((e, denomValue) => {
        const idx = ALL_DENOMS.findIndex(d => d.value === denomValue);
        if (e.key === 'ArrowLeft') {
            e.preventDefault();
            handleStep(denomValue, -1);
        } else if (e.key === 'ArrowRight') {
            e.preventDefault();
            handleStep(denomValue, +1);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            const prev = ALL_DENOMS[idx - 1];
            if (prev) inputRefs.current[prev.value]?.focus();
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            const next = ALL_DENOMS[idx + 1];
            if (next) inputRefs.current[next.value]?.focus();
        }
    }, [handleStep]);

    const handleReset = () => {
        setQuantities(Object.fromEntries(ALL_DENOMS.map(d => [d.value, ''])));
    };

    const total = useMemo(() =>
        ALL_DENOMS.reduce((sum, d) => sum + d.value * parseQty(quantities[d.value]), 0),
        [quantities]
    );
    const noteTotal = useMemo(() =>
        NOTES.reduce((sum, d) => sum + d.value * parseQty(quantities[d.value]), 0),
        [quantities]
    );
    const coinTotal = useMemo(() =>
        COINS.reduce((sum, d) => sum + d.value * parseQty(quantities[d.value]), 0),
        [quantities]
    );

    return (
        <motion.div
            className="flex flex-col sm:h-[calc(100vh-4rem)] sm:overflow-hidden p-4 gap-3"
            variants={containerVariants}
            initial="hidden"
            animate="visible"
        >
            {/* ── Grand total banner ── */}
            <motion.div
                variants={cardVariants}
                className="shrink-0 rounded-2xl bg-gradient-to-br from-primary-700 to-accent-600
                           px-6 py-4 shadow-lg shadow-primary-900/20 text-white
                           flex items-center justify-between"
            >
                <div>
                    <p className="text-[10px] font-semibold uppercase tracking-widest opacity-70 mb-0.5">
                        Grand Total
                    </p>
                    <motion.p
                        key={total}
                        initial={{ scale: 0.94, opacity: 0.5 }}
                        animate={{ scale: 1, opacity: 1 }}
                        transition={{ duration: 0.14 }}
                        className="text-3xl font-bold tracking-tight"
                    >
                        {formatPKR(total)}
                    </motion.p>
                    <div className="mt-1 flex gap-5 text-xs opacity-75">
                        <span className="inline-flex items-center gap-1"><Landmark className="w-3.5 h-3.5" /> Notes&nbsp;<span className="font-semibold">{formatPKR(noteTotal)}</span></span>
                        <span className="inline-flex items-center gap-1"><Coins className="w-3.5 h-3.5" /> Coins&nbsp;<span className="font-semibold">{formatPKR(coinTotal)}</span></span>
                    </div>
                </div>

                {/* Reset button lives in the banner */}
                <Button
                    variant="secondary"
                    size="sm"
                    onClick={handleReset}
                    icon={RotateCcw}
                    className="!bg-white/20 !border-white/30 !text-white hover:!bg-white/30"
                >
                    Reset
                </Button>
            </motion.div>

            {/* ── Two-column grid (stacks on mobile) ── */}
            <div className="flex flex-col sm:flex-row gap-3 flex-1 sm:min-h-0">

                {/* Notes card */}
                <motion.div
                    variants={cardVariants}
                    className="flex flex-col flex-1 bg-white rounded-2xl border border-neutral-200 shadow-sm overflow-hidden"
                >
                    <div className="shrink-0 flex items-center gap-2 px-4 py-2 bg-neutral-50 border-b border-neutral-200">
                        <Landmark className="w-4 h-4 text-neutral-500" />
                        <span className="text-[10px] font-bold uppercase tracking-widest text-neutral-500">
                            Banknotes
                        </span>
                    </div>

                    <div className="flex flex-col flex-1 divide-y divide-neutral-100">
                        {NOTES.map(denom => (
                            <DenomRow
                                key={denom.value}
                                denom={denom}
                                value={quantities[denom.value]}
                                onChange={handleChange}
                                onStep={handleStep}
                                onKeyDown={handleKeyDown}
                                inputRef={el => { inputRefs.current[denom.value] = el; }}
                            />
                        ))}
                    </div>

                    <div className="shrink-0 flex items-center justify-between px-4 py-2 bg-neutral-50 border-t border-neutral-200">
                        <span className="text-[10px] font-bold uppercase tracking-widest text-neutral-400">Subtotal</span>
                        <span className="text-sm font-bold text-neutral-800 tabular-nums">{formatPKR(noteTotal)}</span>
                    </div>
                </motion.div>

                {/* Coins card */}
                <motion.div
                    variants={cardVariants}
                    className="flex flex-col w-full sm:w-72 sm:shrink-0 bg-white rounded-2xl border border-neutral-200 shadow-sm overflow-hidden"
                >
                    <div className="shrink-0 flex items-center gap-2 px-4 py-2 bg-neutral-50 border-b border-neutral-200">
                        <Coins className="w-4 h-4 text-neutral-500" />
                        <span className="text-[10px] font-bold uppercase tracking-widest text-neutral-500">
                            Coins
                        </span>
                    </div>

                    <div className="flex flex-col flex-1 divide-y divide-neutral-100">
                        {COINS.map(denom => (
                            <DenomRow
                                key={denom.value}
                                denom={denom}
                                value={quantities[denom.value]}
                                onChange={handleChange}
                                onStep={handleStep}
                                onKeyDown={handleKeyDown}
                                inputRef={el => { inputRefs.current[denom.value] = el; }}
                            />
                        ))}
                    </div>

                    <div className="shrink-0 flex items-center justify-between px-4 py-2 bg-neutral-50 border-t border-neutral-200">
                        <span className="text-[10px] font-bold uppercase tracking-widest text-neutral-400">Subtotal</span>
                        <span className="text-sm font-bold text-neutral-800 tabular-nums">{formatPKR(coinTotal)}</span>
                    </div>
                </motion.div>

            </div>
        </motion.div>
    );
}

// ── DenomRow ─────────────────────────────────────────────────────────────────
function DenomRow({ denom, value, onChange, onStep, onKeyDown, inputRef }) {
    const subtotal = denom.value * parseQty(value);
    const hasValue = value !== '' && subtotal > 0;

    return (
        <motion.div
            variants={rowVariants}
            className={`flex-1 flex items-center gap-2 px-3 py-2 transition-colors duration-150 min-h-0
                ${hasValue ? 'bg-primary-50/50' : 'bg-white hover:bg-neutral-50'}`}
        >
            {/* Denomination label */}
            <span className={`w-16 shrink-0 text-xs font-semibold
                ${hasValue ? 'text-primary-700' : 'text-neutral-600'}`}>
                {denom.label}
            </span>

            {/* × */}
            <span className="text-neutral-300 text-xs select-none shrink-0">×</span>

            {/* −  button */}
            <button
                tabIndex={-1}
                onClick={() => onStep(denom.value, -1)}
                className="shrink-0 w-6 h-6 rounded-md flex items-center justify-center
                           bg-neutral-100 hover:bg-rose-100 hover:text-rose-600
                           text-neutral-500 text-sm font-bold transition-colors duration-150 select-none"
            >
                −
            </button>

            {/* Quantity input */}
            <input
                ref={inputRef}
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                value={value}
                onChange={e => onChange(denom.value, e.target.value)}
                onKeyDown={e => onKeyDown(e, denom.value)}
                placeholder="0"
                className={`w-14 shrink-0 px-1 py-1 rounded-lg border text-xs font-semibold text-center
                            transition-all duration-200 outline-none
                    ${hasValue
                        ? 'border-primary-300 bg-white text-primary-700 ring-2 ring-primary-100'
                        : 'border-neutral-200 bg-neutral-50 text-neutral-700 focus:border-primary-400 focus:ring-2 focus:ring-primary-100 focus:bg-white'
                    }`}
            />

            {/* + button */}
            <button
                tabIndex={-1}
                onClick={() => onStep(denom.value, +1)}
                className="shrink-0 w-6 h-6 rounded-md flex items-center justify-center
                           bg-neutral-100 hover:bg-emerald-100 hover:text-emerald-600
                           text-neutral-500 text-sm font-bold transition-colors duration-150 select-none"
            >
                +
            </button>

            {/* = */}
            <span className="text-neutral-300 text-xs select-none shrink-0">=</span>

            {/* Per-row subtotal */}
            <span className={`flex-1 text-right text-xs font-semibold tabular-nums truncate
                ${hasValue ? 'text-primary-700' : 'text-neutral-300'}`}>
                {hasValue ? formatPKR(subtotal) : '—'}
            </span>
        </motion.div>
    );
}
