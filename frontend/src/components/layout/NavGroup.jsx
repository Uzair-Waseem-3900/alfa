import { useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Link, useLocation } from 'react-router-dom';
import PropTypes from 'prop-types';
import { ChevronDown } from 'lucide-react';

const linkClasses = (active) =>
    `flex items-center gap-3 px-4 py-2.5 rounded-xl transition-all duration-200 text-sm ${active
        ? 'bg-primary-50 text-primary-700'
        : 'text-neutral-600 hover:bg-neutral-100'
    }`;

const NavGroup = ({ group, sidebarOpen, isOpen, onToggle, isAdmin, isSuperuser }) => {
    const location = useLocation();
    const [flyoutOpen, setFlyoutOpen] = useState(false);
    const closeTimer = useRef(null);

    const items = group.items.filter(
        (item) => (!item.adminOnly || isAdmin) && (!item.superuserOnly || isSuperuser)
    );
    if (items.length === 0) return null;

    const groupActive = items.some((item) => location.pathname.startsWith(item.path));
    const GroupIcon = group.icon;

    const openFlyout = () => {
        clearTimeout(closeTimer.current);
        setFlyoutOpen(true);
    };
    const scheduleCloseFlyout = () => {
        closeTimer.current = setTimeout(() => setFlyoutOpen(false), 150);
    };

    if (!sidebarOpen) {
        return (
            <div
                className="relative mt-2 pt-2 border-t border-neutral-200"
                onMouseEnter={openFlyout}
                onMouseLeave={scheduleCloseFlyout}
            >
                <button
                    type="button"
                    onFocus={openFlyout}
                    onBlur={scheduleCloseFlyout}
                    className={`w-full flex items-center justify-center px-4 py-3 rounded-xl transition-all duration-200 cursor-pointer ${groupActive
                        ? 'bg-primary-50 text-primary-700'
                        : 'text-neutral-600 hover:bg-neutral-100'
                        }`}
                    title={group.label}
                    aria-haspopup="true"
                    aria-expanded={flyoutOpen}
                >
                    <GroupIcon className="w-5 h-5" />
                </button>

                <AnimatePresence>
                    {flyoutOpen && (
                        <motion.div
                            initial={{ opacity: 0, x: -8 }}
                            animate={{ opacity: 1, x: 0 }}
                            exit={{ opacity: 0, x: -8 }}
                            transition={{ duration: 0.15 }}
                            className="absolute left-full top-0 ml-2 z-50 min-w-[200px] bg-white rounded-xl shadow-dropdown border border-neutral-100 p-2"
                        >
                            <p className="px-3 py-1.5 text-xs font-semibold text-neutral-400 uppercase tracking-wide">
                                {group.label}
                            </p>
                            {items.map((item) => {
                                const ItemIcon = item.icon;
                                return (
                                    <Link key={item.path} to={item.path} className={linkClasses(location.pathname === item.path)}>
                                        <ItemIcon className="w-4 h-4" />
                                        <span className="font-medium">{item.name}</span>
                                    </Link>
                                );
                            })}
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>
        );
    }

    return (
        <div className="mt-2 pt-2 border-t border-neutral-200">
            <button
                type="button"
                onClick={onToggle}
                className={`w-full flex items-center justify-between gap-3 px-4 py-3 rounded-xl transition-all duration-200 cursor-pointer ${groupActive
                    ? 'bg-primary-50 text-primary-700'
                    : 'text-neutral-600 hover:bg-neutral-100'
                    }`}
            >
                <div className="flex items-center gap-3">
                    <GroupIcon className="w-5 h-5" />
                    <span className="font-medium">{group.label}</span>
                </div>
                <motion.span animate={{ rotate: isOpen ? 180 : 0 }} transition={{ duration: 0.2 }}>
                    <ChevronDown className="w-4 h-4" />
                </motion.span>
            </button>

            <AnimatePresence>
                {isOpen && (
                    <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        exit={{ opacity: 0, height: 0 }}
                        transition={{ duration: 0.2 }}
                        className="ml-4 space-y-1 overflow-hidden"
                    >
                        {items.map((item) => {
                            const ItemIcon = item.icon;
                            return (
                                <Link key={item.path} to={item.path} className={linkClasses(location.pathname === item.path)}>
                                    <ItemIcon className="w-4 h-4" />
                                    <span className="font-medium">{item.name}</span>
                                </Link>
                            );
                        })}
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
};

NavGroup.propTypes = {
    group: PropTypes.shape({
        key: PropTypes.string.isRequired,
        label: PropTypes.string.isRequired,
        icon: PropTypes.elementType.isRequired,
        items: PropTypes.array.isRequired,
    }).isRequired,
    sidebarOpen: PropTypes.bool.isRequired,
    isOpen: PropTypes.bool.isRequired,
    onToggle: PropTypes.func.isRequired,
    isAdmin: PropTypes.bool,
    isSuperuser: PropTypes.bool,
};

export default NavGroup;
