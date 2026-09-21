import { useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { Plus, X } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { extractErrorMessage } from '../../utils/errorMessage';
import { salesManApi } from '../../services/salesManApi';
import { useSalesManList } from '../../hooks/useSalesMan';
import SalesManTable from '../../components/salesMan/SalesManTable';
import SalesManForm from '../../components/salesMan/SalesManForm';
import SearchBar from '../../components/ui/SearchBar';
import Button from '../../components/ui/Button';
import Modal from '../../components/ui/Modal';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import Pagination from '../../components/ui/Pagination';
import InlineAlert from '../../components/ui/InlineAlert';
import Card from '../../components/ui/Card';

const SalesMenPage = () => {
    const { user } = useAuth();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';
    const navigate = useNavigate();
    const { toast } = useToast();

    const {
        data, meta, setPage, loading, initialLoading, error,
        setFilters, refetch,
    } = useSalesManList();

    const [searchTerm, setSearchTerm] = useState('');
    const [showModal, setShowModal] = useState(false);
    const [formLoading, setFormLoading] = useState(false);
    const [deleteConfirm, setDeleteConfirm] = useState(null);
    const [deleting, setDeleting] = useState(false);

    if (!isAdmin) {
        return <Navigate to="/dashboard" replace />;
    }

    const handleSearch = (value) => {
        setSearchTerm(value);
        setFilters({ search: value || undefined });
    };

    const handleResetFilters = () => {
        setSearchTerm('');
        setFilters({});
    };

    const handleSubmit = async (formData) => {
        setFormLoading(true);
        try {
            await salesManApi.salesMen.create(formData);
            toast.success('Sales man created successfully.');
            setShowModal(false);
            refetch();
        } catch (err) {
            toast.error(extractErrorMessage(err, 'Failed to create sales man.'));
            throw err;
        } finally {
            setFormLoading(false);
        }
    };

    const handleDelete = async () => {
        if (!deleteConfirm) return;
        setDeleting(true);
        try {
            await salesManApi.salesMen.delete(deleteConfirm);
            toast.success('Sales man deleted successfully.');
            setDeleteConfirm(null);
            refetch();
        } catch (err) {
            toast.error(extractErrorMessage(err, 'Failed to delete sales man.'));
        } finally {
            setDeleting(false);
        }
    };

    const handleRowClick = (salesMan) => {
        navigate(`/sales-man/${salesMan.id}`);
    };

    if (initialLoading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <h1 className="text-3xl font-bold text-neutral-900">Sales Men</h1>
                    <p className="text-neutral-500 mt-1">Manage sales men and their customer assignments</p>
                </div>
                <Button onClick={() => setShowModal(true)} icon={Plus}>
                    Add Sales Man
                </Button>
            </div>

            <Card className="p-4 sm:p-5" hover={false}>
                <div className="flex flex-col sm:flex-row gap-3">
                    <SearchBar
                        onSearch={handleSearch}
                        placeholder="Search by name or code..."
                        className="flex-1"
                        value={searchTerm}
                    />
                    {searchTerm && (
                        <button
                            onClick={handleResetFilters}
                            className="flex items-center justify-center gap-1.5 px-4 py-2.5 min-h-[44px] bg-neutral-100 text-neutral-700 rounded-xl hover:bg-neutral-200 transition-colors flex-shrink-0"
                        >
                            <X className="w-4 h-4" />
                            Clear
                        </button>
                    )}
                </div>
            </Card>

            {error && <InlineAlert variant="error" message={error} onRetry={refetch} />}

            <Card className="p-0 overflow-hidden" hover={false}>
                <div className={`relative transition-opacity ${loading ? 'opacity-60' : 'opacity-100'}`}>
                    {loading && (
                        <div className="absolute right-4 top-4 z-10">
                            <LoadingSpinner size="sm" />
                        </div>
                    )}
                    <SalesManTable
                        salesMen={data}
                        onRowClick={handleRowClick}
                        onDelete={(id) => setDeleteConfirm(id)}
                        isAdmin={isAdmin}
                    />
                </div>
            </Card>

            {meta.totalPages > 1 && (
                <Pagination
                    currentPage={meta.currentPage}
                    totalPages={meta.totalPages}
                    onPageChange={setPage}
                />
            )}

            <Modal isOpen={showModal} onClose={() => setShowModal(false)} title="Create Sales Man">
                <SalesManForm
                    onSubmit={handleSubmit}
                    onCancel={() => setShowModal(false)}
                    loading={formLoading}
                />
            </Modal>

            <ConfirmDialog
                isOpen={!!deleteConfirm}
                onClose={() => setDeleteConfirm(null)}
                onConfirm={handleDelete}
                title="Delete Sales Man"
                message="Are you sure you want to delete this sales man? This is only possible when every one of his link names has zero customers assigned."
                variant="danger"
                loading={deleting}
            />
        </div>
    );
};

export default SalesMenPage;
