import { useState } from 'react';
import { motion } from 'framer-motion';
import PropTypes from 'prop-types';
import Button from './Button';
import Input from './Input';
import Select from './Select';

const FilterBar = ({ filters, onApply, onReset, children, className = '' }) => {
    const [isExpanded, setIsExpanded] = useState(true);
    const [filterValues, setFilterValues] = useState(filters.reduce((acc, f) => ({ ...acc, [f.name]: '' }), {}));

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
        const resetValues = filters.reduce((acc, f) => ({ ...acc, [f.name]: '' }), {});
        setFilterValues(resetValues);
        onReset();
    };

    return (
        <motion.div
            className={`bg-white rounded-xl p-4 shadow-card ${className}`}
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
        >
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                    <svg className="w-5 h-5 text-neutral-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
                    </svg>
                    <span className="font-medium text-neutral-700">Filters</span>
                </div>
                <button
                    onClick={() => setIsExpanded(!isExpanded)}
                    className="text-sm text-primary-600 hover:text-primary-700 transition-colors"
                >
                    {isExpanded ? 'Hide Filters' : 'Show Filters'}
                </button>
            </div>

            {isExpanded && (
                <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="space-y-3"
                >
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                        {filters.map((filter) => (
                            <div key={filter.name}>
                                {filter.type === 'select' ? (
                                    <Select
                                        label={filter.label}
                                        value={filterValues[filter.name]}
                                        onChange={(e) => handleChange(filter.name, e.target.value)}
                                        options={filter.options || []}
                                        placeholder={`All ${filter.label}`}
                                    />
                                ) : filter.type === 'date' ? (
                                    <Input
                                        label={filter.label}
                                        type="date"
                                        value={filterValues[filter.name]}
                                        onChange={(e) => handleChange(filter.name, e.target.value)}
                                    />
                                ) : (
                                    <Input
                                        label={filter.label}
                                        type={filter.type || 'text'}
                                        value={filterValues[filter.name]}
                                        onChange={(e) => handleChange(filter.name, e.target.value)}
                                        placeholder={`Search by ${filter.label.toLowerCase()}`}
                                    />
                                )}
                            </div>
                        ))}
                    </div>

                    {children}

                    <div className="flex gap-3 pt-2">
                        <Button size="sm" onClick={handleApply}>
                            Apply Filters
                        </Button>
                        <Button size="sm" variant="secondary" onClick={handleReset}>
                            Reset
                        </Button>
                    </div>
                </motion.div>
            )}
        </motion.div>
    );
};

FilterBar.propTypes = {
    filters: PropTypes.arrayOf(
        PropTypes.shape({
            name: PropTypes.string.isRequired,
            label: PropTypes.string.isRequired,
            type: PropTypes.string,
            options: PropTypes.arrayOf(
                PropTypes.shape({
                    value: PropTypes.any.isRequired,
                    label: PropTypes.string.isRequired,
                })
            ),
        })
    ).isRequired,
    onApply: PropTypes.func.isRequired,
    onReset: PropTypes.func.isRequired,
    children: PropTypes.node,
    className: PropTypes.string,
};

export default FilterBar;