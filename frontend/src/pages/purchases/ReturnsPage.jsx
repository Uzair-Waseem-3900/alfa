import { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { purchasesApi } from '../../services/purchasesApi';
import { extractErrorMessage } from '../../utils/errorMessage';
import Table from '../../components/ui/Table';
import Button from '../../components/ui/Button';
import BackLink from '../../components/ui/BackLink';
import Modal from '../../components/ui/Modal';
import Input from '../../components/ui/Input';
import Select from '../../components/ui/Select';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Badge from '../../components/ui/Badge';
import Pagination from '../../components/ui/Pagination';
import InlineAlert from '../../components/ui/InlineAlert';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import EmptyState from '../../components/ui/EmptyState';
import { usePaginatedList } from '../../hooks/usePaginatedList';
import { useParams, useNavigate } from 'react-router-dom';
import { Plus, Trash2, CheckCircle2, Undo2 } from 'lucide-react';

const ReturnsPage = () => {
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';
    const { orderId } = useParams();
    const navigate = useNavigate();

    const [showCreateModal, setShowCreateModal] = useState(false);
    const [formData, setFormData] = useState({
        items: [],
        note: '',
    });
    const [orderItems, setOrderItems] = useState([]);
    const [formLoading, setFormLoading] = useState(false);
    const [formError, setFormError] = useState('');
    const [acceptTarget, setAcceptTarget] = useState(null);
    const [acceptLoading, setAcceptLoading] = useState(false);

    const fetchReturnsPage = (params) => {
        if (!orderId || orderId === 'undefined') {
            return Promise.resolve({ results: [], count: 0, total_pages: 1, current_page: 1, page_size: 25 });
        }
        return purchasesApi.returns.getByOrder(orderId, params);
    };

    const {
        data: returns, meta, page, setPage, loading, initialLoading, error: listError,
        refetch: fetchReturns,
    } = usePaginatedList(fetchReturnsPage, {}, 25, [orderId]);

    useEffect(() => {
        if (orderId && orderId !== 'undefined') {
            fetchOrderItems();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [orderId]);

    const fetchOrderItems = async () => {
        try {
            const order = await purchasesApi.orders.getById(orderId);
            setOrderItems(order.items || []);
        } catch (error) {
            console.error('Failed to fetch order items:', error);
        }
    };

    const handleCreateReturn = async (e) => {
        e.preventDefault();
        setFormLoading(true);
        setFormError('');
        try {
            await purchasesApi.returns.create(orderId, {
                items: formData.items.map(item => ({
                    invoice_item_id: item.invoice_item_id,
                    quantity: item.quantity,
                })),
                note: formData.note,
            });
            setShowCreateModal(false);
            resetForm();
            fetchReturns();
            toast.success('Return created successfully.');
        } catch (error) {
            console.error('Failed to create return:', error);
            setFormError(extractErrorMessage(error, 'Failed to create return.'));
        } finally {
            setFormLoading(false);
        }
    };

    const handleAcceptReturn = async () => {
        if (!acceptTarget) return;
        setAcceptLoading(true);
        try {
            await purchasesApi.returns.accept(acceptTarget);
            fetchReturns();
            toast.success('Return accepted.');
            setAcceptTarget(null);
        } catch (error) {
            console.error('Failed to accept return:', error);
            toast.error(extractErrorMessage(error, 'Failed to accept return.'));
        } finally {
            setAcceptLoading(false);
        }
    };

    const resetForm = () => {
        setFormData({
            items: [],
            note: '',
        });
        setFormError('');
    };

    const handleAddReturnItem = () => {
        setFormData(prev => ({
            ...prev,
            items: [
                ...prev.items,
                { invoice_item_id: '', quantity: 1 }
            ]
        }));
    };

    const handleUpdateReturnItem = (index, field, value) => {
        setFormData(prev => ({
            ...prev,
            items: prev.items.map((item, i) =>
                i === index ? { ...item, [field]: value } : item
            )
        }));
    };

    const handleRemoveReturnItem = (index) => {
        setFormData(prev => ({
            ...prev,
            items: prev.items.filter((_, i) => i !== index)
        }));
    };

    const getStatusBadge = (status) => {
        const variants = {
            pending: 'pending',
            accepted: 'accepted',
        };
        return <Badge variant={variants[status] || 'default'}>{status}</Badge>;
    };

    const columns = [
        { key: 'reference_number', label: 'Return #', width: '140px' },
        {
            key: 'order_number',
            label: 'Order #',
            render: (value) => value || 'N/A'
        },
        {
            key: 'supplier_name',
            label: 'Supplier',
            render: (value) => value || 'N/A'
        },
        {
            key: 'status',
            label: 'Status',
            render: getStatusBadge
        },
        {
            key: 'total_return_amount',
            label: 'Amount (PKR)',
            render: (value) => {
                const num = typeof value === 'string' ? parseFloat(value) : value;
                return <span className="font-medium tabular-nums">{isNaN(num) ? '0.00' : num.toFixed(2)}</span>;
            }
        },
        {
            key: 'created_at',
            label: 'Date',
            render: (value) => value ? new Date(value).toLocaleDateString() : 'N/A'
        },
        { key: 'note', label: 'Note', render: (value) => value || <span className="text-neutral-400">&mdash;</span> },
        {
            key: 'actions',
            label: 'Actions',
            width: '150px',
            render: (_, row) => row.status === 'pending' && isAdmin && (
                <Button
                    size="sm"
                    variant="success"
                    icon={CheckCircle2}
                    onClick={(e) => {
                        e.stopPropagation();
                        setAcceptTarget(row.id);
                    }}
                >
                    Accept
                </Button>
            ),
        },
    ];

    // Full-page spinner only before the very first fetch completes.
    if (initialLoading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    if (!orderId || orderId === 'undefined') {
        return (
            <div className="text-center py-12">
                <h2 className="text-2xl font-semibold text-neutral-900">Invalid Order</h2>
                <p className="text-neutral-500 mt-2">Please go back to the orders list.</p>
                <BackLink to="/purchases/orders" className="mt-4">Back to Orders</BackLink>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <h1 className="text-3xl font-bold text-neutral-900">Order Returns</h1>
                    <p className="text-neutral-500 mt-1">
                        Manage returns for Order #{orderId}
                    </p>
                    <div className="mt-3">
                        <BackLink to="/purchases/returns" direction="right">View All Returns</BackLink>
                    </div>
                </div>
                {isAdmin && (
                    <Button
                        onClick={() => {
                            resetForm();
                            setShowCreateModal(true);
                        }}
                        icon={Plus}
                    >
                        Create Return
                    </Button>
                )}
            </div>

            {listError && (
                <InlineAlert variant="error" message={listError} onRetry={fetchReturns} />
            )}

            <div className={`relative transition-opacity ${loading ? 'opacity-60' : 'opacity-100'}`}>
                {loading && (
                    <div className="absolute right-2 top-2 z-10">
                        <LoadingSpinner size="sm" />
                    </div>
                )}
                {returns.length === 0 && !loading ? (
                    <EmptyState
                        title="No returns for this order"
                        description="Returns created for this order will appear here."
                    />
                ) : (
                    <Table
                        columns={columns}
                        data={returns}
                        onRowClick={(ret) => navigate(`/purchases/returns/${ret.id}`)}
                    />
                )}
            </div>

            {meta.totalPages > 1 && (
                <Pagination
                    currentPage={meta.currentPage}
                    totalPages={meta.totalPages}
                    onPageChange={setPage}
                />
            )}

            {/* Create Return Modal */}
            <Modal
                isOpen={showCreateModal}
                onClose={() => {
                    setShowCreateModal(false);
                    resetForm();
                }}
                title="Create Return"
                size="lg"
            >
                <form onSubmit={handleCreateReturn} className="space-y-6 max-h-[70vh] overflow-y-auto">
                    <div>
                        <div className="flex items-center justify-between mb-3">
                            <h3 className="font-semibold text-neutral-900">Items to Return</h3>
                            <Button size="sm" variant="secondary" icon={Plus} onClick={handleAddReturnItem}>
                                Add Item
                            </Button>
                        </div>

                        <div className="space-y-2">
                            {formData.items.length === 0 ? (
                                <p className="text-center text-neutral-500 py-4">No items added yet</p>
                            ) : (
                                formData.items.map((item, index) => (
                                    <div key={index} className="grid grid-cols-1 md:grid-cols-3 gap-2 p-3 bg-neutral-50 rounded-xl border border-neutral-200">
                                        <Select
                                            label="Product"
                                            value={item.invoice_item_id}
                                            onChange={(e) => handleUpdateReturnItem(index, 'invoice_item_id', parseInt(e.target.value))}
                                            options={orderItems.map(i => ({
                                                value: i.id,
                                                label: `${i.product_name} (Returnable: ${i.returnable_quantity})`,
                                            }))}
                                            placeholder="Select item"
                                            required
                                        />
                                        <Input
                                            label="Quantity"
                                            type="number"
                                            value={item.quantity}
                                            onChange={(e) => handleUpdateReturnItem(index, 'quantity', parseInt(e.target.value) || 0)}
                                            required
                                        />
                                        <div className="flex items-end">
                                            <Button
                                                size="sm"
                                                variant="danger"
                                                icon={Trash2}
                                                onClick={() => handleRemoveReturnItem(index)}
                                                className="w-full"
                                            >
                                                Remove
                                            </Button>
                                        </div>
                                    </div>
                                ))
                            )}
                        </div>
                    </div>

                    <Input
                        label="Note"
                        value={formData.note}
                        onChange={(e) => setFormData({ ...formData, note: e.target.value })}
                        placeholder="Return note (optional)"
                    />

                    {formError && <InlineAlert variant="error" message={formError} />}

                    <div className="flex justify-end gap-3 pt-4 border-t border-neutral-200">
                        <Button
                            type="button"
                            variant="secondary"
                            onClick={() => {
                                setShowCreateModal(false);
                                resetForm();
                            }}
                        >
                            Cancel
                        </Button>
                        <Button type="submit" loading={formLoading} icon={Undo2}>
                            Create Return
                        </Button>
                    </div>
                </form>
            </Modal>

            <ConfirmDialog
                isOpen={!!acceptTarget}
                onClose={() => setAcceptTarget(null)}
                onConfirm={handleAcceptReturn}
                title="Accept Return"
                message="Are you sure you want to accept this return? This action cannot be undone."
                confirmText="Accept"
                variant="primary"
                loading={acceptLoading}
            />
        </div>
    );
};

export default ReturnsPage;
