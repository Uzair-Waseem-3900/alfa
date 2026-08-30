import { useAuth } from '../context/AuthContext';
import NormalUserDashboard from '../components/dashboard/NormalUserDashboard';
import AdminDashboard from '../components/dashboard/AdminDashboard';
import LoadingSpinner from '../components/ui/LoadingSpinner';

const DashboardPage = () => {
    const { user, loading } = useAuth();

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    return isAdmin ? <AdminDashboard /> : <NormalUserDashboard />;
};

export default DashboardPage;