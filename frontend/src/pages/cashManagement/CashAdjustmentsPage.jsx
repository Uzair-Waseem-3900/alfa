import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Trash2, Scale, SlidersHorizontal } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { useCashManagementStats, useCashAdjustments } from '../../hooks/useCashManagement';
import { extractErrorMessage } from '../../utils/errorMessage';
import { todayLocalDate } from '../../utils/helpers';
import MethodSplitPicker, { isSplitBalanced } from '../../components/paymentMethods/MethodSplitPicker';
import BackLink from '../../components/ui/BackLink';
import Button from '../../components/ui/Button';
import Modal from '../../components/ui/Modal';
import Input from '../../components/ui/Input';
import Select from '../../components/ui/Select';
import Badge from '../../components/ui/Badge';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Table from '../../components/ui/Table';
import FilterBar from '../../components/ui/FilterBar';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import Pagination from '../../components/ui/Pagination';
import EmptyState from '../../components/ui/EmptyState';
import InlineAlert from '../../components/ui/InlineAlert';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const formatAllocations = (allocations) => {
    if (!allocations || allocations.length === 0) return <span className="text-neutral-300">—</span>;
    return allocations.map((a) => `${a.payment_method_name} (Rs. ${fmt(a.amount)})`).join(', ');
};

const CashAdjustmentsPage = () => {
    const { user } = useAuth();
    const { toast } = useToast();
    const navigate = useNavigate();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const {
        data: adjustments, meta, page, setPage, loading, error: listError,
        filters, setFilters, refetch, create, delete: deleteAdjustment,
    } = useCashAdjustments();
    const { refetch: refetchStats } = useCashManagementStats();

    const [showModal, setShowModal] = useState(false);
    const [formData, setFormData] = useState({
        amount: '',
        adjustment_type: 'lost',
        adjustment_date: todayLocalDate(),
        reason: '',
        method_allocations: [],
    });
    const [formLoading, setFormLoading] = useState(false);
    const [formError, setFormError] = useState('');
    const [splitError, setSplitError] = useState('');
    const [deleteConfirm, setDeleteConfirm] = useState(null);
    const [deleteLoading, setDeleteLoading] = useState(false);
    const [showFilters, setShowFilters] = useState(false);

    const resetForm = () => {
        setFormData({
            amount: '', adjustment_type: 'lost',
            adjustment_date: todayLocalDate(), reason: '', method_allocations: [],
        });
        setFormError('');
        setSplitError('');
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setFormError('');
        setSplitError('');
        setFormLoading(true);
        try {
            await create({ ...formData, amount: parseFloat(formData.amount) });
            setShowModal(false);
            resetForm();
            refetch();
            refetchStats();
            toast.success('Cash adjustment recorded successfully');
        } catch (error) {
            const fieldSplitError = error.response?.data?.method_allocations?.[0] || error.response?.data?.splits?.[0];
            if (fieldSplitError) {
                setSplitError(fieldSplitError);
            } else {
                setFormError(extractErrorMessage(error, 'Failed to record cash adjustment'));
            }
        } finally {
            setFormLoading(false);
        }
    };

    const handleDelete = async (id) => {
        setDeleteLoading(true);
        try {
            await deleteAdjustment(id);
            setDeleteConfirm(null);
            refetch();
            refetchStats();
            toast.success('Cash adjustment deleted and cash in hand restored');
        } catch (error) {
            toast.error(extractErrorMessage(error, 'Failed to delete cash adjustment'));
        } finally {
            setDeleteLoading(false);
        }
    };

    const handleApplyFilters = (values) => setFilters(values);
    const handleResetFilters = () => setFilters({});
    const handleRowClick = (row) => navigate(`/cash-management/adjustments/${row.id}`);

    const filterConfig = [
        { name: 'adjustment_type', label: 'Type', type: 'select', options: [
            { value: '', label: 'All' },
            { value: 'lost', label: 'Lost' },
            { value: 'found', label: 'Found' },
        ] },
        { name: 'date_from', label: 'Date From', type: 'date' },
        { name: 'date_to', label: 'Date To', type: 'date' },
        { name: 'min_amount', label: 'Min Amount', type: 'number' },
        { name: 'max_amount', label: 'Max Amount', type: 'number' },
    ];

    const columns = [
        {
            key: 'adjustment_date',
            label: 'Date',
            render: (value) => new Date(value).toLocaleDateString(),
        },
        {
            key: 'adjustment_type',
            label: 'Type',
            render: (value) => value === 'lost'
                ? <Badge variant="error" size="sm">Lost</Badge>
                : <Badge variant="success" size="sm">Found</Badge>,
        },
        {
            key: 'amount',
            label: 'Amount (PKR)',
            render: (value, row) => (
                <span className={`font-semibold ${row.adjustment_type === 'lost' ? 'text-error-600' : 'text-success-600'}`}>
                    Rs. {fmt(value)}
                </span>
            ),
        },
        { key: 'reason', label: 'Reason', render: (value) => value || <span className="text-neutral-300">—</span> },
        { key: 'allocations', label: 'Method', render: (value) => formatAllocations(value) },
        { key: 'created_by', label: 'Recorded By', render: (value) => value || 'N/A' },
        {
            key: 'actions',
            label: 'Actions',
            width: '90px',
            render: (_value, row) => (
                <button
                    onClick={(e) => { e.stopPropagation(); setDeleteConfirm(row); }}
                    className="inline-flex items-center justify-center w-9 h-9 rounded-lg text-error-600 hover:bg-error-50 transition-colors"
                    aria-label="Delete adjustment"
                >
                    <Trash2 className="w-4 h-4" />
                </button>
            ),
        },
    ];

    if (!isAdmin) {
        return (
            <div className="text-center py-16">
                <h2 className="text-2xl font-semibold text-neutral-900">Access Denied</h2>
                <p className="text-neutral-500 mt-2">Only admins or superusers can view cash adjustments.</p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <BackLink to="/cash-management">Back to Cash Management</BackLink>
                    <div className="flex items-center gap-2.5 mt-2">
                        <Scale className="w-6 h-6 text-primary-600" />
                        <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900">Cash Adjustments</h1>
                    </div>
                    <p className="text-neutral-500 mt-1">Lost and found/recovered cash entries</p>
                </div>
                <Button onClick={() => { resetForm(); setShowModal(true); }} icon={Plus}>
                    Record Adjustment
                </Button>
            </div>

            <div className="space-y-4">
                <div className="flex gap-3">
                    <Button variant="secondary" size="sm" icon={SlidersHorizontal} onClick={() => setShowFilters(!showFilters)}>
                        {showFilters ? 'Hide Filters' : 'Show Filters'}
                    </Button>
                    {Object.keys(filters).length > 0 && (
                        <Button variant="secondary" size="sm" onClick={handleResetFilters}>Clear Filters</Button>
                    )}
                </div>
                {showFilters && (
                    <FilterBar filters={filterConfig} onApply={handleApplyFilters} onReset={handleResetFilters} />
                )}
            </div>

            {listError && !loading && (
                <InlineAlert variant="error" title="Couldn't load cash adjustments" message={listError} onRetry={refetch} />
            )}

            {loading ? (
                <div className="flex items-center justify-center py-16">
                    <LoadingSpinner size="lg" />
                </div>
            ) : adjustments.length === 0 ? (
                <EmptyState
                    icon={<Scale className="w-8 h-8 text-neutral-400 mx-auto" />}
                    title="No Cash Adjustments Recorded Yet"
                    description="Record one when physical cash doesn't match what the system expects."
                />
            ) : (
                <>
                    <Table columns={columns} data={adjustments} onRowClick={handleRowClick} />
                    {meta.totalPages > 1 && (
                        <Pagination currentPage={meta.currentPage} totalPages={meta.totalPages} onPageChange={setPage} />
                    )}
                </>
            )}

            {/* Record Adjustment Modal */}
            <Modal
                isOpen={showModal}
                onClose={() => { setShowModal(false); resetForm(); }}
                title="Record Cash Adjustment"
                size="lg"
            >
                <form onSubmit={handleSubmit} className="space-y-4">
                    <Select
                        label="Type"
                        value={formData.adjustment_type}
                        onChange={(e) => setFormData({ ...formData, adjustment_type: e.target.value })}
                        options={[
                            { value: 'lost', label: 'Lost — reduces cash in hand' },
                            { value: 'found', label: 'Found / Recovered — increases cash in hand' },
                        ]}
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
                        value={formData.adjustment_date}
                        onChange={(e) => setFormData({ ...formData, adjustment_date: e.target.value })}
                        required
                    />
                    <Input
                        label="Reason"
                        value={formData.reason}
                        onChange={(e) => setFormData({ ...formData, reason: e.target.value })}
                        placeholder="Optional note (e.g. till shortage, extra cash found during counting)"
                    />

                    <div>
                        <label className="block text-sm font-medium text-neutral-700 mb-1.5">
                            {formData.adjustment_type === 'lost' ? 'Lost From' : 'Found Into'}
                        </label>
                        <MethodSplitPicker
                            totalAmount={formData.amount}
                            value={formData.method_allocations}
                            onChange={(value) => setFormData({ ...formData, method_allocations: value })}
                            error={splitError}
                        />
                    </div>

                    {formData.amount && parseFloat(formData.amount) > 0 && (
                        <InlineAlert
                            variant={formData.adjustment_type === 'lost' ? 'warning' : 'info'}
                            message={(
                                <>
                                    This will {formData.adjustment_type === 'lost' ? 'deduct' : 'add'}{' '}
                                    <strong>Rs. {fmt(formData.amount)}</strong> {formData.adjustment_type === 'lost' ? 'from' : 'to'} cash in hand
                                </>
                            )}
                        />
                    )}

                    {formError && <InlineAlert variant="error" message={formError} />}

                    <div className="flex justify-end gap-3 pt-4">
                        <Button type="button" variant="secondary" onClick={() => { setShowModal(false); resetForm(); }}>
                            Cancel
                        </Button>
                        <Button
                            type="submit"
                            loading={formLoading}
                            disabled={!isSplitBalanced(formData.amount, formData.method_allocations)}
                        >
                            Record Adjustment
                        </Button>
                    </div>
                </form>
            </Modal>

            {/* Delete Confirmation */}
            <ConfirmDialog
                isOpen={!!deleteConfirm}
                onClose={() => setDeleteConfirm(null)}
                onConfirm={() => handleDelete(deleteConfirm?.id)}
                title="Delete Cash Adjustment"
                message={`Are you sure you want to delete this Rs. ${fmt(deleteConfirm?.amount)} ${deleteConfirm?.adjustment_type} entry? This will reverse its effect on cash in hand.`}
                loading={deleteLoading}
            />
        </div>
    );
};

export default CashAdjustmentsPage;
