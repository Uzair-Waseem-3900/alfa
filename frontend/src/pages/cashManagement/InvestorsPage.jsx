import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Pencil, Trash2, Users } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { useInvestors } from '../../hooks/useCashManagement';
import { extractErrorMessage } from '../../utils/errorMessage';
import Button from '../../components/ui/Button';
import Modal from '../../components/ui/Modal';
import Input from '../../components/ui/Input';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Table from '../../components/ui/Table';
import SearchBar from '../../components/ui/SearchBar';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import Pagination from '../../components/ui/Pagination';
import BackLink from '../../components/ui/BackLink';
import EmptyState from '../../components/ui/EmptyState';
import InlineAlert from '../../components/ui/InlineAlert';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const InvestorsPage = () => {
    const { user } = useAuth();
    const { toast } = useToast();
    const navigate = useNavigate();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const {
        data: investors, meta, page, setPage, loading, error: listError,
        filters, setFilters, refetch, create, update, delete: deleteInvestor,
    } = useInvestors();

    const [showModal, setShowModal] = useState(false);
    const [editingInvestor, setEditingInvestor] = useState(null);
    const [formData, setFormData] = useState({ name: '', contact_number: '', email: '', note: '', growth_rate: '' });
    const [formLoading, setFormLoading] = useState(false);
    const [formError, setFormError] = useState('');
    const [deleteConfirm, setDeleteConfirm] = useState(null);
    const [deleteLoading, setDeleteLoading] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');

    const resetForm = () => {
        setFormData({ name: '', contact_number: '', email: '', note: '', growth_rate: '' });
        setEditingInvestor(null);
        setFormError('');
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setFormError('');
        setFormLoading(true);
        try {
            const payload = { ...formData, growth_rate: (parseFloat(formData.growth_rate) || 0) / 100 };
            if (editingInvestor) {
                await update(editingInvestor.id, payload);
                toast.success('Investor updated successfully');
            } else {
                await create(payload);
                toast.success('Investor created successfully');
            }
            setShowModal(false);
            resetForm();
            refetch();
        } catch (error) {
            setFormError(extractErrorMessage(error, 'Failed to save investor'));
        } finally {
            setFormLoading(false);
        }
    };

    const handleEdit = (investor) => {
        setEditingInvestor(investor);
        setFormData({
            name: investor.name || '',
            contact_number: investor.contact_number || '',
            email: investor.email || '',
            note: investor.note || '',
            growth_rate: investor.growth_rate ? (parseFloat(investor.growth_rate) * 100).toString() : '',
        });
        setShowModal(true);
    };

    const handleDelete = async (id) => {
        setDeleteLoading(true);
        try {
            await deleteInvestor(id);
            setDeleteConfirm(null);
            refetch();
            toast.success('Investor deleted');
        } catch (error) {
            toast.error(extractErrorMessage(error, 'Failed to delete investor'));
        } finally {
            setDeleteLoading(false);
        }
    };

    const handleSearch = (value) => {
        setSearchTerm(value);
        setFilters({ ...filters, search: value });
    };

    const handleRowClick = (investor) => navigate(`/cash-management/investors/${investor.id}`);

    const columns = [
        { key: 'name', label: 'Name' },
        { key: 'contact_number', label: 'Contact', render: (value) => value || <span className="text-neutral-300">—</span> },
        { key: 'email', label: 'Email', render: (value) => value || <span className="text-neutral-300">—</span> },
        {
            key: 'total_invested',
            label: 'Total Invested (PKR)',
            render: (value) => <span className="font-semibold text-info-600">Rs. {fmt(value)}</span>,
        },
        {
            key: 'total_withdrawn',
            label: 'Total Withdrawn (PKR)',
            render: (value) => `Rs. ${fmt(value)}`,
        },
        {
            key: 'net_stake',
            label: 'Net Stake (PKR)',
            render: (value) => <span className="font-semibold text-purple-600">Rs. {fmt(value)}</span>,
        },
        {
            key: 'growth_rate',
            label: 'Growth Rate',
            render: (value) => parseFloat(value) > 0 ? `${(parseFloat(value) * 100).toFixed(2)}% / yr` : <span className="text-neutral-300">—</span>,
        },
        {
            key: 'growth_increased',
            label: 'Growth Increased (PKR)',
            render: (_value, row) => {
                const increase = parseFloat(row.current_worth) - parseFloat(row.net_stake);
                return increase > 0
                    ? <span className="font-semibold text-success-600">+Rs. {fmt(increase)}</span>
                    : <span className="text-neutral-300">Rs. 0.00</span>;
            },
        },
        {
            key: 'current_worth',
            label: 'Current Worth (PKR)',
            render: (value) => <span className="font-semibold text-teal-600">Rs. {fmt(value)}</span>,
        },
        {
            key: 'actions',
            label: 'Actions',
            width: '100px',
            render: (_value, row) => (
                <div className="flex gap-1">
                    <button
                        onClick={(e) => { e.stopPropagation(); handleEdit(row); }}
                        className="inline-flex items-center justify-center w-9 h-9 rounded-lg text-primary-600 hover:bg-primary-50 transition-colors"
                        aria-label="Edit investor"
                    >
                        <Pencil className="w-4 h-4" />
                    </button>
                    <button
                        onClick={(e) => { e.stopPropagation(); setDeleteConfirm(row); }}
                        className="inline-flex items-center justify-center w-9 h-9 rounded-lg text-error-600 hover:bg-error-50 transition-colors"
                        aria-label="Delete investor"
                    >
                        <Trash2 className="w-4 h-4" />
                    </button>
                </div>
            ),
        },
    ];

    if (!isAdmin) {
        return (
            <div className="text-center py-16">
                <h2 className="text-2xl font-semibold text-neutral-900">Access Denied</h2>
                <p className="text-neutral-500 mt-2">Only admins or superusers can view investors.</p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <BackLink to="/cash-management">Back to Cash Management</BackLink>
                    <div className="flex items-center gap-2.5 mt-2">
                        <Users className="w-6 h-6 text-primary-600" />
                        <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900">Investors</h1>
                    </div>
                    <p className="text-neutral-500 mt-1">Manage investors and their capital</p>
                </div>
                <Button onClick={() => { resetForm(); setShowModal(true); }} icon={Plus}>
                    Add Investor
                </Button>
            </div>

            <SearchBar
                onSearch={handleSearch}
                placeholder="Search by name, email, or contact number..."
                value={searchTerm}
            />

            {listError && !loading && (
                <InlineAlert variant="error" title="Couldn't load investors" message={listError} onRetry={refetch} />
            )}

            {loading ? (
                <div className="flex items-center justify-center py-16">
                    <LoadingSpinner size="lg" />
                </div>
            ) : investors.length === 0 ? (
                <EmptyState
                    icon={<Users className="w-8 h-8 text-neutral-400 mx-auto" />}
                    title="No Investors Yet"
                    description="Add an investor to start recording their capital."
                />
            ) : (
                <>
                    <Table columns={columns} data={investors} onRowClick={handleRowClick} />
                    {meta.totalPages > 1 && (
                        <Pagination currentPage={meta.currentPage} totalPages={meta.totalPages} onPageChange={setPage} />
                    )}
                </>
            )}

            {/* Create/Edit Modal */}
            <Modal
                isOpen={showModal}
                onClose={() => { setShowModal(false); resetForm(); }}
                title={editingInvestor ? 'Edit Investor' : 'Add Investor'}
                size="lg"
            >
                <form onSubmit={handleSubmit} className="space-y-4">
                    <Input
                        label="Name"
                        value={formData.name}
                        onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                        placeholder="Enter investor name"
                        required
                    />
                    <Input
                        label="Contact Number"
                        value={formData.contact_number}
                        onChange={(e) => setFormData({ ...formData, contact_number: e.target.value })}
                        placeholder="Optional"
                    />
                    <Input
                        label="Email"
                        type="email"
                        value={formData.email}
                        onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                        placeholder="Optional"
                    />
                    <Input
                        label="Note"
                        value={formData.note}
                        onChange={(e) => setFormData({ ...formData, note: e.target.value })}
                        placeholder="Optional"
                    />
                    <Input
                        label="Annual Growth Rate (%)"
                        type="number"
                        step="0.01"
                        min="0"
                        value={formData.growth_rate}
                        onChange={(e) => setFormData({ ...formData, growth_rate: e.target.value })}
                        placeholder="e.g. 2 for 2% annual — 0 or blank for no growth"
                    />

                    {formError && <InlineAlert variant="error" message={formError} />}

                    <div className="flex justify-end gap-3 pt-4">
                        <Button type="button" variant="secondary" onClick={() => { setShowModal(false); resetForm(); }}>
                            Cancel
                        </Button>
                        <Button type="submit" loading={formLoading}>
                            {editingInvestor ? 'Update Investor' : 'Create Investor'}
                        </Button>
                    </div>
                </form>
            </Modal>

            {/* Delete Confirmation */}
            <ConfirmDialog
                isOpen={!!deleteConfirm}
                onClose={() => setDeleteConfirm(null)}
                onConfirm={() => handleDelete(deleteConfirm?.id)}
                title="Delete Investor"
                message={`Are you sure you want to delete "${deleteConfirm?.name}"? This is blocked if they have any recorded transactions.`}
                loading={deleteLoading}
            />
        </div>
    );
};

export default InvestorsPage;
