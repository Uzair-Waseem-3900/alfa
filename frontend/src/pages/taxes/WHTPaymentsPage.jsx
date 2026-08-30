import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, SlidersHorizontal, X, AlertTriangle, Trash2, Receipt, Info } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { useTaxesStats, useWHTPayments } from '../../hooks/useTaxes';
import { extractErrorMessage } from '../../utils/errorMessage';
import { todayLocalDate } from '../../utils/helpers';
import MethodSplitPicker, { isSplitBalanced } from '../../components/paymentMethods/MethodSplitPicker';
import Button from '../../components/ui/Button';
import Modal from '../../components/ui/Modal';
import Input from '../../components/ui/Input';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Table from '../../components/ui/Table';
import SearchBar from '../../components/ui/SearchBar';
import FilterBar from '../../components/ui/FilterBar';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import Pagination from '../../components/ui/Pagination';
import BackLink from '../../components/ui/BackLink';
import InlineAlert from '../../components/ui/InlineAlert';
import EmptyState from '../../components/ui/EmptyState';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const WHTPaymentsPage = () => {
    const { user } = useAuth();
    const navigate = useNavigate();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const {
        data: payments, meta, page, setPage, loading, error: listError,
        filters, setFilters, refetch, create, delete: deletePayment,
    } = useWHTPayments();
    const { refetch: refetchStats } = useTaxesStats();

    const [showModal, setShowModal] = useState(false);
    const [formData, setFormData] = useState({
        amount: '',
        payment_date: todayLocalDate(),
        note: '',
    });
    const [formLoading, setFormLoading] = useState(false);
    const [formErrors, setFormErrors] = useState({});
    const [methodAllocations, setMethodAllocations] = useState([]);
    const [splitError, setSplitError] = useState('');
    const [deleteConfirm, setDeleteConfirm] = useState(null);
    const [deleteLoading, setDeleteLoading] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');
    const [showFilters, setShowFilters] = useState(false);
    const [filterValues, setFilterValues] = useState({});

    const resetForm = () => {
        setFormData({ amount: '', payment_date: todayLocalDate(), note: '' });
        setFormErrors({});
        setMethodAllocations([]);
        setSplitError('');
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setFormErrors({});
        setSplitError('');
        setFormLoading(true);
        try {
            await create({
                ...formData,
                amount: parseFloat(formData.amount),
                method_allocations: methodAllocations,
            });
            setShowModal(false);
            resetForm();
            refetchStats();
            toast.success('WHT payment recorded successfully');
        } catch (error) {
            const data = error?.response?.data;
            const methodError = data?.method_allocations || data?.splits;
            const hasFieldErrors = data && typeof data === 'object' && !Array.isArray(data)
                && (data.amount || data.payment_date || data.note);
            if (hasFieldErrors) {
                setFormErrors({
                    amount: Array.isArray(data.amount) ? data.amount[0] : data.amount,
                    payment_date: Array.isArray(data.payment_date) ? data.payment_date[0] : data.payment_date,
                    note: Array.isArray(data.note) ? data.note[0] : data.note,
                });
            }
            if (methodError) {
                setSplitError(Array.isArray(methodError) ? methodError[0] : methodError);
            }
            if (!hasFieldErrors && !methodError) {
                toast.error(extractErrorMessage(error, 'Failed to record WHT payment'));
            }
        } finally {
            setFormLoading(false);
        }
    };

    const handleDelete = async (id) => {
        setDeleteLoading(true);
        try {
            await deletePayment(id);
            setDeleteConfirm(null);
            refetchStats();
            toast.success('WHT payment deleted and cash in hand restored');
        } catch (error) {
            toast.error(extractErrorMessage(error, 'Failed to delete WHT payment'));
        } finally {
            setDeleteLoading(false);
        }
    };

    const handleApplyFilters = (values) => {
        setFilterValues(values);
        setFilters({ ...values, search: searchTerm });
    };

    const handleResetFilters = () => {
        setFilterValues({});
        setSearchTerm('');
        setFilters({});
    };

    const handleSearch = (value) => {
        setSearchTerm(value);
        setFilters({ ...filters, search: value });
    };

    const handleRowClick = (payment) => {
        navigate(`/taxes/wht-payments/${payment.id}`);
    };

    const filterConfig = [
        { name: 'date_from', label: 'Date From', type: 'date' },
        { name: 'date_to', label: 'Date To', type: 'date' },
        { name: 'min_amount', label: 'Min Amount', type: 'number' },
        { name: 'max_amount', label: 'Max Amount', type: 'number' },
    ];

    const columns = [
        {
            key: 'payment_date',
            label: 'Date',
            render: (value) => new Date(value).toLocaleDateString(),
        },
        {
            key: 'amount',
            label: 'Amount (PKR)',
            render: (value) => <span className="font-semibold text-error-600">Rs. {fmt(value)}</span>,
        },
        { key: 'note', label: 'Note', render: (value) => value || <span className="text-neutral-300">—</span> },
        { key: 'created_by', label: 'Recorded By', render: (value) => value || 'N/A' },
        {
            key: 'actions',
            label: 'Actions',
            width: '90px',
            render: (_value, row) => (
                <button
                    onClick={(e) => { e.stopPropagation(); setDeleteConfirm(row); }}
                    className="inline-flex items-center justify-center w-9 h-9 rounded-lg text-error-600 hover:bg-error-50 transition-colors"
                    aria-label="Delete WHT payment"
                >
                    <Trash2 className="w-4 h-4" />
                </button>
            ),
        },
    ];

    if (!isAdmin) {
        return (
            <div className="flex flex-col items-center justify-center text-center py-20">
                <div className="w-14 h-14 rounded-full bg-error-50 flex items-center justify-center mb-4">
                    <AlertTriangle className="w-7 h-7 text-error-500" />
                </div>
                <h2 className="text-2xl font-semibold text-neutral-900">Access Denied</h2>
                <p className="text-neutral-500 mt-2 max-w-sm">Only admins or superusers can view WHT payments.</p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <BackLink to="/taxes">Back to Taxes</BackLink>
                    <h1 className="text-3xl font-bold text-neutral-900 mt-2">WHT Payments</h1>
                    <p className="text-neutral-500 mt-1">
                        Every withholding tax deposit made to FBR, against tax withheld from suppliers.
                    </p>
                </div>
                <Button onClick={() => { resetForm(); setShowModal(true); }} icon={Plus}>
                    Record WHT Payment
                </Button>
            </div>

            <div className="p-3 bg-info-50 border border-info-200 rounded-lg text-sm text-info-700 flex items-start gap-2">
                <Info className="w-4 h-4 flex-shrink-0 mt-0.5" />
                <span>
                    Only tax withheld from suppliers is paid here — WHT withheld by customers is deposited by
                    them directly with FBR on your behalf, so it's never something you pay.
                </span>
            </div>

            <div className="space-y-4">
                <div className="flex flex-col sm:flex-row gap-3">
                    <SearchBar
                        onSearch={handleSearch}
                        placeholder="Search by note..."
                        className="flex-1"
                        value={searchTerm}
                    />
                    <div className="flex gap-3">
                        <Button
                            variant="secondary"
                            onClick={() => setShowFilters(!showFilters)}
                            icon={SlidersHorizontal}
                        >
                            {showFilters ? 'Hide Filters' : 'Filters'}
                        </Button>
                        {(Object.keys(filterValues).length > 0 || searchTerm) && (
                            <Button variant="secondary" onClick={handleResetFilters} icon={X}>
                                Clear
                            </Button>
                        )}
                    </div>
                </div>

                {showFilters && (
                    <FilterBar
                        filters={filterConfig}
                        onApply={handleApplyFilters}
                        onReset={handleResetFilters}
                    />
                )}
            </div>

            {listError ? (
                <InlineAlert variant="error" message={listError} onRetry={refetch} />
            ) : loading ? (
                <div className="flex items-center justify-center py-12">
                    <LoadingSpinner size="lg" />
                </div>
            ) : payments.length === 0 ? (
                <EmptyState
                    title="No WHT Payments Recorded Yet"
                    description="Record a payment when you actually deposit WHT to FBR."
                    icon={<Receipt className="w-8 h-8 text-neutral-400 mx-auto" />}
                />
            ) : (
                <>
                    <Table columns={columns} data={payments} onRowClick={handleRowClick} />
                    {meta.totalPages > 1 && (
                        <Pagination currentPage={meta.currentPage} totalPages={meta.totalPages} onPageChange={setPage} />
                    )}
                </>
            )}

            {/* Record WHT Payment Modal */}
            <Modal
                isOpen={showModal}
                onClose={() => { setShowModal(false); resetForm(); }}
                title="Record WHT Payment"
                size="lg"
            >
                <form onSubmit={handleSubmit} className="space-y-4">
                    <Input
                        label="Amount (PKR)"
                        type="number"
                        step="0.01"
                        min="0.01"
                        value={formData.amount}
                        onChange={(e) => setFormData({ ...formData, amount: e.target.value })}
                        placeholder="Enter amount deposited to FBR"
                        error={formErrors.amount}
                        required
                    />
                    <Input
                        label="Payment Date"
                        type="date"
                        value={formData.payment_date}
                        onChange={(e) => setFormData({ ...formData, payment_date: e.target.value })}
                        error={formErrors.payment_date}
                        required
                    />
                    <Input
                        label="Note"
                        value={formData.note}
                        onChange={(e) => setFormData({ ...formData, note: e.target.value })}
                        placeholder="Optional note (e.g. filing period, supplier)"
                        error={formErrors.note}
                    />

                    {formData.amount && parseFloat(formData.amount) > 0 && (
                        <div className="p-3 bg-amber-50 rounded-lg flex items-start gap-2">
                            <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
                            <p className="text-sm text-amber-700">
                                This will deduct <strong>Rs. {fmt(formData.amount)}</strong> from cash in hand
                            </p>
                        </div>
                    )}

                    <MethodSplitPicker
                        totalAmount={formData.amount}
                        value={methodAllocations}
                        onChange={setMethodAllocations}
                        error={splitError}
                    />

                    <div className="flex justify-end gap-3 pt-4">
                        <Button type="button" variant="secondary" onClick={() => { setShowModal(false); resetForm(); }}>
                            Cancel
                        </Button>
                        <Button
                            type="submit"
                            loading={formLoading}
                            disabled={!isSplitBalanced(formData.amount, methodAllocations)}
                        >
                            Record Payment
                        </Button>
                    </div>
                </form>
            </Modal>

            {/* Delete Confirmation */}
            <ConfirmDialog
                isOpen={!!deleteConfirm}
                onClose={() => setDeleteConfirm(null)}
                onConfirm={() => handleDelete(deleteConfirm?.id)}
                title="Delete WHT Payment"
                message={`Are you sure you want to delete this Rs. ${fmt(deleteConfirm?.amount)} WHT payment? This will restore the amount to cash in hand.`}
                loading={deleteLoading}
            />
        </div>
    );
};

export default WHTPaymentsPage;
