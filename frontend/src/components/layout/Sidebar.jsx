import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Link, useLocation } from 'react-router-dom';
import PropTypes from 'prop-types';
import { useAuth } from '../../context/AuthContext';
import { mainNavigation, navGroups, standaloneLinks } from '../../config/navigation';
import NavGroup from './NavGroup';

const Sidebar = ({ desktopOpen, mobileOpen, onCloseMobile }) => {
    const { user } = useAuth();
    const location = useLocation();
    const [openGroups, setOpenGroups] = useState(new Set());

    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';
    const isSuperuser = user?.role === 'superuser';

    // Close the mobile drawer whenever the route changes — it's a no-op on
    // desktop where the drawer isn't visible anyway.
    useEffect(() => {
        onCloseMobile();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [location.pathname]);

    const toggleGroup = (key) => {
        setOpenGroups((prev) => {
            const next = new Set(prev);
            if (next.has(key)) next.delete(key);
            else next.add(key);
            return next;
        });
    };

    const isActive = (path) => location.pathname === path;

    const visibleMainNav = mainNavigation.filter(
        (item) => (!item.adminOnly || isAdmin) && (!item.superuserOnly || isSuperuser)
    );
    const visibleGroups = navGroups.filter((g) => !g.adminOnly || isAdmin);
    const visibleStandalone = standaloneLinks.filter(
        (l) => (!l.adminOnly || isAdmin) && (!l.superuserOnly || isSuperuser)
    );

    return (
        <>
            {/* Mobile overlay */}
            {mobileOpen && (
                <div
                    className="fixed inset-0 bg-black/40 z-30 lg:hidden"
                    onClick={onCloseMobile}
                    aria-hidden="true"
                />
            )}

            <motion.aside
                className={`fixed top-0 left-0 h-full bg-white border-r border-neutral-200 z-40 transition-all duration-300
                    ${desktopOpen ? 'lg:w-64' : 'lg:w-20'}
                    w-64 ${mobileOpen ? 'translate-x-0' : '-translate-x-full'} lg:translate-x-0`}
                initial={{ x: -20, opacity: 0 }}
                animate={{ x: 0, opacity: 1 }}
            >
                <div className="flex flex-col h-full">
                    {/* Logo */}
                    <div className="flex items-center h-16 px-4 border-b border-neutral-200">
                        <div className="flex items-center gap-3">
                            <div className="w-10 h-10 rounded-xl flex items-center justify-center overflow-hidden bg-white border border-neutral-200 flex-shrink-0">
                                <img src="/logo.svg" alt={import.meta.env.VITE_APP_NAME} className="w-full h-full object-contain p-1" />
                            </div>
                            {(desktopOpen || mobileOpen) && (
                                <motion.span
                                    initial={{ opacity: 0 }}
                                    animate={{ opacity: 1 }}
                                    className="text-lg font-bold text-neutral-900 whitespace-nowrap"
                                >
                                    {import.meta.env.VITE_APP_NAME}
                                </motion.span>
                            )}
                        </div>
                    </div>

                    {/* Navigation */}
                    <nav className="flex-1 p-4 space-y-1 overflow-y-auto overflow-x-hidden">
                        {visibleMainNav.map((item) => {
                            const Icon = item.icon;
                            return (
                                <Link
                                    key={item.path}
                                    to={item.path}
                                    className={`flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200 ${isActive(item.path)
                                        ? 'bg-primary-50 text-primary-700'
                                        : 'text-neutral-600 hover:bg-neutral-100'
                                        }`}
                                >
                                    <Icon className="w-5 h-5 flex-shrink-0" />
                                    {(desktopOpen || mobileOpen) && (
                                        <span className="font-medium whitespace-nowrap">{item.name}</span>
                                    )}
                                </Link>
                            );
                        })}

                        {visibleGroups.map((group) => (
                            <NavGroup
                                key={group.key}
                                group={group}
                                sidebarOpen={desktopOpen || mobileOpen}
                                isOpen={openGroups.has(group.key)}
                                onToggle={() => toggleGroup(group.key)}
                                isAdmin={isAdmin}
                                isSuperuser={isSuperuser}
                            />
                        ))}

                        {visibleStandalone.map((item) => {
                            const Icon = item.icon;
                            return (
                                <div key={item.path} className="mt-2 pt-2 border-t border-neutral-200">
                                    <Link
                                        to={item.path}
                                        className={`flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200 ${isActive(item.path)
                                            ? 'bg-primary-50 text-primary-700'
                                            : 'text-neutral-600 hover:bg-neutral-100'
                                            }`}
                                    >
                                        <Icon className="w-5 h-5 flex-shrink-0" />
                                        {(desktopOpen || mobileOpen) && (
                                            <span className="font-medium whitespace-nowrap">{item.name}</span>
                                        )}
                                    </Link>
                                </div>
                            );
                        })}
                    </nav>

                    {/* User Info */}
                    <div className="p-4 border-t border-neutral-200">
                        <div className="flex items-center gap-3">
                            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-600 to-accent-600 flex items-center justify-center text-white font-semibold text-sm flex-shrink-0">
                                {user?.first_name?.[0]}{user?.last_name?.[0]}
                            </div>
                            {(desktopOpen || mobileOpen) && (
                                <div className="flex-1 min-w-0">
                                    <p className="text-sm font-medium text-neutral-900 truncate">
                                        {user?.first_name} {user?.last_name}
                                    </p>
                                    <p className="text-xs text-neutral-500 truncate">{user?.email}</p>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </motion.aside>
        </>
    );
};

Sidebar.propTypes = {
    desktopOpen: PropTypes.bool.isRequired,
    mobileOpen: PropTypes.bool.isRequired,
    onCloseMobile: PropTypes.func.isRequired,
};

export default Sidebar;
