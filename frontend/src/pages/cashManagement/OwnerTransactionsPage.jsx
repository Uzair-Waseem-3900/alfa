import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Trash2, Landmark, HandCoins, SlidersHorizontal } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { useCashManagementStats, useOwnerTransactions } from '../../hooks/useCashManagement';
import { extractErrorMessage } from '../../utils/errorMessage';
import { todayLocalDate } from '../../utils/helpers';
import MethodSplitPicker, { isSplitBalanced } from '../../components/paymentMethods/MethodSplitPicker';
import Card from '../../components/ui/Card';
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
import BackLink from '../../components/ui/BackLink';
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

const SkeletonStat = () => (
    <div className="p-4 rounded-2xl bg-white shadow-card animate-pulse">
        <div className="h-3 w-24 bg-neutral-200 rounded mb-3" />
        <div className="h-6 w-24 bg-neutral-200 rounded" />
    </div>
);

const OwnerTransactionsPage = () => {
    const { user } = useAuth();
    const { toast } = useToast();
    const navigate = useNavigate();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const { data: stats, loading: statsLoading, refetch: refetchStats } = useCashManagementStats();
    const {
        data: transactions, meta, page, setPage, loading, error: listError,
        filters, setFilters, refetch, create, delete: deleteTransaction,
    } = useOwnerTransactions();

    const [showModal, setShowModal] = useState(false);
    const [formData, setFormData] = useState({
        transaction_type: 'contribution',
        amount: '',
        transaction_date: todayLocalDate(),
        note: '',
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
            transaction_type: 'contribution', amount: '',
            transaction_date: todayLocalDate(), note: '', method_allocations: [],
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
            toast.success('Owner transaction recorded successfully');
        } catch (error) {
            const fieldSplitError = error.response?.data?.method_allocations?.[0] || error.response?.data?.splits?.[0];
            if (fieldSplitError) {
                setSplitError(fieldSplitError);
            } else {
                setFormError(extractErrorMessage(error, 'Failed to record owner transaction'));
            }
        } finally {
            setFormLoading(false);
        }
    };

    const handleDelete = async (id) => {
        setDeleteLoading(true);
        try {
            await deleteTransaction(id);
            setDeleteConfirm(null);
            refetch();
            refetchStats();
            toast.success('Owner transaction deleted and cash in hand adjusted');
        } catch (error) {
            toast.error(extractErrorMessage(error, 'Failed to delete owner transaction'));
        } finally {
            setDeleteLoading(false);
        }
    };

    const handleApplyFilters = (values) => setFilters(values);
    const handleResetFilters = () => setFilters({});
    const handleRowClick = (row) => navigate(`/cash-management/owner-transactions/${row.id}`);

    const filterConfig = [
        { name: 'transaction_type', label: 'Type', type: 'select', options: [
            { value: '', label: 'All' },
            { value: 'contribution', label: 'Contribution' },
            { value: 'drawing', label: 'Drawing' },
        ] },
        { name: 'date_from', label: 'Date From', type: 'date' },
        { name: 'date_to', label: 'Date To', type: 'date' },
        { name: 'min_amount', label: 'Min Amount', type: 'number' },
        { name: 'max_amount', label: 'Max Amount', type: 'number' },
    ];

    const columns = [
        { key: 'transaction_date', label: 'Date', render: (v) => new Date(v).toLocaleDateString() },
        {
            key: 'transaction_type',
            label: 'Type',
            render: (v) => v === 'contribution'
                ? <Badge variant="success" size="sm">Contribution</Badge>
                : <Badge variant="warning" size="sm">Drawing</Badge>,
        },
        {
            key: 'amount',
            label: 'Amount (PKR)',
            render: (v, row) => (
                <span className={`font-semibold ${row.transaction_type === 'contribution' ? 'text-success-600' : 'text-warning-700'}`}>
                    Rs. {fmt(v)}
                </span>
            ),
        },
        { key: 'note', label: 'Note', render: (v) => v || <span className="text-neutral-300">—</span> },
        { key: 'allocations', label: 'Method', render: (v) => formatAllocations(v) },
        { key: 'created_by', label: 'Recorded By', render: (v) => v || 'N/A' },
        {
            key: 'actions',
            label: 'Actions',
            width: '90px',
            render: (_v, row) => (
                <button
                    onClick={(e) => { e.stopPropagation(); setDeleteConfirm(row); }}
                    className="inline-flex items-center justify-center w-9 h-9 rounded-lg text-error-600 hover:bg-error-50 transition-colors"
                    aria-label="Delete transaction"
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
                <p className="text-neutral-500 mt-2">Only admins or superusers can view owner transactions.</p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <BackLink to="/cash-management">Back to Cash Management</BackLink>
                    <div className="flex items-center gap-2.5 mt-2">
                        <Landmark className="w-6 h-6 text-primary-600" />
                        <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900">Owner Transactions</h1>
                    </div>
                    <p className="text-neutral-500 mt-1">
                        Money the owner deposits into or withdraws from the business — distinct from
                        investor capital and from unexplained lost/found cash.
                    </p>
                </div>
                <Button onClick={() => { resetForm(); setShowModal(true); }} icon={Plus}>
                    Record Transaction
                </Button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
                {statsLoading ? (
                    <>
                        <SkeletonStat /><SkeletonStat /><SkeletonStat /><SkeletonStat /><SkeletonStat />
                    </>
                ) : (
                    <>
                        <Card className="p-4" hover={false}>
                            <p className="text-xs text-neutral-500 mb-1">Total Contributions</p>
                            <p className="text-xl font-bold text-info-600">Rs. {fmt(stats?.total_owner_contributions)}</p>
                        </Card>
                        <Card className="p-4" hover={false}>
                            <p className="text-xs text-neutral-500 mb-1">Number of Contributions</p>
                            <p className="text-xl font-bold text-neutral-900">{stats?.total_owner_contributions_count ?? 0}</p>
                        </Card>
                        <Card className="p-4" hover={false}>
                            <p className="text-xs text-neutral-500 mb-1">Total Drawings</p>
                            <p className="text-xl font-bold text-warning-700">Rs. {fmt(stats?.total_owner_drawings)}</p>
                        </Card>
                        <Card className="p-4" hover={false}>
                            <p className="text-xs text-neutral-500 mb-1">Number of Drawings</p>
                            <p className="text-xl font-bold text-neutral-900">{stats?.total_owner_withdrawals_count ?? 0}</p>
                        </Card>
                        <Card className="p-4" hover={false}>
                            <p className="text-xs text-neutral-500 mb-1">Net Owner Capital</p>
                            <p className={`text-xl font-bold ${parseFloat(stats?.net_owner_capital) < 0 ? 'text-error-600' : 'text-purple-600'}`}>
                                Rs. {fmt(stats?.net_owner_capital)}
                            </p>
                        </Card>
                    </>
                )}
            </div>

            <InlineAlert
                variant="info"
                message="Drawings are not capped by contributions — the owner can draw out more than they've deposited (financed by the business's profits). A negative net owner capital is normal."
            />

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
                <InlineAlert variant="error" title="Couldn't load owner transactions" message={listError} onRetry={refetch} />
            )}

            {loading ? (
                <div className="flex items-center justify-center py-16">
                    <LoadingSpinner size="lg" />
                </div>
            ) : transactions.length === 0 ? (
                <EmptyState
                    icon={<HandCoins className="w-8 h-8 text-neutral-400 mx-auto" />}
                    title="No Owner Transactions Yet"
                    description="Record a contribution or drawing to get started."
                />
            ) : (
                <>
                    <Table columns={columns} data={transactions} onRowClick={handleRowClick} />
                    {meta.totalPages > 1 && (
                        <Pagination currentPage={meta.currentPage} totalPages={meta.totalPages} onPageChange={setPage} />
                    )}
                </>
            )}

            {/* Record Transaction Modal */}
            <Modal
                isOpen={showModal}
                onClose={() => { setShowModal(false); resetForm(); }}
                title="Record Owner Transaction"
                size="lg"
            >
                <form onSubmit={handleSubmit} className="space-y-4">
                    <Select
                        label="Type"
                        value={formData.transaction_type}
                        onChange={(e) => setFormData({ ...formData, transaction_type: e.target.value })}
                        options={[
                            { value: 'contribution', label: 'Contribution — increases cash in hand' },
                            { value: 'drawing', label: 'Drawing — decreases cash in hand' },
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
                        value={formData.transaction_date}
                        onChange={(e) => setFormData({ ...formData, transaction_date: e.target.value })}
                        required
                    />
                    <Input
                        label="Note"
                        value={formData.note}
                        onChange={(e) => setFormData({ ...formData, note: e.target.value })}
                        placeholder="Optional"
                    />

                    <div>
                        <label className="block text-sm font-medium text-neutral-700 mb-1.5">
                            {formData.transaction_type === 'contribution' ? 'Received Via' : 'Paid Via'}
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
                            variant={formData.transaction_type === 'contribution' ? 'info' : 'warning'}
                            message={(
                                <>
                                    This will {formData.transaction_type === 'contribution' ? 'add' : 'deduct'}{' '}
                                    <strong>Rs. {fmt(formData.amount)}</strong> {formData.transaction_type === 'contribution' ? 'to' : 'from'} cash in hand
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
                            Record
                        </Button>
                    </div>
                </form>
            </Modal>

            {/* Delete Confirmation */}
            <ConfirmDialog
                isOpen={!!deleteConfirm}
                onClose={() => setDeleteConfirm(null)}
                onConfirm={() => handleDelete(deleteConfirm?.id)}
                title="Delete Owner Transaction"
                message={`Are you sure you want to delete this Rs. ${fmt(deleteConfirm?.amount)} ${deleteConfirm?.transaction_type}? This will reverse its effect on cash in hand.`}
                loading={deleteLoading}
            />
        </div>
    );
};

export default OwnerTransactionsPage;
