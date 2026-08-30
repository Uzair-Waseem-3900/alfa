import { useState } from 'react';
import { Navigate } from 'react-router-dom';
import { Plus, Trash2, ArrowLeftRight } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import {
    useAccountTransfers, usePaymentMethods, useCreateTransfer, useDeleteTransfer,
} from '../../hooks/usePaymentMethods';
import { extractErrorMessage } from '../../utils/errorMessage';
import { todayLocalDate } from '../../utils/helpers';
import Button from '../../components/ui/Button';
import Modal from '../../components/ui/Modal';
import Input from '../../components/ui/Input';
import Select from '../../components/ui/Select';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Table from '../../components/ui/Table';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import Pagination from '../../components/ui/Pagination';
import BackLink from '../../components/ui/BackLink';
import EmptyState from '../../components/ui/EmptyState';
import InlineAlert from '../../components/ui/InlineAlert';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

// Errors from the transfer endpoint can land under "splits" instead of a
// field name a form would expect ("amount"/"from_method") — the insufficient
// balance message specifically comes back keyed "splits" per the API
// contract, so it's checked for explicitly before falling back to the
// generic extractor.
const extractTransferError = (error, fallback) => {
    const data = error?.response?.data;
    if (data?.splits) {
        return Array.isArray(data.splits) ? data.splits[0] : data.splits;
    }
    return extractErrorMessage(error, fallback);
};

const AccountTransfersPage = () => {
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const {
        data: transfers, meta, page, setPage, loading, error: listError, refetch,
    } = useAccountTransfers();
    const { data: methods, loading: methodsLoading } = usePaymentMethods();
    const { create, mutating: creating } = useCreateTransfer();
    const { delete: deleteTransfer, mutating: deleting } = useDeleteTransfer();

    const [showModal, setShowModal] = useState(false);
    const [formData, setFormData] = useState({
        from_method: '', to_method: '', amount: '', date: todayLocalDate(), note: '',
    });
    const [formError, setFormError] = useState('');
    const [deleteConfirm, setDeleteConfirm] = useState(null);

    if (!isAdmin) {
        return <Navigate to="/dashboard" replace />;
    }

    const resetForm = () => {
        setFormData({ from_method: '', to_method: '', amount: '', date: todayLocalDate(), note: '' });
        setFormError('');
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setFormError('');
        try {
            await create({
                from_method: Number(formData.from_method),
                to_method: Number(formData.to_method),
                amount: formData.amount,
                date: formData.date,
                note: formData.note || undefined,
            });
            toast.success('Transfer completed');
            setShowModal(false);
            resetForm();
            await refetch();
        } catch (error) {
            setFormError(extractTransferError(error, 'Failed to create transfer'));
        }
    };

    const handleDelete = async (id) => {
        try {
            await deleteTransfer(id);
            setDeleteConfirm(null);
            if (transfers.length === 1 && page > 1) {
                setPage(page - 1);
            } else {
                await refetch();
            }
            toast.success('Transfer reversed');
        } catch (error) {
            toast.error(extractTransferError(error, 'Failed to reverse transfer'));
        }
    };

    const methodOptions = (methods || []).map((m) => ({ value: m.id, label: m.name }));

    const columns = [
        { key: 'date', label: 'Date', render: (v) => new Date(v).toLocaleDateString() },
        { key: 'from_method_name', label: 'From' },
        { key: 'to_method_name', label: 'To' },
        {
            key: 'amount',
            label: 'Amount (PKR)',
            render: (v) => <span className="font-semibold text-primary-700">Rs. {fmt(v)}</span>,
        },
        { key: 'note', label: 'Note', render: (v) => v || <span className="text-neutral-300">—</span> },
        {
            key: 'actions',
            label: 'Actions',
            width: '90px',
            render: (_v, row) => (
                <button
                    onClick={(e) => { e.stopPropagation(); setDeleteConfirm(row); }}
                    className="inline-flex items-center justify-center w-9 h-9 rounded-lg text-error-600 hover:bg-error-50 transition-colors"
                    aria-label="Reverse transfer"
                >
                    <Trash2 className="w-4 h-4" />
                </button>
            ),
        },
    ];

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <BackLink to="/payment-methods">Back to Payment Methods</BackLink>
                    <div className="flex items-center gap-2.5 mt-2">
                        <ArrowLeftRight className="w-6 h-6 text-primary-600" />
                        <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900">Account Transfers</h1>
                    </div>
                    <p className="text-neutral-500 mt-1">Move balance between payment methods</p>
                </div>
                <Button onClick={() => { resetForm(); setShowModal(true); }} icon={Plus} disabled={methodsLoading}>
                    New Transfer
                </Button>
            </div>

            {listError && !loading && (
                <InlineAlert variant="error" title="Couldn't load transfers" message={listError} onRetry={refetch} />
            )}

            {loading ? (
                <div className="flex items-center justify-center py-16">
                    <LoadingSpinner size="lg" />
                </div>
            ) : transfers.length === 0 ? (
                <EmptyState
                    title="No Transfers Yet"
                    description="Move balance between payment methods to see transfers here."
                />
            ) : (
                <>
                    <Table columns={columns} data={transfers} />
                    {meta.totalPages > 1 && (
                        <Pagination currentPage={meta.currentPage} totalPages={meta.totalPages} onPageChange={setPage} />
                    )}
                </>
            )}

            <Modal
                isOpen={showModal}
                onClose={() => { setShowModal(false); resetForm(); }}
                title="New Transfer"
                size="lg"
            >
                <form onSubmit={handleSubmit} className="space-y-4">
                    <Select
                        label="From Method"
                        value={formData.from_method}
                        onChange={(e) => setFormData({ ...formData, from_method: e.target.value })}
                        options={methodOptions}
                        required
                    />
                    <Select
                        label="To Method"
                        value={formData.to_method}
                        onChange={(e) => setFormData({ ...formData, to_method: e.target.value })}
                        options={methodOptions}
                        required
                    />
                    <Input
                        label="Amount (PKR)"
                        type="number"
                        step="0.01"
                        min="0.01"
                        value={formData.amount}
                        onChange={(e) => setFormData({ ...formData, amount: e.target.value })}
                        placeholder="Enter amount"
                        required
                    />
                    <Input
                        label="Date"
                        type="date"
                        value={formData.date}
                        onChange={(e) => setFormData({ ...formData, date: e.target.value })}
                        required
                    />
                    <Input
                        label="Note"
                        value={formData.note}
                        onChange={(e) => setFormData({ ...formData, note: e.target.value })}
                        placeholder="Optional"
                    />

                    {formError && <InlineAlert variant="error" message={formError} />}

                    <div className="flex justify-end gap-3 pt-4">
                        <Button type="button" variant="secondary" onClick={() => { setShowModal(false); resetForm(); }}>
                            Cancel
                        </Button>
                        <Button type="submit" loading={creating}>
                            Transfer
                        </Button>
                    </div>
                </form>
            </Modal>

            <ConfirmDialog
                isOpen={!!deleteConfirm}
                onClose={() => setDeleteConfirm(null)}
                onConfirm={() => handleDelete(deleteConfirm?.id)}
                title="Reverse Transfer"
                message={`Are you sure you want to reverse this Rs. ${fmt(deleteConfirm?.amount)} transfer from "${deleteConfirm?.from_method_name}" to "${deleteConfirm?.to_method_name}"?`}
                loading={deleting}
            />
        </div>
    );
};

export default AccountTransfersPage;
