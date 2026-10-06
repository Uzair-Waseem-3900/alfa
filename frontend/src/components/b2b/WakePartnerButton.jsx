import { useEffect, useRef, useState } from 'react';
import PropTypes from 'prop-types';
import { Power, X } from 'lucide-react';
import Button from '../ui/Button';
import { useToast } from '../../context/ToastContext';

// The browser only starts waking a partner when the user presses this button. It asks OUR
// backend (which makes one 5-second readiness check of the partner) every few seconds, for
// at most 90 seconds. Nothing in the database changes while waking.
const WAKE_MAX_MS = 90000;
const POLL_EVERY_MS = 3000;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const WakePartnerButton = ({ partnerLabel, wake, onAwake, className = '' }) => {
    const { toast } = useToast();
    const [phase, setPhase] = useState('idle'); // idle | waking | awake | failed | refused
    const [elapsed, setElapsed] = useState(0);
    const [detail, setDetail] = useState('');
    const runId = useRef(0);

    // Leaving the page stops the loop.
    useEffect(() => () => { runId.current += 1; }, []);

    const start = async () => {
        runId.current += 1;
        const me = runId.current;
        const startedAt = Date.now();
        setPhase('waking');
        setElapsed(0);
        setDetail('');
        const ticker = setInterval(() => {
            if (runId.current === me) setElapsed(Math.round((Date.now() - startedAt) / 1000));
        }, 1000);
        try {
            while (runId.current === me && Date.now() - startedAt < WAKE_MAX_MS) {
                let result;
                try {
                    result = await wake();
                } catch {
                    result = { awake: false, reason: 'asleep' };
                }
                if (runId.current !== me) return;
                if (result?.awake) {
                    setPhase('awake');
                    toast.success(`${partnerLabel} is awake`);
                    if (onAwake) onAwake();
                    return;
                }
                if (result?.reason === 'not_configured') {
                    // Waiting cannot help: the partner answered but refused this connection.
                    setPhase('refused');
                    setDetail(result.detail || '');
                    return;
                }
                await sleep(POLL_EVERY_MS);
            }
            if (runId.current === me) setPhase('failed');
        } finally {
            clearInterval(ticker);
        }
    };

    const stop = () => {
        runId.current += 1;
        setPhase('idle');
    };

    return (
        <div className={className}>
            {phase === 'waking' ? (
                <div className="flex flex-wrap items-center gap-3">
                    <Button variant="secondary" icon={X} onClick={stop}>
                        Stop
                    </Button>
                    <span role="status" aria-live="polite" className="text-sm text-neutral-600">
                        Waking up {partnerLabel}… {elapsed}s (waits up to 90s)
                    </span>
                </div>
            ) : (
                <Button variant="secondary" icon={Power} onClick={start}>
                    Wake up {partnerLabel}
                </Button>
            )}
            {phase === 'awake' && (
                <p role="status" className="text-sm text-success-600 mt-1.5">{partnerLabel} is awake.</p>
            )}
            {phase === 'failed' && (
                <p role="alert" className="text-sm text-error-600 mt-1.5">
                    {partnerLabel} did not answer within 90 seconds. Nothing was changed — you can try again.
                </p>
            )}
            {phase === 'refused' && (
                <p role="alert" className="text-sm text-error-600 mt-1.5">
                    {detail || `${partnerLabel} did not accept this connection. Check the shared secret, company name and address on both sides.`}
                </p>
            )}
        </div>
    );
};

WakePartnerButton.propTypes = {
    partnerLabel: PropTypes.string.isRequired,
    wake: PropTypes.func.isRequired,
    onAwake: PropTypes.func,
    className: PropTypes.string,
};

export default WakePartnerButton;
