import { useState } from 'react';
import { useParams, useNavigate, Navigate } from 'react-router-dom';
import { Users, Wallet, Plus, X, Tag, Pencil, Receipt } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { extractErrorMessage } from '../../utils/errorMessage';
import { salesManApi } from '../../services/salesManApi';
import { useSalesManDetail, useSalesManLinkNames } from '../../hooks/useSalesMan';
import SalesManForm from '../../components/salesMan/SalesManForm';
import BackLink from '../../components/ui/BackLink';
import Card from '../../components/ui/Card';
import Badge from '../../components/ui/Badge';
import Button from '../../components/ui/Button';
import Input from '../../components/ui/Input';
import Modal from '../../components/ui/Modal';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import InlineAlert from '../../components/ui/InlineAlert';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toLocaleString('en-PK', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

// This page shows only the sales man's own stored fields (name, code,
// address, phone, the O(1) total_customers/total_outstanding counters) and
// link-name management. Customers and invoices are each their own page,
// navigated to via a button below — their data is fetched only once that
// page actually mounts, not preloaded here as inline tabs.
const SalesManDetailPage = () => {
    const { id } = useParams();
    const { user } = useAuth();
    const navigate = useNavigate();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const { salesMan, loading, error, refetch } = useSalesManDetail(id);
    const { linkNames, refetch: refetchLinkNames } = useSalesManLinkNames(id);

    const [newLinkName, setNewLinkName] = useState('');
    const [addingLinkName, setAddingLinkName] = useState(false);
    const [deleteLinkTarget, setDeleteLinkTarget] = useState(null);
    const [deletingLinkName, setDeletingLinkName] = useState(false);

    const [showEditModal, setShowEditModal] = useState(false);
    const [editLoading, setEditLoading] = useState(false);

    if (!isAdmin) {
        return <Navigate to="/dashboard" replace />;
    }

    const handleAddLinkName = async (e) => {
        e.preventDefault();
        if (!newLinkName.trim()) return;
        setAddingLinkName(true);
        try {
            await salesManApi.linkNames.create(id, { name: newLinkName.trim() });
            toast.success('Link name added.');
            setNewLinkName('');
            refetchLinkNames();
        } catch (err) {
            toast.error(extractErrorMessage(err, 'Failed to add link name.'));
        } finally {
            setAddingLinkName(false);
        }
    };

    const handleDeleteLinkName = async () => {
        if (!deleteLinkTarget) return;
        setDeletingLinkName(true);
        try {
            await salesManApi.linkNames.delete(deleteLinkTarget);
            toast.success('Link name removed.');
            setDeleteLinkTarget(null);
            refetchLinkNames();
        } catch (err) {
            toast.error(extractErrorMessage(err, 'Failed to remove link name.'));
        } finally {
            setDeletingLinkName(false);
        }
    };

    const handleEditSubmit = async (formData) => {
        setEditLoading(true);
        try {
            await salesManApi.salesMen.update(id, formData);
            toast.success('Sales man updated successfully.');
            setShowEditModal(false);
            refetch();
        } catch (err) {
            toast.error(extractErrorMessage(err, 'Failed to update sales man.'));
            throw err;
        } finally {
            setEditLoading(false);
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    if (error || !salesMan) {
        return <InlineAlert variant="error" message={error || 'Sales man not found.'} onRetry={refetch} />;
    }

    return (
        <div className="space-y-6">
            <BackLink to="/sales-man">Back to Sales Men</BackLink>

            <div className="flex flex-col gap-4">
                <div>
                    <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900 break-words">{salesMan.name}</h1>
                    <p className="text-neutral-500 mt-1">Code: {salesMan.code}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                    <Button icon={Users} onClick={() => navigate(`/sales-man/${id}/customers`)}>
                        View Customers
                    </Button>
                    <Button icon={Receipt} onClick={() => navigate(`/sales-man/${id}/invoices`)}>
                        View Invoices
                    </Button>
                    <Button variant="secondary" icon={Pencil} onClick={() => setShowEditModal(true)}>
                        Edit Details
                    </Button>
                </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Card className="p-5 flex items-center gap-4" hover={false}>
                    <div className="w-12 h-12 flex-shrink-0 rounded-xl bg-primary-50 flex items-center justify-center">
                        <Users className="w-6 h-6 text-primary-600" />
                    </div>
                    <div className="min-w-0">
                        <p className="text-sm text-neutral-500">Total Customers</p>
                        <p className="text-2xl font-bold text-neutral-900">{salesMan.total_customers}</p>
                    </div>
                </Card>
                <Card className="p-5 flex items-center gap-4" hover={false}>
                    <div className="w-12 h-12 flex-shrink-0 rounded-xl bg-amber-50 flex items-center justify-center">
                        <Wallet className="w-6 h-6 text-amber-600" />
                    </div>
                    <div className="min-w-0">
                        <p className="text-sm text-neutral-500">Total Outstanding</p>
                        <p className="text-2xl font-bold text-neutral-900 break-words">Rs. {fmt(salesMan.total_outstanding)}</p>
                    </div>
                </Card>
            </div>

            <Card className="p-5 space-y-4" hover={false}>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                        <p className="text-sm text-neutral-500">Address</p>
                        <p className="text-neutral-900">{salesMan.address || 'N/A'}</p>
                    </div>
                    <div>
                        <p className="text-sm text-neutral-500">Phone</p>
                        <p className="text-neutral-900">{salesMan.phone || 'N/A'}</p>
                    </div>
                </div>

                <div>
                    <h3 className="text-sm font-semibold text-neutral-700 mb-2">Link Names</h3>
                    <p className="text-xs text-neutral-500 mb-3">
                        A link name is the segment embedded in every assigned customer's code. Removing one
                        is only possible once it has zero customers linked to it.
                    </p>
                    <div className="flex flex-wrap gap-2 mb-3">
                        {linkNames.length === 0 && (
                            <span className="text-sm text-neutral-400">No link names yet.</span>
                        )}
                        {linkNames.map((ln) => (
                            <Badge key={ln.id} variant="default" className="flex items-center gap-1.5 pr-1">
                                <Tag className="w-3 h-3" />
                                {ln.name}
                                <button
                                    onClick={() => setDeleteLinkTarget(ln.id)}
                                    className="ml-1 p-0.5 rounded hover:bg-neutral-200"
                                    title="Remove link name"
                                    aria-label="Remove link name"
                                >
                                    <X className="w-3 h-3" />
                                </button>
                            </Badge>
                        ))}
                    </div>
                    <form onSubmit={handleAddLinkName} className="flex flex-col sm:flex-row gap-2 max-w-sm">
                        <Input
                            value={newLinkName}
                            onChange={(e) => setNewLinkName(e.target.value)}
                            placeholder="New link name, e.g. FSD"
                            className="flex-1"
                        />
                        <Button type="submit" icon={Plus} loading={addingLinkName} disabled={!newLinkName.trim()} className="sm:w-auto w-full">
                            Add
                        </Button>
                    </form>
                </div>
            </Card>

            <ConfirmDialog
                isOpen={!!deleteLinkTarget}
                onClose={() => setDeleteLinkTarget(null)}
                onConfirm={handleDeleteLinkName}
                title="Remove Link Name"
                message="Are you sure? This is only possible when zero customers are currently assigned to this link name."
                variant="danger"
                loading={deletingLinkName}
            />

            <Modal isOpen={showEditModal} onClose={() => setShowEditModal(false)} title="Edit Sales Man">
                <SalesManForm
                    initialData={salesMan}
                    onSubmit={handleEditSubmit}
                    onCancel={() => setShowEditModal(false)}
                    loading={editLoading}
                />
            </Modal>
        </div>
    );
};

export default SalesManDetailPage;
