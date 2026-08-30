import { motion } from 'framer-motion';
import PropTypes from 'prop-types';

const Tabs = ({ tabs, activeTab, onChange, className = '' }) => {
    return (
        <div className={`border-b border-neutral-200 ${className}`}>
            <div className="flex gap-2">
                {tabs.map((tab) => (
                    <button
                        key={tab.value}
                        onClick={() => onChange(tab.value)}
                        className={`
              px-4 py-2 text-sm font-medium rounded-t-lg transition-all
              ${activeTab === tab.value
                                ? 'text-primary-600 border-b-2 border-primary-600'
                                : 'text-neutral-500 hover:text-neutral-700 hover:bg-neutral-50'
                            }
            `}
                    >
                        {tab.label}
                        {tab.count !== undefined && (
                            <span className={`ml-2 px-2 py-0.5 rounded-full text-xs ${activeTab === tab.value ? 'bg-primary-100 text-primary-600' : 'bg-neutral-100 text-neutral-500'
                                }`}>
                                {tab.count}
                            </span>
                        )}
                    </button>
                ))}
            </div>
        </div>
    );
};

Tabs.propTypes = {
    tabs: PropTypes.arrayOf(
        PropTypes.shape({
            value: PropTypes.string.isRequired,
            label: PropTypes.string.isRequired,
            count: PropTypes.number,
        })
    ).isRequired,
    activeTab: PropTypes.string.isRequired,
    onChange: PropTypes.func.isRequired,
    className: PropTypes.string,
};

export default Tabs;