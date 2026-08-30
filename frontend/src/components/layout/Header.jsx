import PropTypes from 'prop-types';
import { Link } from 'react-router-dom';
import { Menu } from 'lucide-react';
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
