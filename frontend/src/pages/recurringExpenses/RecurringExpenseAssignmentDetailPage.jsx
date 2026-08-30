import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Plus, Trash2, ShieldAlert, Receipt } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { recurringExpensesApi } from '../../services/recurringExpensesApi';
import { useRecurringExpensePayments } from '../../hooks/useRecurringExpenses';
import { extractErrorMessage } from '../../utils/errorMessage';
import { todayLocalDate } from '../../utils/helpers';
import MethodSplitPicker, { isSplitBalanced } from '../../components/paymentMethods/MethodSplitPicker';
import Button from '../../components/ui/Button';
import BackLink from '../../components/ui/BackLink';
import Card from '../../components/ui/Card';
import Modal from '../../components/ui/Modal';
import Input from '../../components/ui/Input';
import Badge from '../../components/ui/Badge';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Table from '../../components/ui/Table';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import Pagination from '../../components/ui/Pagination';
import EmptyState from '../../components/ui/EmptyState';
import InlineAlert from '../../components/ui/InlineAlert';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const statusBadge = (status) => {
    if (status === 'paid') return <Badge variant="success">Paid</Badge>;
    if (status === 'partial') return <Badge variant="warning">Partial</Badge>;
    return <Badge variant="error">Unpaid</Badge>;
};

const RecurringExpenseAssignmentDetailPage = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const [assignment, setAssignment] = useState(null);
    const [loading, setLoading] = useState(true);
    const [unassignConfirm, setUnassignConfirm] = useState(false);
    const [unassignError, setUnassignError] = useState('');
    const [unassigning, setUnassigning] = useState(false);
    const [deleteLoading, setDeleteLoading] = useState(false);

    const {
        data: payments, meta, page, setPage, loading: paymentsLoading,
        refetch: refetchPayments, create, delete: deletePayment,
    } = useRecurringExpensePayments({ assignment_id: id });

    const [showModal, setShowModal] = useState(false);
    const [formData, setFormData] = useState({
        amount: '', payment_date: todayLocalDate(), note: '',
    });
    const [formLoading, setFormLoading] = useState(false);
    const [formError, setFormError] = useState('');
    const [methodAllocations, setMethodAllocations] = useState([]);
    const [splitError, setSplitError] = useState('');
    const [deleteConfirm, setDeleteConfirm] = useState(null);

    useEffect(() => {
        fetchAssignment();
    }, [id]);

    const fetchAssignment = async () => {
        setLoading(true);
        try {
            const data = await recurringExpensesApi.assignments.getById(id);
            setAssignment(data);
        } catch (error) {
            console.error('Failed to fetch assignment:', error);
            setAssignment(null);
        } finally {
            setLoading(false);
        }
    };

    const resetForm = () => {
        setFormData({ amount: '', payment_date: todayLocalDate(), note: '' });
        setFormError('');
        setMethodAllocations([]);
        setSplitError('');
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setFormError('');
        setSplitError('');
        setFormLoading(true);
        try {
            await create({
                ...formData,
                assignment: id,
                amount: parseFloat(formData.amount),
                method_allocations: methodAllocations,
            });
            setShowModal(false);
            resetForm();
            await Promise.all([refetchPayments(), fetchAssignment()]);
            toast.success('Payment recorded successfully');
        } catch (error) {
            const data = error?.response?.data;
            const methodError = data?.method_allocations || data?.splits;
            if (methodError) {
                setSplitError(Array.isArray(methodError) ? methodError[0] : methodError);
            } else {
                setFormError(extractErrorMessage(error, 'Failed to record payment'));
            }
        } finally {
            setFormLoading(false);
        }
    };

    const handleDelete = async (paymentId) => {
        setDeleteLoading(true);
        try {
            await deletePayment(paymentId);
            setDeleteConfirm(null);
            await Promise.all([refetchPayments(), fetchAssignment()]);
            toast.success('Payment deleted and balances restored');
        } catch (error) {
            setDeleteConfirm(null);
            toast.error(extractErrorMessage(error, 'Failed to delete payment'));
        } finally {
            setDeleteLoading(false);
        }
    };

    const handleUnassign = async () => {
        setUnassignError('');
        setUnassigning(true);
        try {
            await recurringExpensesApi.assignments.delete(id);
            toast.success('Assignment unassigned');
            navigate('/recurring-expenses/assignments');
        } catch (error) {
            setUnassignConfirm(false);
            // Most likely cause: a payment was recorded against this assignment
            // in the meantime, which the backend blocks (see services.py).
            setUnassignError(extractErrorMessage(error, "Failed to unassign — it may already have payments recorded."));
        } finally {
            setUnassigning(false);
        }
    };

    const columns = [
        { key: 'payment_date', label: 'Date', render: (v) => new Date(v).toLocaleDateString() },
        { key: 'amount', label: 'Amount (PKR)', render: (v) => <span className="font-semibold text-success-600">Rs. {fmt(v)}</span> },
        { key: 'note', label: 'Note', render: (v) => v || <span className="text-neutral-300">—</span> },
        {
            key: 'actions',
            label: 'Actions',
            width: '100px',
            render: (_v, row) => (
                <button
                    onClick={(e) => { e.stopPropagation(); setDeleteConfirm(row); }}
                    className="inline-flex items-center gap-1 text-error-600 hover:text-error-700 text-sm font-medium min-h-[44px] sm:min-h-0"
                >
                    <Trash2 className="w-3.5 h-3.5" /> Delete
                </button>
            ),
        },
    ];

    if (!isAdmin) {
        return (
            <div className="flex flex-col items-center justify-center text-center py-20">
                <div className="w-14 h-14 rounded-full bg-error-50 flex items-center justify-center mb-4">
                    <ShieldAlert className="w-7 h-7 text-error-500" />
                </div>
                <h2 className="text-2xl font-semibold text-neutral-900">Access Denied</h2>
                <p className="text-neutral-500 mt-2 max-w-sm">Only admins or superusers can view this.</p>
            </div>
        );
    }

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    if (!assignment) {
        return (
            <div className="text-center py-12">
                <h2 className="text-2xl font-semibold text-neutral-900">Assignment Not Found</h2>
                <BackLink to="/recurring-expenses/assignments" className="mt-4">Back to Assignments</BackLink>
            </div>
        );
    }

    const amountPending = parseFloat(assignment.amount) - parseFloat(assignment.amount_paid);

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                <div>
                    <BackLink to="/recurring-expenses/assignments">Back to Assignments</BackLink>
                    <div className="flex items-center gap-3 mt-1">
                        <h1 className="text-3xl font-bold text-neutral-900">{assignment.name_snapshot}</h1>
                        {statusBadge(assignment.payment_status)}
                    </div>
                    <p className="text-neutral-500">{assignment.category_name_snapshot} · {assignment.period}</p>
                </div>
                <div className="flex gap-3">
                    {assignment.payment_status === 'unpaid' && (
                        <Button variant="danger" onClick={() => { setUnassignError(''); setUnassignConfirm(true); }}>
                            Unassign
                        </Button>
                    )}
                    {amountPending > 0 && (
                        <Button icon={Plus} onClick={() => { resetForm(); setShowModal(true); }}>Record Payment</Button>
                    )}
                </div>
            </div>

            {unassignError && (
                <InlineAlert variant="error" title="Couldn't unassign" message={unassignError} />
            )}

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <Card className="p-4">
                    <p className="text-xs text-neutral-500 mb-1">Assigned Amount</p>
                    <p className="text-xl font-bold text-info-600">Rs. {fmt(assignment.amount)}</p>
                </Card>
                <Card className="p-4">
                    <p className="text-xs text-neutral-500 mb-1">Paid</p>
                    <p className="text-xl font-bold text-success-600">Rs. {fmt(assignment.amount_paid)}</p>
                </Card>
                <Card className="p-4">
                    <p className="text-xs text-neutral-500 mb-1">Pending</p>
                    <p className="text-xl font-bold text-warning-700">Rs. {fmt(amountPending)}</p>
                </Card>
                <Card className="p-4">
                    <p className="text-xs text-neutral-500 mb-1">Assigned On</p>
                    <p className="text-xl font-bold text-neutral-900">{new Date(assignment.assigned_at).toLocaleDateString()}</p>
                </Card>
            </div>

            {assignment.note && (
                <Card className="p-4">
                    <p className="text-sm text-neutral-500">Note</p>
                    <p className="font-medium">{assignment.note}</p>
                </Card>
            )}

            <div className="space-y-4">
                <h2 className="text-lg font-semibold text-neutral-900">Payment History</h2>
                {paymentsLoading ? (
                    <div className="flex items-center justify-center py-8">
                        <LoadingSpinner size="lg" />
                    </div>
                ) : payments.length === 0 ? (
                    <EmptyState
                        icon={<Receipt className="w-8 h-8 text-neutral-400" />}
                        title="No Payments Yet"
                        description="Record a payment to reduce the pending balance."
                    />
                ) : (
                    <>
                        <Table
                            columns={columns}
                            data={payments}
                            onRowClick={(row) => navigate(`/recurring-expenses/payments/${row.id}`)}
                        />
                        {meta.totalPages > 1 && (
                            <Pagination currentPage={meta.currentPage} totalPages={meta.totalPages} onPageChange={setPage} />
                        )}
                    </>
                )}
            </div>

            <Modal
                isOpen={showModal}
                onClose={() => { setShowModal(false); resetForm(); }}
                title="Record Payment"
                size="lg"
            >
                <form onSubmit={handleSubmit} className="space-y-4">
                    <p className="text-sm text-neutral-500">
                        Outstanding balance: <strong>Rs. {fmt(amountPending)}</strong>
                    </p>
                    <Input
                        label="Amount (PKR)"
                        type="number"
                        step="0.01"
                        min="0.01"
                        max={amountPending}
                        value={formData.amount}
                        onChange={(e) => setFormData({ ...formData, amount: e.target.value })}
                        required
                    />
                    <Input
                        label="Payment Date"
                        type="date"
                        value={formData.payment_date}
                        onChange={(e) => setFormData({ ...formData, payment_date: e.target.value })}
                        required
                    />
                    <Input
                        label="Note"
                        value={formData.note}
                        onChange={(e) => setFormData({ ...formData, note: e.target.value })}
                        placeholder="Optional"
                    />

                    <MethodSplitPicker
                        totalAmount={formData.amount}
                        value={methodAllocations}
                        onChange={setMethodAllocations}
                        error={splitError}
                    />

                    {formError && <InlineAlert variant="error" message={formError} />}

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

            <ConfirmDialog
                isOpen={!!deleteConfirm}
                onClose={() => setDeleteConfirm(null)}
                onConfirm={() => handleDelete(deleteConfirm?.id)}
                loading={deleteLoading}
                title="Delete Payment"
                message={`Are you sure you want to delete this Rs. ${fmt(deleteConfirm?.amount)} payment? This will restore cash in hand and this assignment's pending balance.`}
            />

            <ConfirmDialog
                isOpen={unassignConfirm}
                onClose={() => setUnassignConfirm(false)}
                onConfirm={handleUnassign}
                loading={unassigning}
                title="Unassign"
                message={`Are you sure you want to unassign "${assignment.name_snapshot}" for ${assignment.period}? This removes the assignment entirely so you can post it again correctly. Only possible because no payments have been recorded yet.`}
            />
        </div>
    );
};

export default RecurringExpenseAssignmentDetailPage;
