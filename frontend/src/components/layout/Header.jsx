import PropTypes from 'prop-types';
import { Link } from 'react-router-dom';
import { Menu, Sparkles } from 'lucide-react';
import Button from '../ui/Button';

const ROLE_LABELS = { superuser: 'Superuser', admin: 'Admin' };

const Header = ({ user, onToggleSidebar, onLogout }) => {
    return (
        <header className="sticky top-0 z-30 bg-white/80 backdrop-blur-lg border-b border-neutral-200">
            <div className="flex items-center justify-between h-16 px-4 sm:px-6">
                <button
                    type="button"
                    onClick={onToggleSidebar}
                    aria-label="Toggle navigation"
                    className="p-3 -m-1 rounded-lg hover:bg-neutral-100 active:bg-neutral-200 transition-colors cursor-pointer"
                >
                    <Menu className="w-5 h-5 text-neutral-600" />
                </button>

                <div className="flex items-center gap-2 sm:gap-4">
                    {/* AI assistant — admins and superusers only (the page redirects everyone else) */}
                    {(user?.role === 'admin' || user?.role === 'superuser') && (
                        <Link
                            to="/agent"
                            title="Open the AI assistant"
                            aria-label="Open the AI assistant"
                            className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-primary-700 to-accent-600 px-3 sm:px-4 min-h-[40px] text-sm font-medium text-white shadow-sm hover:from-primary-800 hover:to-accent-700 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 focus-visible:ring-offset-2"
                        >
                            <Sparkles className="w-4 h-4" aria-hidden="true" />
                            <span className="hidden sm:inline">Assistant</span>
                        </Link>
                    )}
                    <Link
                        to="/profile"
                        title="View profile"
                        className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-neutral-100 active:bg-neutral-200 transition-colors"
                    >
                        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-primary-600 to-accent-600 flex items-center justify-center text-white text-xs font-semibold flex-shrink-0">
                            {user?.first_name?.[0]}{user?.last_name?.[0]}
                        </div>
                        <span className="hidden sm:flex flex-col items-start leading-tight">
                            <span className="text-sm font-medium text-neutral-900">
                                {user?.first_name} {user?.last_name}
                            </span>
                            <span className="text-xs text-neutral-500">
                                {ROLE_LABELS[user?.role] || 'User'}
                            </span>
                        </span>
                    </Link>
                    <Button size="sm" variant="secondary" onClick={onLogout}>
                        Logout
                    </Button>
                </div>
            </div>
        </header>
    );
};

Header.propTypes = {
    user: PropTypes.object,
    onToggleSidebar: PropTypes.func.isRequired,
    onLogout: PropTypes.func.isRequired,
};

export default Header;
