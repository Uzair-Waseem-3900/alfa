import { useState, useEffect, useCallback, useMemo } from 'react';
import { Truck, FileText, PlusCircle } from 'lucide-react';
import { dataEntryApi } from '../../services/dataEntryApi';
import { purchasesApi } from '../../services/purchasesApi';
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

const SupplierOpeningBalancePanel = () => {
    const { toast } = useToast();
    const [selectedSupplierLabel, setSelectedSupplierLabel] = useState('');
    const [records, setRecords] = useState([]);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState('');
    const [saving, setSaving] = useState(false);
    const [form, setForm] = useState({ supplier_id: '', amount: '', note: '' });
    const [fieldErrors, setFieldErrors] = useState({});
    const [bannerError, setBannerError] = useState('');

    const loadRecords = useCallback(async () => {
        try {
            const res = await dataEntryApi.supplierOpeningBalance.getAll({ page_size: 500 });
            setRecords(res?.results ?? res ?? []);
            setLoadError('');
        } catch (err) {
            setLoadError(extractErrorMessage(err, 'Failed to load supplier opening balances.'));
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

    const usedSupplierIds = useMemo(() => new Set(records.map(r => r.supplier)), [records]);

    const searchSuppliers = useCallback(async (query) => {
        const res = await purchasesApi.suppliers.getAll({ search: query });
        const results = res?.results ?? res ?? [];
        return results
            .filter(s => !usedSupplierIds.has(s.id))
            .map(s => ({ value: s.id, label: `${s.name} (${s.code})` }));
    }, [usedSupplierIds]);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setFieldErrors({}); setBannerError('');
        const errors = {};
        if (!form.supplier_id) errors.supplier = 'Please select a supplier.';
        if (!form.amount || parseFloat(form.amount) <= 0) errors.amount = 'Amount must be greater than 0.';
        if (Object.keys(errors).length) {
            setFieldErrors(errors);
            return;
        }
        setSaving(true);
        try {
            await dataEntryApi.supplierOpeningBalance.create({
                supplier_id: parseInt(form.supplier_id),
                amount: form.amount,
                note: form.note,
            });
            toast.success('Supplier opening balance recorded.');
            setForm({ supplier_id: '', amount: '', note: '' });
            setSelectedSupplierLabel('');
            await loadRecords();
        } catch (err) {
            const supplierErr = getFieldError(err, 'supplier_id', 'supplier');
            const amountErr = getFieldError(err, 'amount');
            const noteErr = getFieldError(err, 'note');
            if (supplierErr || amountErr || noteErr) {
                setFieldErrors({ supplier: supplierErr, amount: amountErr, note: noteErr });
            } else {
                setBannerError(extractErrorMessage(err, 'Failed to record opening balance.'));
            }
        } finally {
            setSaving(false);
        }
    };

    const columns = [
        {
            key: 'supplier_name', label: 'Supplier', render: (v, row) => (
                <span>{v} <span className="text-neutral-400">({row.supplier_code})</span></span>
            ),
        },
        { key: 'amount', label: 'Amount', render: (v) => <span className="font-medium text-neutral-900">{fmt(v)}</span> },
        { key: 'order_number', label: 'Order', render: (v) => v || '—' },
        { key: 'created_at', label: 'Date', render: (v) => new Date(v).toLocaleDateString() },
    ];

    if (loading) {
        return <div className="flex justify-center py-16"><LoadingSpinner size="lg" /></div>;
    }

    return (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card hover={false}>
                <div className="flex items-center gap-3 mb-5">
                    <div className="w-10 h-10 rounded-xl bg-primary-50 flex items-center justify-center flex-shrink-0">
                        <Truck className="w-5 h-5 text-primary-600" />
                    </div>
                    <h3 className="font-semibold text-neutral-900">New Supplier Opening Balance</h3>
                </div>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <SearchableSelect
                        label="Supplier"
                        value={form.supplier_id}
                        selectedLabel={selectedSupplierLabel}
                        onChange={(v, option) => {
                            setForm(f => ({ ...f, supplier_id: v }));
                            setSelectedSupplierLabel(option?.label ?? '');
                        }}
                        onSearch={searchSuppliers}
                        placeholder="Search supplier..."
                        error={fieldErrors.supplier}
                        required
                    />
                    <Input
                        label="Opening Balance Amount (PKR)"
                        type="number" step="0.01" min="0.01"
                        value={form.amount}
                        onChange={(e) => setForm(f => ({ ...f, amount: e.target.value }))}
                        placeholder="Amount we owe this supplier"
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
                        Record Opening Balance
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
                        title="No supplier opening balances yet"
                        description="Recorded balances will appear here for audit."
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

export default SupplierOpeningBalancePanel;
