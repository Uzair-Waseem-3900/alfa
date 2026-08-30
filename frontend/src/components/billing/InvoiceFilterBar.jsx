import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import PropTypes from 'prop-types';
import { SlidersHorizontal, ChevronDown, ChevronUp, RotateCcw, Filter } from 'lucide-react';
import Button from '../ui/Button';
import Input from '../ui/Input';
import Select from '../ui/Select';

const InvoiceFilterBar = ({ onApply, onReset, filters, className = '' }) => {
    const [isExpanded, setIsExpanded] = useState(false);
    const [filterValues, setFilterValues] = useState({
        customer_name: '',
        customer_code: '',
        bill_number: '',
        status: '',
        payment_status: '',
        date: '',
        date_from: '',
        date_to: '',
        min_amount: '',
        max_amount: '',
    });

    const handleChange = (name, value) => {
        setFilterValues(prev => ({ ...prev, [name]: value }));
    };

    const handleApply = () => {
        const activeFilters = Object.entries(filterValues).reduce((acc, [key, value]) => {
            if (value && value !== '') {
                acc[key] = value;
            }
            return acc;
        }, {});
        onApply(activeFilters);
    };

    const handleReset = () => {
        const resetValues = Object.keys(filterValues).reduce((acc, key) => ({ ...acc, [key]: '' }), {});
        setFilterValues(resetValues);
        onReset();
    };

    return (
        <motion.div
            className={`bg-white rounded-2xl p-4 sm:p-5 shadow-card border border-neutral-100 ${className}`}
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
        >
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-lg bg-primary-50 flex items-center justify-center">
                        <SlidersHorizontal className="w-4 h-4 text-primary-600" />
                    </div>
                    <span className="font-semibold text-neutral-800">Invoice Filters</span>
                </div>
                <button
                    onClick={() => setIsExpanded(!isExpanded)}
                    className="inline-flex items-center gap-1 text-sm font-medium text-primary-600 hover:text-primary-700 transition-colors min-h-[44px] sm:min-h-0 px-2"
                >
                    {isExpanded ? 'Hide Filters' : 'Show Filters'}
                    {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                </button>
            </div>

            <AnimatePresence initial={false}>
                {isExpanded && (
                <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="space-y-3 overflow-hidden"
                >
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 pt-1">
                        <Input
                            label="Customer Name"
                            value={filterValues.customer_name}
                            onChange={(e) => handleChange('customer_name', e.target.value)}
                            placeholder="Search by customer name"
                        />
                        <Input
                            label="Customer Code"
                            value={filterValues.customer_code}
                            onChange={(e) => handleChange('customer_code', e.target.value)}
                            placeholder="Search by customer code"
                        />
                        <Input
                            label="Bill Number"
                            value={filterValues.bill_number}
                            onChange={(e) => handleChange('bill_number', e.target.value)}
                            placeholder="Search by bill number"
                        />
                        <Select
                            label="Status"
                            value={filterValues.status}
                            onChange={(e) => handleChange('status', e.target.value)}
                            options={[
                                { value: '', label: 'All Status' },
                                { value: 'draft', label: 'Draft' },
                                { value: 'confirmed', label: 'Confirmed' },
                                { value: 'partial', label: 'Partial Return' },
                                { value: 'returned', label: 'Returned' },
                            ]}
                        />
                        <Select
                            label="Payment Status"
                            value={filterValues.payment_status}
                            onChange={(e) => handleChange('payment_status', e.target.value)}
                            options={[
                                { value: '', label: 'All Payment Status' },
                                { value: 'unpaid', label: 'Unpaid' },
                                { value: 'partial', label: 'Partial' },
                                { value: 'paid', label: 'Paid' },
                            ]}
                        />
                        <Input
                            label="Date (Exact)"
                            type="date"
                            value={filterValues.date}
                            onChange={(e) => handleChange('date', e.target.value)}
                        />
                        <Input
                            label="Date From"
                            type="date"
                            value={filterValues.date_from}
                            onChange={(e) => handleChange('date_from', e.target.value)}
                        />
                        <Input
                            label="Date To"
                            type="date"
                            value={filterValues.date_to}
                            onChange={(e) => handleChange('date_to', e.target.value)}
                        />
                        <Input
                            label="Min Amount"
                            type="number"
                            value={filterValues.min_amount}
                            onChange={(e) => handleChange('min_amount', e.target.value)}
                            placeholder="Min amount"
                        />
                        <Input
                            label="Max Amount"
                            type="number"
                            value={filterValues.max_amount}
                            onChange={(e) => handleChange('max_amount', e.target.value)}
                            placeholder="Max amount"
                        />
                    </div>

                    <div className="flex gap-3 pt-2">
                        <Button size="sm" onClick={handleApply} icon={Filter}>
                            Apply Filters
                        </Button>
                        <Button size="sm" variant="secondary" onClick={handleReset} icon={RotateCcw}>
                            Reset All
                        </Button>
                    </div>
                </motion.div>
                )}
            </AnimatePresence>
        </motion.div>
    );
};

InvoiceFilterBar.propTypes = {
    onApply: PropTypes.func.isRequired,
    onReset: PropTypes.func.isRequired,
    filters: PropTypes.object,
    className: PropTypes.string,
};

export default InvoiceFilterBar;