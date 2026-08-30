import { useState, useEffect, useCallback } from 'react';
import { TrendingUp, FileText, PlusCircle } from 'lucide-react';
import { dataEntryApi } from '../../services/dataEntryApi';
import { cashManagementApi } from '../../services/cashManagementApi';
import { extractErrorMessage } from '../../utils/errorMessage';
import { useToast } from '../../context/ToastContext';
import { getFieldError } from './fieldError';
import Card from '../ui/Card';
import Input from '../ui/Input';
import Button from '../ui/Button';
import SearchableSelect from '../ui/SearchableSelect';
import LoadingSpinner from '../ui/LoadingSpinner';
import InlineAlert from '../ui/InlineAlert';
import EmptyState from '../ui/EmptyState';
import Table from '../ui/Table';

const fmt = (v) => Number(v || 0).toFixed(2);

const OpeningInvestorInvestmentPanel = () => {
    const { toast } = useToast();
    const [selectedInvestorLabel, setSelectedInvestorLabel] = useState('');
    const [records, setRecords] = useState([]);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState('');
    const [saving, setSaving] = useState(false);
    const [form, setForm] = useState({ investor_id: '', amount: '', note: '' });
    const [fieldErrors, setFieldErrors] = useState({});
    const [bannerError, setBannerError] = useState('');

    const loadRecords = useCallback(async () => {
        try {
            const res = await dataEntryApi.openingInvestorInvestment.getAll({ page_size: 500 });
            setRecords(res?.results ?? res ?? []);
            setLoadError('');
        } catch (err) {
            setLoadError(extractErrorMessage(err, 'Failed to load opening investor investments.'));
        }
    }, []);

    useEffect(() => {
        (async () => {
            setLoading(true);
            try {
                await loadRecords();
            } finally {
                setLoading(false);
            }
        })();
    }, [loadRecords]);

    const searchInvestors = useCallback(async (query) => {
        const res = await cashManagementApi.investors.getAll({ search: query, page_size: 25 });
        const results = res?.results ?? res ?? [];
        return results.map(i => ({ value: i.id, label: i.name }));
    }, []);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setFieldErrors({}); setBannerError('');
        const errors = {};
        if (!form.investor_id) errors.investor = 'Please select an investor.';
        if (!form.amount || parseFloat(form.amount) <= 0) errors.amount = 'Amount must be greater than 0.';
        if (Object.keys(errors).length) {
            setFieldErrors(errors);
            return;
        }
        setSaving(true);
        try {
            await dataEntryApi.openingInvestorInvestment.create({
                investor_id: parseInt(form.investor_id),
                amount: form.amount,
                note: form.note,
            });
            toast.success('Opening investor investment recorded.');
            setForm({ investor_id: '', amount: '', note: '' });
            setSelectedInvestorLabel('');
            await loadRecords();
        } catch (err) {
            const investorErr = getFieldError(err, 'investor_id', 'investor');
            const amountErr = getFieldError(err, 'amount');
            const noteErr = getFieldError(err, 'note');
            if (investorErr || amountErr || noteErr) {
                setFieldErrors({ investor: investorErr, amount: amountErr, note: noteErr });
            } else {
                setBannerError(extractErrorMessage(err, 'Failed to record investment.'));
            }
        } finally {
            setSaving(false);
        }
    };

    const columns = [
        { key: 'investor_name', label: 'Investor' },
        { key: 'amount', label: 'Amount', render: (v) => <span className="font-medium text-neutral-900">{fmt(v)}</span> },
        { key: 'note', label: 'Note', render: (v) => v || '—' },
        { key: 'created_at', label: 'Date', render: (v) => new Date(v).toLocaleDateString() },
    ];

    if (loading) {
        return <div className="flex justify-center py-16"><LoadingSpinner size="lg" /></div>;
    }

    return (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card hover={false}>
                <div className="flex items-center gap-3 mb-3">
                    <div className="w-10 h-10 rounded-xl bg-primary-50 flex items-center justify-center flex-shrink-0">
                        <TrendingUp className="w-5 h-5 text-primary-600" />
                    </div>
                    <h3 className="font-semibold text-neutral-900">New Opening Investor Investment</h3>
                </div>
                <p className="text-sm text-neutral-500 mb-4">
                    For capital an investor put in before this system existed — added to their
                    invested stake, but <span className="font-medium text-neutral-700">not</span> to Cash in Hand
                    (that cash isn't actually sitting in the till right now).
                </p>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <SearchableSelect
                        label="Investor"
                        value={form.investor_id}
                        selectedLabel={selectedInvestorLabel}
                        onChange={(v, option) => {
                            setForm(f => ({ ...f, investor_id: v }));
                            setSelectedInvestorLabel(option?.label ?? '');
                        }}
                        onSearch={searchInvestors}
                        placeholder="Search investor..."
                        error={fieldErrors.investor}
                        required
                    />
                    <Input
                        label="Investment Amount (PKR)"
                        type="number" step="0.01" min="0.01"
                        value={form.amount}
                        onChange={(e) => setForm(f => ({ ...f, amount: e.target.value }))}
                        placeholder="Amount already invested by this investor"
                        error={fieldErrors.amount}
                        required
                    />
                    <Input
                        label="Note (optional)"
                        value={form.note}
                        onChange={(e) => setForm(f => ({ ...f, note: e.target.value }))}
                        placeholder="Reference / remarks"
                        error={fieldErrors.note}
                    />
                    {bannerError && <InlineAlert variant="error" message={bannerError} />}
                    <Button type="submit" loading={saving} icon={PlusCircle} className="w-full sm:w-auto">
                        Record Investment
                    </Button>
                </form>
            </Card>

            <Card hover={false}>
                <div className="flex items-center gap-3 mb-5">
                    <div className="w-10 h-10 rounded-xl bg-neutral-100 flex items-center justify-center flex-shrink-0">
                        <FileText className="w-5 h-5 text-neutral-500" />
                    </div>
                    <h3 className="font-semibold text-neutral-900">Recorded ({records.length})</h3>
                </div>
                {loadError && <InlineAlert variant="error" message={loadError} onRetry={loadRecords} className="mb-4" />}
                {records.length === 0 ? (
                    <EmptyState
                        title="No opening investor investments yet"
                        description="Recorded investments will appear here for audit."
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

export default OpeningInvestorInvestmentPanel;
