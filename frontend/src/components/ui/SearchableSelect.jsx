import { useState, useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import PropTypes from 'prop-types';

const SearchableSelect = ({
    label,
    value,
    selectedLabel,
    onChange,
    options,
    onSearch,
    debounceMs = 300,
    placeholder = 'Search...',
    error,
    required,
    disabled,
    className = '',
}) => {
    const [query, setQuery] = useState('');
    const [isOpen, setIsOpen] = useState(false);
    const [remoteOptions, setRemoteOptions] = useState([]);
    const [searching, setSearching] = useState(false);
    const containerRef = useRef(null);
    const searchSeq = useRef(0);

    const isRemote = typeof onSearch === 'function';
    const selectedOption = isRemote
        ? (remoteOptions.find(o => String(o.value) === String(value))
            ?? (selectedLabel != null ? { value, label: selectedLabel } : undefined))
        : options.find(o => String(o.value) === String(value));

    useEffect(() => {
        const handleClickOutside = (e) => {
            if (containerRef.current && !containerRef.current.contains(e.target)) {
                setIsOpen(false);
                setQuery('');
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    useEffect(() => {
        if (!isRemote) return undefined;
        if (!query) {
            setRemoteOptions([]);
            setSearching(false);
            return undefined;
        }
        const seq = ++searchSeq.current;
        setSearching(true);
        const timer = setTimeout(async () => {
            try {
                const results = await onSearch(query);
                if (searchSeq.current === seq) setRemoteOptions(results || []);
            } finally {
                if (searchSeq.current === seq) setSearching(false);
            }
        }, debounceMs);
        return () => clearTimeout(timer);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [query, isRemote, debounceMs]);

    const filteredOptions = isRemote
        ? remoteOptions
        : (query ? options.filter(o => o.label.toLowerCase().includes(query.toLowerCase())) : options);

    const handleSelect = (option) => {
        onChange(option.value, option);
        setQuery('');
        setIsOpen(false);
    };

    return (
        <div className={`relative ${className}`} ref={containerRef}>
            {label && (
                <label className="block text-sm font-medium text-neutral-700 mb-1.5">
                    {label}
                    {required && <span className="text-error-500 ml-1">*</span>}
                </label>
            )}

            <div className="relative">
                <input
                    type="text"
                    value={isOpen ? query : (selectedOption?.label || '')}
                    onChange={(e) => {
                        setQuery(e.target.value);
                        setIsOpen(true);
                    }}
                    onFocus={() => {
                        setIsOpen(true);
                        setQuery('');
                    }}
                    placeholder={selectedOption && !isOpen ? undefined : placeholder}
                    disabled={disabled}
                    className={`
            w-full px-4 py-3 pr-10 bg-white border rounded-xl
            transition-all duration-300 outline-none
            ${error ? 'border-error-500 focus:ring-2 focus:ring-error-500/20' : 'border-neutral-200 focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500'}
            ${disabled ? 'bg-neutral-50 cursor-not-allowed opacity-60' : ''}
          `}
                />
                <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-neutral-400">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-4.35-4.35M17 11a6 6 0 11-12 0 6 6 0 0112 0z" />
                    </svg>
                </div>

                {isOpen && !disabled && (
                    <motion.div
                        initial={{ opacity: 0, y: -5 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="absolute z-20 mt-1 w-full max-h-60 overflow-y-auto bg-white border border-neutral-200 rounded-xl shadow-lg"
                    >
                        {isRemote && searching ? (
                            <div className="px-4 py-3 text-sm text-neutral-400">Searching...</div>
                        ) : isRemote && !query ? (
                            <div className="px-4 py-3 text-sm text-neutral-400">Type to search...</div>
                        ) : filteredOptions.length === 0 ? (
                            <div className="px-4 py-3 text-sm text-neutral-400">No results found</div>
                        ) : (
                            filteredOptions.map((option) => (
                                <button
                                    type="button"
                                    key={option.value}
                                    onMouseDown={(e) => e.preventDefault()}
                                    onClick={() => handleSelect(option)}
                                    className={`
                    w-full text-left px-4 py-2.5 text-sm transition-colors
                    hover:bg-primary-50
                    ${String(option.value) === String(value) ? 'bg-primary-50 text-primary-700 font-medium' : 'text-neutral-700'}
                  `}
                                >
                                    {option.label}
                                </button>
                            ))
                        )}
                    </motion.div>
                )}
            </div>

            {error && (
                <motion.p
                    initial={{ opacity: 0, y: -5 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="mt-1.5 text-sm text-error-500"
                >
                    {error}
                </motion.p>
            )}
        </div>
    );
};

SearchableSelect.propTypes = {
    label: PropTypes.string,
    value: PropTypes.any,
    selectedLabel: PropTypes.string,
    onChange: PropTypes.func.isRequired,
    options: PropTypes.arrayOf(
        PropTypes.shape({
            value: PropTypes.any.isRequired,
            label: PropTypes.string.isRequired,
        })
    ),
    onSearch: PropTypes.func,
    debounceMs: PropTypes.number,
    placeholder: PropTypes.string,
    error: PropTypes.string,
    required: PropTypes.bool,
    disabled: PropTypes.bool,
    className: PropTypes.string,
};

SearchableSelect.defaultProps = {
    options: [],
};

export default SearchableSelect;
