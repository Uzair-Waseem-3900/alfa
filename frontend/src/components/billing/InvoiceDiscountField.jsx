import PropTypes from 'prop-types';
import { BadgePercent } from 'lucide-react';
import Input from '../ui/Input';

const TYPES = [
    { value: 'flat', label: 'Rs' },
    { value: 'percent', label: '%' },
];

// Whole-invoice discount input: a Rs / % toggle plus the amount. Reduces the
// bill total (and gross profit) — never the line prices. Percent is typed as
// a whole number (3 = 3%), matching the backend's stored value.
const InvoiceDiscountField = ({ type, value, onChange, error, disabled = false }) => (
    <div>
        <div className="flex items-end gap-3">
            <div className="flex-1">
                <Input
                    label={`Discount on whole invoice (${type === 'percent' ? '%' : 'PKR'})`}
                    type="number"
                    step="0.01"
                    min="0"
                    max={type === 'percent' ? '100' : undefined}
                    icon={BadgePercent}
                    value={value}
                    onChange={(e) => onChange({ type, value: e.target.value })}
                    placeholder="0"
                    error={error}
                    disabled={disabled}
                />
            </div>
            <div
                className="flex rounded-xl border border-neutral-200 overflow-hidden mb-px h-[50px]"
                role="group"
                aria-label="Discount type"
            >
                {TYPES.map((t) => (
                    <button
                        key={t.value}
                        type="button"
                        disabled={disabled}
                        onClick={() => onChange({ type: t.value, value })}
                        className={`px-4 text-sm font-medium transition-colors ${
                            type === t.value
                                ? 'bg-primary-600 text-white'
                                : 'bg-white text-neutral-600 hover:bg-neutral-50'
                        } ${disabled ? 'cursor-not-allowed opacity-60' : ''}`}
                    >
                        {t.label}
                    </button>
                ))}
            </div>
        </div>
        <p className="text-xs text-neutral-500 mt-1.5">
            Reduces the bill total and your profit — item prices stay the same. Can&apos;t be more than the invoice&apos;s gross profit.
        </p>
    </div>
);

InvoiceDiscountField.propTypes = {
    type: PropTypes.oneOf(['flat', 'percent']).isRequired,
    value: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
    onChange: PropTypes.func.isRequired,
    error: PropTypes.string,
    disabled: PropTypes.bool,
};

export default InvoiceDiscountField;
