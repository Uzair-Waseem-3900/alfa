import { useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import Sidebar from './Sidebar';
import Header from './Header';

const LG_BREAKPOINT = 1024;

const Layout = ({ children }) => {
    const { user, logout } = useAuth();
    const [sidebarOpen, setSidebarOpen] = useState(true);
    const [mobileOpen, setMobileOpen] = useState(false);

    const handleToggleSidebar = () => {
        if (window.innerWidth < LG_BREAKPOINT) {
            setMobileOpen((prev) => !prev);
        } else {
            setSidebarOpen((prev) => !prev);
        }
    };

    return (
        <div className="min-h-screen bg-neutral-50">
            <Sidebar
                desktopOpen={sidebarOpen}
                mobileOpen={mobileOpen}
                onCloseMobile={() => setMobileOpen(false)}
            />

            <div className={`transition-all duration-300 ml-0 ${sidebarOpen ? 'lg:ml-64' : 'lg:ml-20'}`}>
                <Header user={user} onToggleSidebar={handleToggleSidebar} onLogout={logout} />
                <main className="p-4 sm:p-6">
                    {children}
                </main>
            </div>
        </div>
    );
};

export default Layout;
