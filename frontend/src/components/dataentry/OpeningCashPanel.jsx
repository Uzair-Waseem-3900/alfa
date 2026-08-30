import { useState, useEffect, useCallback } from 'react';
import { Wallet, Info, Banknote } from 'lucide-react';
import { dataEntryApi } from '../../services/dataEntryApi';
import { extractErrorMessage } from '../../utils/errorMessage';
import { useToast } from '../../context/ToastContext';
import { getFieldError } from './fieldError';
import Card from '../ui/Card';
import Input from '../ui/Input';
import Button from '../ui/Button';
import LoadingSpinner from '../ui/LoadingSpinner';
import InlineAlert from '../ui/InlineAlert';
import EmptyState from '../ui/EmptyState';
import Table from '../ui/Table';

const fmt = (v) => Number(v || 0).toFixed(2);

const OpeningCashPanel = () => {
    const { toast } = useToast();
    const [records, setRecords] = useState([]);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState('');
    const [saving, setSaving] = useState(false);
    const [amount, setAmount] = useState('');
    const [amountError, setAmountError] = useState('');
    const [bannerError, setBannerError] = useState('');

    const loadRecords = useCallback(async () => {
        try {
            const res = await dataEntryApi.openingCash.getAll({ page_size: 500 });
            setRecords(res?.results ?? res ?? []);
            setLoadError('');
        } catch (err) {
            setLoadError(extractErrorMessage(err, 'Failed to load opening cash entries.'));
        }
    }, []);

    useEffect(() => {
        (async () => { setLoading(true); await loadRecords(); setLoading(false); })();
    }, [loadRecords]);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setAmountError(''); setBannerError('');
        if (!amount || parseFloat(amount) <= 0) {
            setAmountError('Amount must be greater than 0.');
            return;
        }
        setSaving(true);
        try {
            await dataEntryApi.openingCash.create({ amount });
            toast.success('Opening cash added to cash in hand.');
            setAmount('');
            await loadRecords();
        } catch (err) {
            const amtErr = getFieldError(err, 'amount');
            if (amtErr) {
                setAmountError(amtErr);
            } else {
                setBannerError(extractErrorMessage(err, 'Failed to add opening cash.'));
            }
        } finally {
            setSaving(false);
        }
    };

    const total = records.reduce((sum, r) => sum + Number(r.amount || 0), 0);

    const columns = [
        { key: 'amount', label: 'Amount', render: (v) => <span className="font-medium text-neutral-900">{fmt(v)}</span> },
        { key: 'added_by', label: 'Added By', render: (v) => v || '—' },
        { key: 'added_at', label: 'Date', render: (v) => new Date(v).toLocaleString() },
    ];

    if (loading) {
        return <div className="flex justify-center py-16"><LoadingSpinner size="lg" /></div>;
    }

    return (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card hover={false}>
                <div className="flex items-center gap-3 mb-5">
                    <div className="w-10 h-10 rounded-xl bg-primary-50 flex items-center justify-center flex-shrink-0">
                        <Wallet className="w-5 h-5 text-primary-600" />
                    </div>
                    <h3 className="font-semibold text-neutral-900">Add Opening Cash</h3>
                </div>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <Input
                        label="Amount (PKR)"
                        type="number" step="0.01" min="0.01"
                        value={amount}
                        onChange={(e) => setAmount(e.target.value)}
                        placeholder="Cash to add to cash in hand"
                        error={amountError}
                        required
                    />
                    <InlineAlert
                        variant="info"
                        message="Adds directly to cash in hand. Can be used multiple times."
                    />
                    {bannerError && <InlineAlert variant="error" message={bannerError} />}
                    <Button type="submit" loading={saving} icon={Banknote} className="w-full sm:w-auto">
                        Add Opening Cash
                    </Button>
                </form>
            </Card>

            <Card hover={false}>
                <div className="flex items-center justify-between mb-5 gap-3 flex-wrap">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-neutral-100 flex items-center justify-center flex-shrink-0">
                            <Info className="w-5 h-5 text-neutral-500" />
                        </div>
                        <h3 className="font-semibold text-neutral-900">Recorded ({records.length})</h3>
                    </div>
                    <span className="text-sm text-neutral-500">
                        Total: <span className="font-semibold text-neutral-900">PKR {fmt(total)}</span>
                    </span>
                </div>
                {loadError && <InlineAlert variant="error" message={loadError} onRetry={loadRecords} className="mb-4" />}
                {records.length === 0 ? (
                    <EmptyState
                        title="No opening cash entries yet"
                        description="Entries you add will appear here for audit."
                    />
                ) : (
                    <div className="max-h-[420px] overflow-y-auto">
                        <Table columns={columns} data={records} />
                    </div>
                )}
            </Card>
        </div>
    );
};

export default OpeningCashPanel;
