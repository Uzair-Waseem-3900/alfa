import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { extractErrorMessage } from '../../utils/errorMessage';
import { purchasesApi } from '../../services/purchasesApi';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Badge from '../../components/ui/Badge';
import InlineAlert from '../../components/ui/InlineAlert';
import ShelfAllocationEditor from '../../components/shared/ShelfAllocationEditor';
import BackLink from '../../components/ui/BackLink';

const formatCurrency = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : value;
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

// ─── Mark as Found modal ──────────────────────────────────────────────────────

const MarkFoundModal = ({ item, onClose, onSuccess }) => {
    const [quantity, setQuantity] = useState('1');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [shelfAllocations, setShelfAllocations] = useState([]);

    const maxQty = item.returnable_quantity ?? (item.quantity - item.found_quantity);

    // Put-away — any active shelf is valid, so this searches the full shelf
    // list by name on demand (a large factory can have hundreds of shelves).
    const searchShelvesForPutAway = async (query) => {
        const res = await purchasesApi.shelves.getAll({ search: query, page_size: 25 });
        const results = res?.results || res || [];
        return results.map((s) => ({ value: s.id, label: s.name, name: s.name }));
    };

    const allocatedTotal = shelfAllocations.reduce((sum, a) => sum + (parseInt(a.quantity, 10) || 0), 0);
    const qtyNum = parseInt(quantity, 10) || 0;
    const allocationMismatch = allocatedTotal !== qtyNum;

    const handleSubmit = async (e) => {
        e.preventDefault();
        const qty = parseInt(quantity, 10);
        if (!qty || qty <= 0) {
            setError('Enter a valid quantity greater than zero.');
            return;
        }
        if (qty > maxQty) {
            setError(`Cannot exceed returnable quantity of ${maxQty}.`);
            return;
        }
        if (allocationMismatch) {
            setError('Shelf allocations must sum exactly to the quantity found.');
            return;
        }
        setError('');
        setLoading(true);
        try {
            await purchasesApi.lostInventory.markFound(
                item.id,
                qty,
                shelfAllocations.map((a) => ({
                    shelf_id: parseInt(a.shelf_id, 10),
                    quantity: parseInt(a.quantity, 10),
                })),
            );
            onSuccess();
        } catch (err) {
            const data = err.response?.data;
            if (data && typeof data === 'object') {
                const messages = Object.entries(data)
                    .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`)
                    .join('\n');
                setError(messages);
            } else {
                setError(err.message || 'Failed to mark as found. Please try again.');
            }
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6 space-y-4">
                <div>
                    <h3 className="text-lg font-semibold text-neutral-900">Mark as Found</h3>
                    <p className="text-sm text-neutral-500 mt-1">
                        Restoring stock for <span className="font-medium text-neutral-800">{item.product_name}</span>
                    </p>
                </div>

                <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                        <p className="text-neutral-500">Originally Lost</p>
                        <p className="font-medium">{item.quantity}</p>
                    </div>
                    <div>
                        <p className="text-neutral-500">Already Found</p>
                        <p className="font-medium text-success-700">{item.found_quantity}</p>
                    </div>
                    <div>
                        <p className="text-neutral-500">Still Missing</p>
                        <p className="font-medium text-warning-700">{maxQty}</p>
                    </div>
                    <div>
                        <p className="text-neutral-500">Unit Cost (FIFO)</p>
                        <p className="font-medium">Rs. {formatCurrency(item.unit_cost)}</p>
                    </div>
                </div>

                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-neutral-700 mb-1.5">
                            Quantity Found
                        </label>
                        <input
                            type="number"
                            min="1"
                            max={maxQty}
                            value={quantity}
                            onChange={(e) => {
                                const raw = e.target.value;
                                if (raw !== '' && !/^\d+$/.test(raw)) return;
                                setQuantity(raw);
                            }}
                            className="w-full px-4 py-3 bg-white border border-neutral-200 rounded-xl focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 outline-none transition-all"
                            autoFocus
                        />
                        <p className="text-xs text-neutral-400 mt-1">Maximum: {maxQty}</p>
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-neutral-700 mb-1.5">
                            Shelf Allocation (where the found stock is placed)
                        </label>
                        <ShelfAllocationEditor
                            mode="putaway"
                            value={shelfAllocations}
                            onChange={setShelfAllocations}
                            onSearchShelves={searchShelvesForPutAway}
                            requiredQuantity={qtyNum}
                        />
                    </div>

                    {error && <InlineAlert variant="error" message={error} />}

                    <div className="flex gap-3 pt-2">
                        <Button
                            type="button"
                            variant="secondary"
                            className="flex-1"
                            onClick={onClose}
                            disabled={loading}
                        >
                            Cancel
                        </Button>
                        <Button
                            type="submit"
                            variant="success"
                            className="flex-1"
                            loading={loading}
                            disabled={allocationMismatch}
                        >
                            Confirm Found
                        </Button>
                    </div>
                </form>
            </div>
        </div>
    );
};

// ─── Main page ────────────────────────────────────────────────────────────────

const LostInventoryDetailPage = () => {
    const { recordId } = useParams();
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const [record, setRecord] = useState(null);
    const [loading, setLoading] = useState(true);
    const [modalItem, setModalItem] = useState(null);   // item to mark-as-found

    const fetchRecord = async () => {
        setLoading(true);
        try {
            const data = await purchasesApi.lostInventory.getById(recordId);
            setRecord(data);
        } catch (err) {
            console.error('Failed to fetch lost inventory record:', err);
            toast.error(extractErrorMessage(err, 'Failed to load lost inventory record'));
            setRecord(null);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchRecord();
    }, [recordId]);

    const handleMarkFoundSuccess = async () => {
        const itemName = modalItem?.product_name;
        setModalItem(null);
        await fetchRecord();
        toast.success(`Stock restored for "${itemName}"`);
    };

    // ── guards ────────────────────────────────────────────────────────────────

    if (!isAdmin) {
        return (
            <div className="text-center py-12">
                <h2 className="text-2xl font-semibold text-neutral-900">Access Denied</h2>
                <p className="text-neutral-500 mt-2">Only admins or superusers can view this page.</p>
                <BackLink to="/purchases/lost-inventory/records" className="mt-4">Back to Records</BackLink>
            </div>
        );
    }

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    if (!record) {
        return (
            <div className="text-center py-12">
                <h2 className="text-2xl font-semibold text-neutral-900">Record Not Found</h2>
                <p className="text-neutral-500 mt-1">The lost inventory record you&apos;re looking for doesn&apos;t exist.</p>
                <BackLink to="/purchases/lost-inventory/records" className="mt-4">Back to Records</BackLink>
            </div>
        );
    }

    const items = record.items || [];
    const totalRecovered = items.reduce((sum, it) => sum + parseFloat(it.recovered_amount || 0), 0);
    const netLoss = parseFloat(record.total_lost_amount || 0) - totalRecovered;
    const allFound = items.length > 0 && items.every((it) => (it.returnable_quantity ?? (it.quantity - it.found_quantity)) === 0);

    return (
        <>
            {/* Mark-as-Found modal */}
            {modalItem && (
                <MarkFoundModal
                    item={modalItem}
                    onClose={() => setModalItem(null)}
                    onSuccess={handleMarkFoundSuccess}
                />
            )}

            <div className="space-y-6">
                {/* Header */}
                <div className="flex items-start justify-between">
                    <div>
                        <BackLink to="/purchases/lost-inventory/records">Back to Lost Inventory Records</BackLink>
                        <h1 className="text-3xl font-bold text-neutral-900 mt-1">Lost Inventory Detail</h1>
                        <div className="flex items-center gap-3 mt-1">
                            <p className="text-neutral-500 font-mono">{record.reference_number}</p>
                            {allFound ? (
                                <Badge variant="success">Fully Recovered</Badge>
                            ) : (
                                <Badge variant="error">Active Loss</Badge>
                            )}
                        </div>
                    </div>
                </div>

                {/* Summary cards */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <Card className="p-4">
                        <p className="text-xs text-neutral-500 mb-1">Total Lost Value</p>
                        <p className="text-xl font-bold text-error-600">
                            Rs. {formatCurrency(record.total_lost_amount)}
                        </p>
                    </Card>
                    <Card className="p-4">
                        <p className="text-xs text-neutral-500 mb-1">Recovered Value</p>
                        <p className="text-xl font-bold text-success-600">
                            Rs. {formatCurrency(totalRecovered)}
                        </p>
                    </Card>
                    <Card className="p-4">
                        <p className="text-xs text-neutral-500 mb-1">Net Loss</p>
                        <p className="text-xl font-bold text-warning-600">
                            Rs. {formatCurrency(netLoss)}
                        </p>
                    </Card>
                    <Card className="p-4">
                        <p className="text-xs text-neutral-500 mb-1">Products Lost</p>
                        <p className="text-xl font-bold text-neutral-900">{items.length}</p>
                    </Card>
                </div>

                {/* Record info */}
                <Card className="p-6">
                    <h3 className="font-semibold text-neutral-900 mb-4">Record Information</h3>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div>
                            <p className="text-sm text-neutral-500">Reference</p>
                            <p className="font-medium font-mono">{record.reference_number}</p>
                        </div>
                        <div>
                            <p className="text-sm text-neutral-500">Date Recorded</p>
                            <p className="font-medium">{new Date(record.created_at).toLocaleString()}</p>
                        </div>
                        <div>
                            <p className="text-sm text-neutral-500">Recorded By</p>
                            <p className="font-medium">{record.created_by || 'N/A'}</p>
                        </div>
                        {record.updated_by && record.updated_by !== record.created_by && (
                            <div>
                                <p className="text-sm text-neutral-500">Last Updated By</p>
                                <p className="font-medium">{record.updated_by}</p>
                            </div>
                        )}
                        {record.note && (
                            <div className="col-span-full">
                                <p className="text-sm text-neutral-500">Note</p>
                                <p className="font-medium">{record.note}</p>
                            </div>
                        )}
                    </div>
                </Card>

                {/* Items table */}
                <Card className="p-6">
                    <div className="flex items-center justify-between mb-4">
                        <h3 className="font-semibold text-neutral-900">Lost Items</h3>
                        {!allFound && (
                            <p className="text-xs text-neutral-500">
                                Click &quot;Mark as Found&quot; on any item to restore its stock.
                            </p>
                        )}
                    </div>

                    {items.length === 0 ? (
                        <p className="text-center text-neutral-500 py-6">No items in this record.</p>
                    ) : (
                        <div className="overflow-x-auto">
                            <table className="w-full">
                                <thead>
                                    <tr className="border-b border-neutral-200 bg-neutral-50">
                                        <th className="px-3 py-3 text-left text-xs font-semibold text-neutral-600 uppercase tracking-wide">Product</th>
                                        <th className="px-3 py-3 text-left text-xs font-semibold text-neutral-600 uppercase tracking-wide">Reason</th>
                                        <th className="px-3 py-3 text-right text-xs font-semibold text-neutral-600 uppercase tracking-wide">Lost Qty</th>
                                        <th className="px-3 py-3 text-right text-xs font-semibold text-neutral-600 uppercase tracking-wide">Found Qty</th>
                                        <th className="px-3 py-3 text-right text-xs font-semibold text-neutral-600 uppercase tracking-wide">Still Missing</th>
                                        <th className="px-3 py-3 text-right text-xs font-semibold text-neutral-600 uppercase tracking-wide">Unit Cost</th>
                                        <th className="px-3 py-3 text-right text-xs font-semibold text-neutral-600 uppercase tracking-wide">Total Lost</th>
                                        <th className="px-3 py-3 text-right text-xs font-semibold text-neutral-600 uppercase tracking-wide">Recovered</th>
                                        <th className="px-3 py-3 text-right text-xs font-semibold text-neutral-600 uppercase tracking-wide">Net Loss</th>
                                        <th className="px-3 py-3 text-center text-xs font-semibold text-neutral-600 uppercase tracking-wide">Action</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-neutral-100">
                                    {items.map((item) => {
                                        const stillMissing = item.returnable_quantity ?? (item.quantity - item.found_quantity);
                                        const recovered = parseFloat(item.recovered_amount || 0);
                                        const netAmt = parseFloat(item.net_amount ?? (parseFloat(item.total_cost) - recovered));
                                        const fullyFound = stillMissing === 0;

                                        return (
                                            <tr key={item.id} className="hover:bg-neutral-50 transition-colors">
                                                <td className="px-3 py-3">
                                                    <p className="font-medium text-sm text-neutral-900">{item.product_name}</p>
                                                    <p className="text-xs text-neutral-400">{item.product_code}</p>
                                                </td>
                                                <td className="px-3 py-3 text-sm text-neutral-600">
                                                    {item.reason || <span className="text-neutral-300">—</span>}
                                                </td>
                                                <td className="px-3 py-3 text-sm text-right font-medium text-error-600">
                                                    {item.quantity}
                                                </td>
                                                <td className="px-3 py-3 text-sm text-right font-medium text-success-600">
                                                    {item.found_quantity > 0 ? item.found_quantity : <span className="text-neutral-300">—</span>}
                                                </td>
                                                <td className="px-3 py-3 text-sm text-right">
                                                    {fullyFound ? (
                                                        <Badge variant="success" size="sm">All Found</Badge>
                                                    ) : (
                                                        <span className="font-semibold text-warning-700">{stillMissing}</span>
                                                    )}
                                                </td>
                                                <td className="px-3 py-3 text-sm text-right text-neutral-700">
                                                    Rs. {formatCurrency(item.unit_cost)}
                                                </td>
                                                <td className="px-3 py-3 text-sm text-right font-semibold text-error-600">
                                                    Rs. {formatCurrency(item.total_cost)}
                                                </td>
                                                <td className="px-3 py-3 text-sm text-right font-semibold text-success-600">
                                                    {recovered > 0 ? `Rs. ${formatCurrency(recovered)}` : <span className="text-neutral-300">—</span>}
                                                </td>
                                                <td className="px-3 py-3 text-sm text-right font-semibold text-warning-700">
                                                    Rs. {formatCurrency(netAmt)}
                                                </td>
                                                <td className="px-3 py-3 text-center">
                                                    {!fullyFound ? (
                                                        <Button
                                                            size="sm"
                                                            variant="success"
                                                            onClick={() => setModalItem(item)}
                                                        >
                                                            Mark as Found
                                                        </Button>
                                                    ) : (
                                                        <span className="text-xs text-neutral-400">Recovered</span>
                                                    )}
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                                <tfoot className="border-t-2 border-neutral-200 bg-neutral-50">
                                    <tr>
                                        <td colSpan="6" className="px-3 py-3 text-sm font-bold text-neutral-700 text-right">
                                            Totals
                                        </td>
                                        <td className="px-3 py-3 text-sm font-bold text-error-600 text-right">
                                            Rs. {formatCurrency(record.total_lost_amount)}
                                        </td>
                                        <td className="px-3 py-3 text-sm font-bold text-success-600 text-right">
                                            Rs. {formatCurrency(totalRecovered)}
                                        </td>
                                        <td className="px-3 py-3 text-sm font-bold text-warning-700 text-right">
                                            Rs. {formatCurrency(netLoss)}
                                        </td>
                                        <td />
                                    </tr>
                                </tfoot>
                            </table>
                        </div>
                    )}
                </Card>

                {/* Recovery explanation */}
                <Card className="p-4 bg-blue-50 border border-blue-200">
                    <div className="flex gap-3">
                        <div className="flex-shrink-0 mt-0.5">
                            <svg className="w-5 h-5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                        </div>
                        <div>
                            <p className="text-sm font-semibold text-blue-800">How &quot;Mark as Found&quot; works</p>
                            <p className="text-sm text-blue-700 mt-1">
                                When you mark a lost item as found, the stock is restored to the exact original purchase batch it was taken from (FIFO). The recovered value is tracked separately — the dashboard shows the <em>net</em> lost inventory worth (total lost minus recovered).
                            </p>
                        </div>
                    </div>
                </Card>
            </div>
        </>
    );
};

export default LostInventoryDetailPage;
