import { useState } from 'react';
import { Play, Square, ListChecks } from 'lucide-react';
import { useRecovery } from '../../hooks/useBilling';
import { useToast } from '../../context/ToastContext';
import { extractErrorMessage } from '../../utils/errorMessage';
import RecoveryDetailsModal from './RecoveryDetailsModal';
import Card from '../ui/Card';
import Button from '../ui/Button';
import InlineAlert from '../ui/InlineAlert';
import ConfirmDialog from '../ui/ConfirmDialog';

const formatAmount = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : value;
    return isNaN(num) ? '0.00' : num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

// Start/Stop Recovery controls + running total. Fetches its own status, so it
// never blocks or delays the invoice list around it. Render for admin and
// superuser only (the backend enforces it too).
//
// Mobile-first: everything stacks in one column on phones (full-width,
// 44px-tall buttons; the total gets its own row so a large figure never
// overflows), and opens up to side-by-side layouts from `sm`/`lg` upward.
const RecoveryPanel = () => {
    const { toast } = useToast();
    const { data, loading, error, mutating, refetch, start, stop } = useRecovery();
    const [showDetails, setShowDetails] = useState(false);
    const [confirmStop, setConfirmStop] = useState(false);

    const handleStart = async () => {
        try {
            await start();
            toast.success('Recovery started. Invoice payments are now being recorded.');
        } catch (err) {
            toast.error(extractErrorMessage(err, 'Failed to start recovery.'));
        }
    };

    const handleStop = async () => {
        try {
            await stop();
            setConfirmStop(false);
            setShowDetails(false);
            toast.success('Recovery stopped and recovery records cleared.');
        } catch (err) {
            toast.error(extractErrorMessage(err, 'Failed to stop recovery.'));
        }
    };

    // Payments can be recorded from other pages, so refresh the numbers when
    // the details are opened.
    const openDetails = () => {
        refetch();
        setShowDetails(true);
    };

    return (
        <>
        <Card hover={false} className="!p-4 sm:!p-5">
            {error ? (
                <InlineAlert variant="error" message={error} onRetry={refetch} />
            ) : loading && !data ? (
                <div className="animate-pulse space-y-2" aria-busy="true" aria-label="Loading recovery status">
                    <div className="h-3 w-32 max-w-full rounded bg-neutral-200" />
                    <div className="h-7 w-48 max-w-full rounded bg-neutral-200" />
                </div>
            ) : data?.is_active ? (
                <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                    <div className="min-w-0">
                        <div className="flex items-center gap-2">
                            <span className="inline-block w-2.5 h-2.5 rounded-full bg-success-500 animate-pulse flex-shrink-0" aria-hidden="true" />
                            <p className="text-sm font-semibold text-success-700">Recovery in progress</p>
                        </div>
                        {data.started_at && (
                            <p className="text-xs text-neutral-500 mt-0.5 ml-[18px]">
                                Since {new Date(data.started_at).toLocaleString()}
                            </p>
                        )}

                        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-10">
                            <div className="min-w-0">
                                <p className="text-sm text-neutral-500">Total recovered</p>
                                <p className="text-2xl font-bold text-neutral-900 tabular-nums break-words">
                                    Rs. {formatAmount(data.total_amount)}
                                </p>
                            </div>
                            <div className="min-w-0">
                                <p className="text-sm text-neutral-500">Payments recorded</p>
                                <p className="text-2xl font-bold text-neutral-900 tabular-nums">
                                    {data.record_count.toLocaleString()}
                                </p>
                            </div>
                        </div>
                    </div>

                    <div className="flex flex-col gap-3 sm:flex-row lg:flex-shrink-0">
                        <Button variant="secondary" icon={ListChecks} onClick={openDetails} className="w-full sm:w-auto">
                            View Details
                        </Button>
                        <Button
                            variant="danger"
                            icon={Square}
                            onClick={() => setConfirmStop(true)}
                            disabled={mutating}
                            className="w-full sm:w-auto"
                        >
                            Stop Recovery
                        </Button>
                    </div>
                </div>
            ) : (
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0">
                        <p className="font-semibold text-neutral-900">Payment Recovery</p>
                        <p className="text-sm text-neutral-500">
                            Start recovery to record every invoice payment received from now on.
                        </p>
                    </div>
                    <Button icon={Play} onClick={handleStart} loading={mutating} className="w-full sm:w-auto sm:flex-shrink-0">
                        Start Recovery
                    </Button>
                </div>
            )}
        </Card>

        {/* Outside the Card: it is an animated element, and a transformed
            ancestor would break the dialogs' position: fixed overlay. */}
        <RecoveryDetailsModal
            isOpen={showDetails}
            onClose={() => setShowDetails(false)}
            total={data?.total_amount ?? '0'}
            count={data?.record_count ?? 0}
        />

        <ConfirmDialog
            isOpen={confirmStop}
            onClose={() => setConfirmStop(false)}
            onConfirm={handleStop}
            title="Stop Recovery"
            message={`This will clear ${data?.record_count ?? 0} recovery record(s) totalling Rs. ${formatAmount(data?.total_amount)}. The invoice payments themselves are not affected.`}
            confirmText="Stop & Clear"
            variant="danger"
            loading={mutating}
        />
        </>
    );
};

export default RecoveryPanel;
