import { useState } from 'react';
import { motion } from 'framer-motion';
import PropTypes from 'prop-types';
import Input from '../ui/Input';
import Select from '../ui/Select';
import Button from '../ui/Button';

const SUPPLIER_ENTRY_TYPE_OPTIONS = [
    { value: '', label: 'All Types' },
    { value: 'purchase', label: 'Purchase' },
    { value: 'payment', label: 'Payment' },
    { value: 'return', label: 'Return' },
    { value: 'advance', label: 'Advance' },
];

const LedgerFilterBar = ({
    filters,
    onFilterChange,
    onClear,
    className = '',
    entryTypeOptions = SUPPLIER_ENTRY_TYPE_OPTIONS,
}) => {
    const [localFilters, setLocalFilters] = useState(filters || {});

    const handleChange = (key, value) => {
        const newFilters = { ...localFilters, [key]: value };
        setLocalFilters(newFilters);
        onFilterChange(newFilters);
    };

    const handleClear = () => {
        const resetFilters = {
            date_from: '',
            date_to: '',
            entry_type: '',
            reference: '',
            min_amount: '',
            max_amount: '',
        };
        setLocalFilters(resetFilters);
        onClear();
    };

    return (
        <div className={`bg-white rounded-xl p-4 shadow-card ${className}`}>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3">
                <Input
                    label="Date From"
                    type="date"
                    value={localFilters.date_from || ''}
                    onChange={(e) => handleChange('date_from', e.target.value)}
                    className="w-full"
                />
                <Input
                    label="Date To"
                    type="date"
                    value={localFilters.date_to || ''}
                    onChange={(e) => handleChange('date_to', e.target.value)}
                    className="w-full"
                />
                <Select
                    label="Entry Type"
                    value={localFilters.entry_type || ''}
                    onChange={(e) => handleChange('entry_type', e.target.value)}
                    options={entryTypeOptions}
                    className="w-full"
                />
                <Input
                    label="Reference"
                    value={localFilters.reference || ''}
                    onChange={(e) => handleChange('reference', e.target.value)}
                    placeholder="PO-2026, SPY-2026..."
                    className="w-full"
                />
                <Input
                    label="Min Amount"
                    type="number"
                    step="0.01"
                    value={localFilters.min_amount || ''}
                    onChange={(e) => handleChange('min_amount', e.target.value)}
                    placeholder="Min amount"
                    className="w-full"
                />
                <Input
                    label="Max Amount"
                    type="number"
                    step="0.01"
                    value={localFilters.max_amount || ''}
                    onChange={(e) => handleChange('max_amount', e.target.value)}
                    placeholder="Max amount"
                    className="w-full"
                />
            </div>
            <div className="flex justify-end mt-3">
                <Button size="sm" variant="secondary" onClick={handleClear}>
                    Clear All Filters
                </Button>
            </div>
        </div>
    );
};

LedgerFilterBar.propTypes = {
    filters: PropTypes.object,
    onFilterChange: PropTypes.func.isRequired,
    onClear: PropTypes.func.isRequired,
    className: PropTypes.string,
    entryTypeOptions: PropTypes.arrayOf(
        PropTypes.shape({ value: PropTypes.string, label: PropTypes.string })
    ),
};

export { SUPPLIER_ENTRY_TYPE_OPTIONS };
export default LedgerFilterBar;