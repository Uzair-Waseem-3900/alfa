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
                    <div className="h-3 w-32 rounded bg-neutral-200" />
                    <div className="h-7 w-48 rounded bg-neutral-200" />
                </div>
            ) : data?.is_active ? (
                <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                    <div className="flex flex-col sm:flex-row gap-4 sm:gap-10">
                        <div>
                            <p className="text-sm text-neutral-500">
                                Recovery in progress
                                {data.started_at && ` · since ${new Date(data.started_at).toLocaleString()}`}
                            </p>
                            <p className="text-2xl font-bold text-neutral-900">Rs. {formatAmount(data.total_amount)}</p>
                        </div>
                        <div>
                            <p className="text-sm text-neutral-500">Payments recorded</p>
                            <p className="text-2xl font-bold text-neutral-900">{data.record_count.toLocaleString()}</p>
                        </div>
                    </div>
                    <div className="flex flex-col sm:flex-row gap-3">
                        <Button variant="secondary" icon={ListChecks} onClick={openDetails}>
                            View Details
                        </Button>
                        <Button variant="danger" icon={Square} onClick={() => setConfirmStop(true)} disabled={mutating}>
                            Stop Recovery
                        </Button>
                    </div>
                </div>
            ) : (
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div>
                        <p className="font-semibold text-neutral-900">Payment Recovery</p>
                        <p className="text-sm text-neutral-500">
                            Start recovery to record every invoice payment received from now on.
                        </p>
                    </div>
                    <Button icon={Play} onClick={handleStart} loading={mutating}>
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
