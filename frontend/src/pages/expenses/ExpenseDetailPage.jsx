import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
    Pencil, Trash2, Tag, Calendar, User, Clock, FileText, TrendingDown, Receipt,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { extractErrorMessage } from '../../utils/errorMessage';
import { cashFlowApi } from '../../services/cashFlowApi';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Badge from '../../components/ui/Badge';
import BackLink from '../../components/ui/BackLink';
import InlineAlert from '../../components/ui/InlineAlert';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import EmptyState from '../../components/ui/EmptyState';

const formatAmount = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : value;
    return isNaN(num) ? '0.00' : num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

const ExpenseDetailPage = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const [expense, setExpense] = useState(null);
    const [loading, setLoading] = useState(true);
    const [fetchError, setFetchError] = useState(null);
    const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
    const [deleteLoading, setDeleteLoading] = useState(false);

    useEffect(() => {
        fetchExpenseDetails();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [id]);

    const fetchExpenseDetails = async () => {
        setLoading(true);
        setFetchError(null);
        try {
            const found = await cashFlowApi.expenses.getById(id);
            setExpense(found || null);
        } catch (error) {
            if (error?.response?.status === 404) {
                setExpense(null);
                return;
            }
            console.error('Failed to fetch expense details:', error);
            setExpense(null);
            setFetchError(extractErrorMessage(error, 'Failed to load expense details'));
        } finally {
            setLoading(false);
        }
    };

    const handleEdit = () => {
        navigate(`/expenses/${id}/edit`);
    };

    const handleDelete = async () => {
        setDeleteLoading(true);
        try {
            await cashFlowApi.expenses.delete(id);
            toast.success('Expense deleted and cash in hand restored');
            navigate('/expenses');
        } catch (error) {
            console.error('Failed to delete expense:', error);
            toast.error(extractErrorMessage(error, 'Failed to delete expense'));
            setDeleteLoading(false);
            setDeleteConfirmOpen(false);
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    if (fetchError) {
        return (
            <div className="space-y-6">
                <BackLink to="/expenses">Back to Expenses</BackLink>
                <InlineAlert variant="error" message={fetchError} onRetry={fetchExpenseDetails} />
            </div>
        );
    }

    if (!expense) {
        return (
            <div className="space-y-6">
                <BackLink to="/expenses">Back to Expenses</BackLink>
                <EmptyState
                    title="Expense not found"
                    description="The expense you're looking for doesn't exist or may have been deleted."
                />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex flex-col sm:flex-row sm:items-center justify-between gap-4"
            >
                <div>
                    <BackLink to="/expenses">Back to Expenses</BackLink>
                    <div className="flex items-center gap-3 mt-3">
                        <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-primary-700 to-accent-600 flex items-center justify-center shadow-lg shadow-primary-900/20 flex-shrink-0">
                            <Receipt className="w-5 h-5 text-white" />
                        </div>
                        <div>
                            <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900">Expense Details</h1>
                            <p className="text-neutral-500 text-sm sm:text-base">{expense.name}</p>
                        </div>
                    </div>
                </div>
                {isAdmin && (
                    <div className="flex gap-2">
                        <Button variant="secondary" onClick={handleEdit} icon={Pencil}>
                            Edit
                        </Button>
                        <Button variant="danger" onClick={() => setDeleteConfirmOpen(true)} icon={Trash2}>
                            Delete
                        </Button>
                    </div>
                )}
            </motion.div>

            {/* Expense Information */}
            <Card className="p-6">
                <h3 className="font-semibold text-neutral-900 mb-4 flex items-center gap-2">
                    <FileText className="w-4 h-4 text-neutral-400" />
                    Expense Information
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
                    <div>
                        <p className="text-xs font-medium text-neutral-500 uppercase tracking-wide mb-1">Name</p>
                        <p className="font-medium text-neutral-900">{expense.name}</p>
                    </div>
                    <div>
                        <p className="text-xs font-medium text-neutral-500 uppercase tracking-wide mb-1 flex items-center gap-1">
                            <Tag className="w-3.5 h-3.5" /> Category
                        </p>
                        <Badge>{expense.category?.name || 'N/A'}</Badge>
                    </div>
                    <div>
                        <p className="text-xs font-medium text-neutral-500 uppercase tracking-wide mb-1">Amount</p>
                        <p className="text-xl font-bold text-error-600">Rs. {formatAmount(expense.amount)}</p>
                    </div>
                    <div>
                        <p className="text-xs font-medium text-neutral-500 uppercase tracking-wide mb-1 flex items-center gap-1">
                            <Calendar className="w-3.5 h-3.5" /> Expense Date
                        </p>
                        <p className="font-medium text-neutral-900">{new Date(expense.expense_date).toLocaleDateString()}</p>
                    </div>
                    <div>
                        <p className="text-xs font-medium text-neutral-500 uppercase tracking-wide mb-1 flex items-center gap-1">
                            <User className="w-3.5 h-3.5" /> Created By
                        </p>
                        <p className="font-medium text-neutral-900">{expense.created_by || 'N/A'}</p>
                    </div>
                    <div>
                        <p className="text-xs font-medium text-neutral-500 uppercase tracking-wide mb-1 flex items-center gap-1">
                            <Clock className="w-3.5 h-3.5" /> Created At
                        </p>
                        <p className="font-medium text-neutral-900">{new Date(expense.created_at).toLocaleString()}</p>
                    </div>
                    {expense.updated_by && (
                        <div>
                            <p className="text-xs font-medium text-neutral-500 uppercase tracking-wide mb-1">Updated By</p>
                            <p className="font-medium text-neutral-900">{expense.updated_by}</p>
                        </div>
                    )}
                    {expense.updated_at && expense.updated_at !== expense.created_at && (
                        <div>
                            <p className="text-xs font-medium text-neutral-500 uppercase tracking-wide mb-1">Updated At</p>
                            <p className="font-medium text-neutral-900">{new Date(expense.updated_at).toLocaleString()}</p>
                        </div>
                    )}
                    {expense.description && (
                        <div className="col-span-full">
                            <p className="text-xs font-medium text-neutral-500 uppercase tracking-wide mb-1">Description</p>
                            <p className="font-medium text-neutral-900">{expense.description}</p>
                        </div>
                    )}
                </div>
            </Card>

            {/* Method Breakdown */}
            {expense.allocations?.length > 0 && (
                <Card className="p-6">
                    <h3 className="font-semibold text-neutral-900 mb-4">Method Breakdown</h3>
                    <div className="space-y-2">
                        {expense.allocations.map((a) => (
                            <div key={a.id} className="flex items-center justify-between text-sm bg-neutral-50 rounded-lg px-3 py-2.5">
                                <span className="text-neutral-700">{a.payment_method_name}</span>
                                <span className="font-medium text-error-600">
                                    − Rs. {formatAmount(a.amount)}
                                </span>
                            </div>
                        ))}
                    </div>
                </Card>
            )}

            {/* Cash Impact */}
            <Card className="p-6">
                <h3 className="font-semibold text-neutral-900 mb-3 flex items-center gap-2">
                    <TrendingDown className="w-4 h-4 text-neutral-400" />
                    Cash Impact
                </h3>
                <div className="flex items-start gap-3 p-4 bg-warning-50 rounded-xl border border-warning-100">
                    <TrendingDown className="w-5 h-5 text-warning-500 flex-shrink-0 mt-0.5" />
                    <div>
                        <p className="text-warning-700">
                            This expense reduced cash in hand by <strong>Rs. {formatAmount(expense.amount)}</strong>
                        </p>
                        <p className="text-sm text-warning-600 mt-1">
                            Recorded on {new Date(expense.expense_date).toLocaleDateString()}
                        </p>
                    </div>
                </div>
            </Card>

            {/* Actions */}
            <div className="flex flex-wrap gap-3 pt-4 border-t border-neutral-200">
                <BackLink to="/expenses">Back to Expenses</BackLink>
                {isAdmin && (
                    <div className="flex gap-2 ml-auto">
                        <Button variant="secondary" onClick={handleEdit} icon={Pencil}>
                            Edit Expense
                        </Button>
                        <Button variant="danger" onClick={() => setDeleteConfirmOpen(true)} icon={Trash2}>
                            Delete Expense
                        </Button>
                    </div>
                )}
            </div>

            <ConfirmDialog
                isOpen={deleteConfirmOpen}
                onClose={() => setDeleteConfirmOpen(false)}
                onConfirm={handleDelete}
                title="Delete Expense"
                message={`Are you sure you want to delete "${expense.name}"? This will restore the amount to cash in hand.`}
                confirmText="Delete"
                loading={deleteLoading}
            />
        </div>
    );
};

export default ExpenseDetailPage;
