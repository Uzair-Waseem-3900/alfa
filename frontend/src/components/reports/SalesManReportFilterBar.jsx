import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import PropTypes from 'prop-types';
import Button from '../ui/Button';
import Input from '../ui/Input';
import Select from '../ui/Select';
import { salesManApi } from '../../services/salesManApi';

// Drop-in replacement for the plain <FilterBar> on the 4 reports that
// support sales-man scoping (Invoices, Cash Collected, Customer Returns,
// Profit/Margin). Adds two selects — Sales Man and Sales Man Link Name —
// on top of the report's existing date fields. Selecting a sales man
// narrows the link-name dropdown to just his link names; clearing it goes
// back to listing every link name across all sales men. All fields combine
// via AND, same as every other filter bar in the app — Apply sends one
// combined object through the same onApply(filters) contract FilterBar uses,
// so the 4 report pages barely change to adopt this.
const SalesManReportFilterBar = ({ dateFilters, onApply, onReset, className = '' }) => {
    const [isExpanded, setIsExpanded] = useState(true);
    const [dateValues, setDateValues] = useState(
        dateFilters.reduce((acc, f) => ({ ...acc, [f.name]: '' }), {}),
    );
    const [salesManId, setSalesManId] = useState('');
    const [linkNameId, setLinkNameId] = useState('');

    const [salesMen, setSalesMen] = useState([]);
    const [linkNames, setLinkNames] = useState([]);
    const [linkNamesLoading, setLinkNamesLoading] = useState(false);

    useEffect(() => {
        // Bounded dataset (number of sales men employed) — one page is enough.
        salesManApi.salesMen.getAll({ page_size: 500 }).then((data) => {
            setSalesMen(Array.isArray(data) ? data : data?.results || []);
        }).catch(() => setSalesMen([]));
    }, []);

    const fetchLinkNames = useCallback(async (forSalesManId) => {
        setLinkNamesLoading(true);
        try {
            const data = forSalesManId
                ? await salesManApi.linkNames.getAll(forSalesManId)
                : await salesManApi.linkNames.getAllOptions();
            setLinkNames(Array.isArray(data) ? data : data?.results || []);
        } catch {
            setLinkNames([]);
        } finally {
            setLinkNamesLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchLinkNames(salesManId || null);
    }, [salesManId, fetchLinkNames]);

    const handleDateChange = (name, value) => {
        setDateValues((prev) => ({ ...prev, [name]: value }));
    };

    const handleSalesManChange = (e) => {
        setSalesManId(e.target.value);
        // The previously selected link name may not belong to the newly
        // selected sales man (or may need to widen back to "all") — reset
        // it rather than silently keep a now-mismatched value applied.
        setLinkNameId('');
    };

    const handleApply = () => {
        const active = {};
        Object.entries(dateValues).forEach(([key, value]) => {
            if (value) active[key] = value;
        });
        if (salesManId) active.sales_man_id = salesManId;
        if (linkNameId) active.sales_man_link_name_id = linkNameId;
        onApply(active);
    };

    const handleReset = () => {
        setDateValues(dateFilters.reduce((acc, f) => ({ ...acc, [f.name]: '' }), {}));
        setSalesManId('');
        setLinkNameId('');
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
                    className="space-y-3"
                >
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                        {dateFilters.map((filter) => (
                            <Input
                                key={filter.name}
                                label={filter.label}
                                type="date"
                                value={dateValues[filter.name]}
                                onChange={(e) => handleDateChange(filter.name, e.target.value)}
                            />
                        ))}
                        <Select
                            label="Sales Man"
                            value={salesManId}
                            onChange={handleSalesManChange}
                            options={salesMen.map((sm) => ({ value: sm.id, label: `${sm.name} (${sm.code})` }))}
                            placeholder="All Sales Men"
                        />
                        <Select
                            label="Sales Man Link Name"
                            value={linkNameId}
                            onChange={(e) => setLinkNameId(e.target.value)}
                            options={linkNames.map((ln) => ({ value: ln.id, label: ln.name }))}
                            placeholder={linkNamesLoading ? 'Loading...' : 'All Link Names'}
                            disabled={linkNamesLoading}
                        />
                    </div>

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

SalesManReportFilterBar.propTypes = {
    dateFilters: PropTypes.arrayOf(
        PropTypes.shape({ name: PropTypes.string.isRequired, label: PropTypes.string.isRequired }),
    ).isRequired,
    onApply: PropTypes.func.isRequired,
    onReset: PropTypes.func.isRequired,
    className: PropTypes.string,
};

export default SalesManReportFilterBar;
