import { useState, useEffect } from 'react';
import { CalendarCheck2, CheckCircle2, ShieldAlert } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { useRecurringExpensePendingDues } from '../../hooks/useRecurringExpenses';
import { recurringExpensesApi } from '../../services/recurringExpensesApi';
import { extractErrorMessage } from '../../utils/errorMessage';
import { currentMonthLocal } from '../../utils/helpers';
import Button from '../../components/ui/Button';
import BackLink from '../../components/ui/BackLink';
import Select from '../../components/ui/Select';
import Input from '../../components/ui/Input';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Table from '../../components/ui/Table';
import Pagination from '../../components/ui/Pagination';
import EmptyState from '../../components/ui/EmptyState';
import InlineAlert from '../../components/ui/InlineAlert';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const currentMonth = () => currentMonthLocal();

const RecurringExpensePostDuesPage = () => {
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const [period, setPeriod] = useState(currentMonth());
    const [categoryId, setCategoryId] = useState('');
    const [categories, setCategories] = useState([]);

    const {
        data: pending, meta, page, setPage, loading, refetch, setFilters,
    } = useRecurringExpensePendingDues({ period });

    // usePaginatedList only reads its initialFilters argument once, on mount —
    // period/categoryId change interactively here, so they must be pushed via
    // setFilters explicitly or the list would silently stop updating.
    useEffect(() => {
        setFilters(categoryId ? { period, category_id: categoryId } : { period });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [period, categoryId]);

    const [assigningId, setAssigningId] = useState(null);
    const [bulkLoading, setBulkLoading] = useState(false);
    const [actionError, setActionError] = useState('');
    const [bulkResult, setBulkResult] = useState(null);

    useEffect(() => {
        recurringExpensesApi.categories.getAll({ page_size: 500 }).then((res) => {
            setCategories(res?.results ?? res ?? []);
        });
    }, []);

    const handlePeriodChange = (value) => {
        setPeriod(value);
        setBulkResult(null);
    };

    const handleCategoryChange = (value) => {
        setCategoryId(value);
        setBulkResult(null);
    };

    const handleAssignOne = async (template) => {
        setActionError('');
        setAssigningId(template.id);
        try {
            await recurringExpensesApi.assignments.create({ recurring_expense: template.id, period });
            await refetch();
            toast.success(`Posted "${template.name}" for ${period}`);
        } catch (error) {
            // Most common failure here is a conflict — this template already has
            // an assignment for the period (unique constraint in the backend).
            setActionError(extractErrorMessage(error, 'Failed to assign'));
        } finally {
            setAssigningId(null);
        }
    };

    const handleBulkAssign = async () => {
        setActionError('');
        setBulkResult(null);
        setBulkLoading(true);
        try {
            const payload = { period, ...(categoryId ? { category_id: categoryId } : {}) };
            const result = await recurringExpensesApi.assignments.bulkCreate(payload);
            setBulkResult(result);
            await refetch();
            const createdCount = result.created?.length ?? 0;
            if (result.failed?.length > 0) {
                toast.warning(`Posted ${createdCount}, ${result.failed.length} failed — see details below.`);
            } else if (createdCount > 0) {
                toast.success(`Posted ${createdCount} due${createdCount === 1 ? '' : 's'} for ${period}`);
            }
        } catch (error) {
            setActionError(extractErrorMessage(error, 'Failed to bulk-assign'));
        } finally {
            setBulkLoading(false);
        }
    };

    const columns = [
        { key: 'name', label: 'Name' },
        { key: 'category_name', label: 'Category' },
        { key: 'amount', label: 'Amount (PKR)', render: (v) => <span className="font-semibold text-info-600">Rs. {fmt(v)}</span> },
        {
            key: 'actions',
            label: 'Actions',
            width: '120px',
            render: (_v, row) => (
                <Button size="sm" loading={assigningId === row.id} onClick={() => handleAssignOne(row)}>
                    Post
                </Button>
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
                <p className="text-neutral-500 mt-2 max-w-sm">Only admins or superusers can post recurring expense dues.</p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div>
                <BackLink to="/recurring-expenses">Back to Recurring Expenses</BackLink>
                <h1 className="text-3xl font-bold text-neutral-900 mt-1">Post Dues</h1>
                <p className="text-neutral-500 mt-1 max-w-2xl">
                    Assigning a month's due never moves cash by itself — it only becomes a payable balance.
                    Record an actual payment from the Assignments page once it's paid.
                </p>
            </div>

            <div className="flex flex-col sm:flex-row gap-4 items-end p-4 bg-neutral-50 rounded-xl">
                <Input
                    label="Month"
                    type="month"
                    value={period}
                    onChange={(e) => handlePeriodChange(e.target.value)}
                    className="w-48"
                />
                <Select
                    label="Category (optional)"
                    value={categoryId}
                    onChange={(e) => handleCategoryChange(e.target.value)}
                    options={categories.map((c) => ({ value: c.id, label: c.name }))}
                    placeholder="All categories"
                    className="w-56"
                />
                <Button loading={bulkLoading} onClick={handleBulkAssign} disabled={pending.length === 0} icon={CalendarCheck2}>
                    {categoryId ? `Post All in Category` : 'Post All Due'}
                </Button>
            </div>

            {actionError && (
                <InlineAlert variant="error" title="Couldn't post due" message={actionError} />
            )}

            {bulkResult && (
                <InlineAlert
                    variant={bulkResult.failed?.length > 0 ? 'warning' : 'success'}
                    message={
                        <>
                            Posted {bulkResult.created?.length ?? 0} due{bulkResult.created?.length === 1 ? '' : 's'} for {period}.
                            {bulkResult.failed?.length > 0 && (
                                <> {bulkResult.failed.length} failed: {bulkResult.failed.map((f) => f.name).join(', ')}.</>
                            )}
                        </>
                    }
                />
            )}

            {loading ? (
                <div className="flex items-center justify-center py-8">
                    <LoadingSpinner size="lg" />
                </div>
            ) : pending.length === 0 ? (
                <EmptyState
                    icon={<CheckCircle2 className="w-8 h-8 text-success-500" />}
                    title="Nothing Due"
                    description={`Every active recurring expense${categoryId ? ' in this category' : ''} has already been assigned for ${period}.`}
                />
            ) : (
                <>
                    <Table columns={columns} data={pending} />
                    {meta.totalPages > 1 && (
                        <Pagination currentPage={meta.currentPage} totalPages={meta.totalPages} onPageChange={setPage} />
                    )}
                </>
            )}
        </div>
    );
};

export default RecurringExpensePostDuesPage;
