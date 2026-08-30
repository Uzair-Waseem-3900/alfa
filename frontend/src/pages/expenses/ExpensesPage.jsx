import { useState } from 'react';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import {
    Plus, SlidersHorizontal, X, Pencil, Trash2, Receipt,
    AlertTriangle, Info,
} from 'lucide-react';
import { useExpenses, useAllExpenseCategories, useCashFlowStats } from '../../hooks/useCashFlow';
import { useToast } from '../../context/ToastContext';
import { extractErrorMessage } from '../../utils/errorMessage';
import { todayLocalDate } from '../../utils/helpers';
import MethodSplitPicker, { isSplitBalanced } from '../../components/paymentMethods/MethodSplitPicker';
import Button from '../../components/ui/Button';
import Modal from '../../components/ui/Modal';
import Input from '../../components/ui/Input';
import Select from '../../components/ui/Select';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Table from '../../components/ui/Table';
import SearchBar from '../../components/ui/SearchBar';
import FilterBar from '../../components/ui/FilterBar';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import Pagination from '../../components/ui/Pagination';
import InlineAlert from '../../components/ui/InlineAlert';
import EmptyState from '../../components/ui/EmptyState';

// Field names the expense form/API can validate — anything else in a DRF
// error payload (e.g. a non_field/detail message) is surfaced as a general
// error instead of being silently dropped.
const EXPENSE_FIELDS = ['name', 'category', 'amount', 'expense_date', 'description'];

// Splits a DRF error response into per-field messages (for inline field
// errors) and a general message (for the general form alert / toast).
const splitApiErrors = (error, fieldNames, ignoreKeys = []) => {
    const data = error?.response?.data;
    const fieldErrors = {};
    let generalMessage = null;
    const hadAnyDataKey = !!(data && typeof data === 'object' && !Array.isArray(data) && Object.keys(data).length > 0);

    if (data && typeof data === 'object' && !Array.isArray(data)) {
        Object.keys(data).forEach((key) => {
            if (ignoreKeys.includes(key)) return;
            const val = Array.isArray(data[key]) ? data[key][0] : data[key];
            if (fieldNames.includes(key)) {
                fieldErrors[key] = val;
            } else if (!generalMessage) {
                generalMessage = val;
            }
        });
    }

    if (!generalMessage && Object.keys(fieldErrors).length === 0 && !hadAnyDataKey) {
        generalMessage = extractErrorMessage(error, 'Failed to save expense');
    }

    return { fieldErrors, generalMessage };
};

// method_allocations/splits errors (insufficient balance, empty split, etc.)
// are surfaced next to the MethodSplitPicker instead of via the general
// error alert/field errors above — ignored by splitApiErrors so they aren't
// duplicated there.
const METHOD_ERROR_KEYS = ['method_allocations', 'splits'];
const extractMethodError = (error) => {
    const data = error?.response?.data;
    const val = data?.method_allocations || data?.splits;
    return val ? (Array.isArray(val) ? val[0] : val) : '';
};

const emptyForm = () => ({
    name: '',
    category: '',
    amount: '',
    expense_date: todayLocalDate(),
    description: '',
});

const ExpensesPage = () => {
    const navigate = useNavigate();
    const { toast } = useToast();
    const {
        data: expenses, meta, page, setPage, loading, error,
        filters, setFilters, refetch, create, update, delete: deleteExpense,
    } = useExpenses();
    const { data: categories, loading: categoriesLoading } = useAllExpenseCategories();
    const { refetch: refetchStats } = useCashFlowStats();

    const [showModal, setShowModal] = useState(false);
    const [editingExpense, setEditingExpense] = useState(null);
    const [formData, setFormData] = useState(emptyForm());
    const [fieldErrors, setFieldErrors] = useState({});
    const [formError, setFormError] = useState(null);
    const [formLoading, setFormLoading] = useState(false);
    const [methodAllocations, setMethodAllocations] = useState([]);
    const [splitError, setSplitError] = useState('');
    // Only relevant while editing — creates always require the split.
    // Tracks whether the amount field has actually been touched so the
    // split stays optional on an edit that only changes name/category/date.
    const [amountTouched, setAmountTouched] = useState(false);
    const [deleteConfirm, setDeleteConfirm] = useState(null);
    const [deleteLoading, setDeleteLoading] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');
    const [showFilters, setShowFilters] = useState(false);
    const [filterValues, setFilterValues] = useState({});

    const handleFieldChange = (field, value) => {
        setFormData((prev) => ({ ...prev, [field]: value }));
        if (fieldErrors[field]) {
            setFieldErrors((prev) => ({ ...prev, [field]: '' }));
        }
        if (field === 'amount' && editingExpense) {
            setAmountTouched(true);
        }
    };

    // Create always requires a split; on edit, only require/send one once
    // the amount has actually been changed from its original value.
    const splitRequired = !editingExpense || amountTouched;

    const handleSubmit = async (e) => {
        e.preventDefault();
        setFormError(null);
        setFieldErrors({});
        setSplitError('');
        setFormLoading(true);
        try {
            const data = {
                ...formData,
                amount: parseFloat(formData.amount),
                category: parseInt(formData.category, 10),
            };
            if (splitRequired) {
                data.method_allocations = methodAllocations;
            }

            if (editingExpense) {
                await update(editingExpense.id, data);
                toast.success('Expense updated successfully');
            } else {
                await create(data);
                toast.success('Expense created successfully');
            }
            setShowModal(false);
            resetForm();
            refetchStats();
        } catch (error) {
            const methodError = extractMethodError(error);
            if (methodError) {
                setSplitError(methodError);
            }
            const { fieldErrors: fe, generalMessage } = splitApiErrors(error, EXPENSE_FIELDS, METHOD_ERROR_KEYS);
            setFieldErrors(fe);
            if (generalMessage) {
                setFormError(generalMessage);
            }
        } finally {
            setFormLoading(false);
        }
    };

    const handleEdit = (expense) => {
        setEditingExpense(expense);
        setFormError(null);
        setFieldErrors({});
        setMethodAllocations([]);
        setSplitError('');
        setAmountTouched(false);
        setFormData({
            name: expense.name || '',
            category: expense.category?.id || '',
            amount: expense.amount || '',
            expense_date: expense.expense_date || todayLocalDate(),
            description: expense.description || '',
        });
        setShowModal(true);
    };

    const handleDelete = async (id) => {
        setDeleteLoading(true);
        try {
            await deleteExpense(id);
            toast.success('Expense deleted and cash in hand restored');
            setDeleteConfirm(null);
            refetchStats();
        } catch (error) {
            toast.error(extractErrorMessage(error, 'Failed to delete expense'));
        } finally {
            setDeleteLoading(false);
        }
    };

    const resetForm = () => {
        setFormData(emptyForm());
        setEditingExpense(null);
        setFieldErrors({});
        setFormError(null);
        setMethodAllocations([]);
        setSplitError('');
        setAmountTouched(false);
    };

    const closeModal = () => {
        setShowModal(false);
        resetForm();
    };

    const handleApplyFilters = (newFilters) => {
        setFilterValues(newFilters);
        setFilters(newFilters);
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

    const handleRowClick = (expense) => {
        navigate(`/expenses/${expense.id}`);
    };

    const columns = [
        { key: 'name', label: 'Name' },
        {
            key: 'category',
            label: 'Category',
            render: (value) => value?.name || 'N/A',
        },
        {
            key: 'amount',
            label: 'Amount (PKR)',
            render: (value) => {
                const num = typeof value === 'string' ? parseFloat(value) : value;
                return (
                    <span className="font-semibold text-neutral-900">
                        Rs. {isNaN(num) ? '0.00' : num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </span>
                );
            },
        },
        {
            key: 'expense_date',
            label: 'Date',
            render: (value) => new Date(value).toLocaleDateString(),
        },
        { key: 'description', label: 'Description', render: (value) => value || '-' },
        {
            key: 'actions',
            label: 'Actions',
            width: '110px',
            render: (_, row) => (
                <div className="flex items-center gap-1">
                    <button
                        onClick={(e) => { e.stopPropagation(); handleEdit(row); }}
                        title="Edit expense"
                        aria-label="Edit expense"
                        className="inline-flex items-center justify-center w-9 h-9 rounded-lg text-neutral-500 hover:text-primary-700 hover:bg-primary-50 transition-colors"
                    >
                        <Pencil className="w-4 h-4" />
                    </button>
                    <button
                        onClick={(e) => { e.stopPropagation(); setDeleteConfirm(row); }}
                        title="Delete expense"
                        aria-label="Delete expense"
                        className="inline-flex items-center justify-center w-9 h-9 rounded-lg text-neutral-500 hover:text-error-600 hover:bg-error-50 transition-colors"
                    >
                        <Trash2 className="w-4 h-4" />
                    </button>
                </div>
            ),
        },
    ];

    const filterConfig = [
        {
            name: 'category',
            label: 'Category',
            type: 'select',
            options: [
                { value: '', label: 'All Categories' },
                ...categories.map(c => ({ value: c.id, label: c.name })),
            ],
        },
        { name: 'date_from', label: 'Date From', type: 'date' },
        { name: 'date_to', label: 'Date To', type: 'date' },
        { name: 'min_amount', label: 'Min Amount', type: 'number' },
        { name: 'max_amount', label: 'Max Amount', type: 'number' },
    ];

    const hasActiveFilters = Object.keys(filterValues).length > 0 || searchTerm;

    return (
        <div className="space-y-6">
            <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex flex-col sm:flex-row sm:items-center justify-between gap-4"
            >
                <div className="flex items-center gap-3">
                    <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-primary-700 to-accent-600 flex items-center justify-center shadow-lg shadow-primary-900/20 flex-shrink-0">
                        <Receipt className="w-5 h-5 text-white" />
                    </div>
                    <div>
                        <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900">Expenses</h1>
                        <p className="text-neutral-500 mt-0.5 text-sm sm:text-base">Manage all business expenses</p>
                    </div>
                </div>
                <Button
                    onClick={() => {
                        resetForm();
                        setShowModal(true);
                    }}
                    icon={Plus}
                    className="w-full sm:w-auto"
                >
                    Add Expense
                </Button>
            </motion.div>

            <div className="space-y-4">
                <div className="flex flex-col sm:flex-row gap-3">
                    <SearchBar
                        onSearch={handleSearch}
                        placeholder="Search by name or description..."
                        className="flex-1"
                        value={searchTerm}
                    />
                    <div className="flex gap-3">
                        <Button
                            variant="secondary"
                            onClick={() => setShowFilters(!showFilters)}
                            icon={SlidersHorizontal}
                            className="flex-1 sm:flex-none"
                        >
                            {showFilters ? 'Hide Filters' : 'Filters'}
                        </Button>
                        {hasActiveFilters && (
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

            {error && <InlineAlert variant="error" message={error} onRetry={refetch} />}

            {loading || categoriesLoading ? (
                <div className="flex items-center justify-center py-16">
                    <LoadingSpinner size="lg" />
                </div>
            ) : expenses.length === 0 ? (
                <EmptyState
                    title="No expenses found"
                    description={hasActiveFilters ? 'Try adjusting your search or filters.' : 'Record your first business expense to get started.'}
                />
            ) : (
                <Table
                    columns={columns}
                    data={expenses}
                    onRowClick={handleRowClick}
                />
            )}

            {meta.totalPages > 1 && (
                <Pagination
                    currentPage={meta.currentPage}
                    totalPages={meta.totalPages}
                    onPageChange={setPage}
                />
            )}

            {/* Create/Edit Modal */}
            <Modal
                isOpen={showModal}
                onClose={closeModal}
                title={editingExpense ? 'Edit Expense' : 'Add Expense'}
                size="lg"
            >
                <form onSubmit={handleSubmit} className="space-y-4">
                    {formError && <InlineAlert variant="error" message={formError} />}

                    <Input
                        label="Expense Name"
                        value={formData.name}
                        onChange={(e) => handleFieldChange('name', e.target.value)}
                        placeholder="Enter expense name"
                        error={fieldErrors.name}
                        required
                    />

                    <Select
                        label="Category"
                        value={formData.category}
                        onChange={(e) => handleFieldChange('category', e.target.value)}
                        options={[
                            { value: '', label: 'Select category' },
                            ...categories.map(c => ({ value: c.id, label: c.name })),
                        ]}
                        error={fieldErrors.category}
                        required
                    />

                    <Input
                        label="Amount (PKR)"
                        type="number"
                        step="0.01"
                        min="0.01"
                        value={formData.amount}
                        onChange={(e) => handleFieldChange('amount', e.target.value)}
                        placeholder="Enter amount"
                        error={fieldErrors.amount}
                        required
                    />

                    <Input
                        label="Expense Date"
                        type="date"
                        value={formData.expense_date}
                        onChange={(e) => handleFieldChange('expense_date', e.target.value)}
                        error={fieldErrors.expense_date}
                        required
                    />

                    <Input
                        label="Description"
                        value={formData.description}
                        onChange={(e) => handleFieldChange('description', e.target.value)}
                        placeholder="Enter description (optional)"
                        error={fieldErrors.description}
                    />

                    {!editingExpense && formData.amount && parseFloat(formData.amount) > 0 && (
                        <div className="flex items-start gap-2.5 p-3 bg-warning-50 rounded-xl border border-warning-100">
                            <AlertTriangle className="w-4 h-4 text-warning-500 flex-shrink-0 mt-0.5" />
                            <p className="text-sm text-warning-700">
                                This expense will deduct <strong>Rs. {parseFloat(formData.amount).toFixed(2)}</strong> from cash in hand.
                            </p>
                        </div>
                    )}

                    {editingExpense && formData.amount && parseFloat(formData.amount) > 0 && (
                        <div className="flex items-start gap-2.5 p-3 bg-info-50 rounded-xl border border-info-100">
                            <Info className="w-4 h-4 text-info-500 flex-shrink-0 mt-0.5" />
                            <p className="text-sm text-info-700">
                                Updating the amount will adjust cash in hand by the difference.
                            </p>
                        </div>
                    )}

                    <div>
                        <MethodSplitPicker
                            totalAmount={formData.amount}
                            value={methodAllocations}
                            onChange={setMethodAllocations}
                            error={splitError}
                        />
                        {editingExpense && !amountTouched && (
                            <p className="text-xs text-neutral-400 mt-1.5">
                                Only required if you change the amount.
                            </p>
                        )}
                    </div>

                    <div className="flex justify-end gap-3 pt-4">
                        <Button
                            type="button"
                            variant="secondary"
                            onClick={closeModal}
                        >
                            Cancel
                        </Button>
                        <Button
                            type="submit"
                            loading={formLoading}
                            disabled={splitRequired && !isSplitBalanced(formData.amount, methodAllocations)}
                        >
                            {editingExpense ? 'Update Expense' : 'Create Expense'}
                        </Button>
                    </div>
                </form>
            </Modal>

            {/* Delete Confirmation */}
            <ConfirmDialog
                isOpen={!!deleteConfirm}
                onClose={() => setDeleteConfirm(null)}
                onConfirm={() => handleDelete(deleteConfirm?.id)}
                title="Delete Expense"
                message={`Are you sure you want to delete "${deleteConfirm?.name}"? This will restore the amount to cash in hand.`}
                confirmText="Delete"
                loading={deleteLoading}
            />
        </div>
    );
};

export default ExpensesPage;
