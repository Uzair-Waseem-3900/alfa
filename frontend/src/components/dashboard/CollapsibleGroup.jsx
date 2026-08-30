import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import PropTypes from 'prop-types';
import { ChevronDown } from 'lucide-react';

const CollapsibleGroup = ({ title, icon: Icon, description, defaultOpen = false, children }) => {
    const [open, setOpen] = useState(defaultOpen);

    return (
        <div className="bg-white rounded-2xl shadow-card border border-neutral-100 overflow-hidden">
            <button
                onClick={() => setOpen(!open)}
                className="w-full flex items-center justify-between gap-3 px-6 py-4 hover:bg-neutral-50 transition-colors cursor-pointer"
            >
                <div className="flex items-center gap-3 text-left">
                    <div className="w-10 h-10 rounded-xl bg-primary-50 flex items-center justify-center flex-shrink-0">
                        <Icon className="w-5 h-5 text-primary-700" />
                    </div>
                    <div>
                        <h2 className="text-base font-semibold text-neutral-900">{title}</h2>
                        {description && (
                            <p className="text-xs text-neutral-500 mt-0.5">{description}</p>
                        )}
                    </div>
                </div>
                <motion.span
                    animate={{ rotate: open ? 180 : 0 }}
                    transition={{ duration: 0.2 }}
                    className="text-neutral-400 shrink-0"
                >
                    <ChevronDown className="w-5 h-5" />
                </motion.span>
            </button>

            <AnimatePresence initial={false}>
                {open && (
                    <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.25 }}
                        className="overflow-hidden"
                    >
                        <div className="px-6 pb-6 pt-2 space-y-8 border-t border-neutral-100">
                            {children}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
};

CollapsibleGroup.propTypes = {
    title: PropTypes.string.isRequired,
    icon: PropTypes.elementType.isRequired,
    description: PropTypes.string,
    defaultOpen: PropTypes.bool,
    children: PropTypes.node,
};

export default CollapsibleGroup;
