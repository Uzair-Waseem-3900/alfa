import { useEffect } from 'react';
import PropTypes from 'prop-types';
import { Plus, Trash2 } from 'lucide-react';
import { usePaymentMethods } from '../../hooks/usePaymentMethods';
import Select from '../ui/Select';
import Input from '../ui/Input';
import LoadingSpinner from '../ui/LoadingSpinner';
import InlineAlert from '../ui/InlineAlert';

const toNumber = (v) => {
    const num = typeof v === 'string' ? parseFloat(v) : Number(v);
    return isNaN(num) ? 0 : num;
};

const fmt = (v) => toNumber(v).toFixed(2);

// Pure helpers other forms/pages can reuse to gate their own submit button
// without re-deriving the balance math (e.g. `disabled={!isSplitBalanced(total, splits)}`).
export const splitRemaining = (totalAmount, value) => {
    const allocated = (value || []).reduce((sum, row) => sum + toNumber(row.amount), 0);
    return toNumber(totalAmount) - allocated;
};

export const isSplitBalanced = (totalAmount, value) =>
    (value || []).length > 0 && Math.abs(splitRemaining(totalAmount, value)) < 0.005;

// Shared split-amount picker: lets a form allocate one transaction total
// across one or more payment methods. Produces/consumes the split shape
// every other app's forms send: [{ payment_method: <id>, amount: "123.45" }].
// A single-method form still sends a one-item array.
const MethodSplitPicker = ({ totalAmount, value, onChange, error, className = '' }) => {
    const { data: methods, loading, error: methodsError, refetch } = usePaymentMethods();

    // Parent forms typically start with value=[] before the user picks
    // anything — seed a single blank row so there's always at least one
    // row to edit, keeping the array-shape contract (never a truly empty split).
    useEffect(() => {
        if (value.length === 0) {
            onChange([{ payment_method: '', amount: totalAmount ? String(totalAmount) : '' }]);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [value.length]);

    const rows = value.length > 0 ? value : [{ payment_method: '', amount: '' }];

    const remaining = splitRemaining(totalAmount, rows);
    const isBalanced = isSplitBalanced(totalAmount, rows);

    const updateRow = (index, patch) => {
        onChange(rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
    };

    const addRow = () => {
        onChange([...rows, { payment_method: '', amount: '' }]);
    };

    const removeRow = (index) => {
        if (rows.length <= 1) return;
        onChange(rows.filter((_, i) => i !== index));
    };

    const methodOptions = (methods || []).map((m) => ({ value: m.id, label: m.name }));

    if (loading) {
        return (
            <div className="flex items-center justify-center py-6">
                <LoadingSpinner size="sm" />
            </div>
        );
    }

    if (methodsError) {
        return (
            <InlineAlert
                variant="error"
                title="Couldn't load payment methods"
                message={methodsError}
                onRetry={refetch}
            />
        );
    }

    return (
        <div className={`space-y-3 ${className}`}>
            {rows.map((row, index) => (
                <div key={index} className="flex items-start gap-2">
                    <Select
                        className="flex-1"
                        value={row.payment_method}
                        onChange={(e) => updateRow(index, {
                            payment_method: e.target.value ? Number(e.target.value) : '',
                        })}
                        options={methodOptions}
                        placeholder="Select method..."
                        required
                    />
                    <Input
                        className="flex-1"
                        type="number"
                        step="0.01"
                        min="0"
                        value={row.amount}
                        onChange={(e) => updateRow(index, { amount: e.target.value })}
                        placeholder="Amount"
                        required
                    />
                    <button
                        type="button"
                        onClick={() => removeRow(index)}
                        disabled={rows.length <= 1}
                        className="inline-flex items-center justify-center w-11 h-11 mt-0.5 rounded-lg text-error-600 hover:bg-error-50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent"
                        aria-label="Remove split"
                    >
                        <Trash2 className="w-4 h-4" />
                    </button>
                </div>
            ))}

            <button
                type="button"
                onClick={addRow}
                className="inline-flex items-center gap-1.5 text-sm font-medium text-primary-600 hover:text-primary-700 transition-colors"
            >
                <Plus className="w-4 h-4" /> Add method
            </button>

            <div
                className={`flex items-center justify-between text-sm font-medium rounded-lg px-3 py-2 ${
                    isBalanced ? 'bg-success-50 text-success-700' : 'bg-warning-50 text-warning-700'
                }`}
            >
                <span>Remaining to allocate</span>
                <span>Rs. {fmt(remaining)}</span>
            </div>

            {error && <InlineAlert variant="error" message={error} />}
        </div>
    );
};

MethodSplitPicker.propTypes = {
    totalAmount: PropTypes.oneOfType([PropTypes.number, PropTypes.string]).isRequired,
    value: PropTypes.arrayOf(
        PropTypes.shape({
            payment_method: PropTypes.oneOfType([PropTypes.number, PropTypes.string]),
            amount: PropTypes.oneOfType([PropTypes.number, PropTypes.string]),
        })
    ).isRequired,
    onChange: PropTypes.func.isRequired,
    error: PropTypes.string,
    className: PropTypes.string,
};

export default MethodSplitPicker;
