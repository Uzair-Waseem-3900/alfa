import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { PackagePlus, ClipboardList, Plus, Trash2 } from 'lucide-react';
import { dataEntryApi } from '../../services/dataEntryApi';
import { purchasesApi } from '../../services/purchasesApi';
import { extractErrorMessage } from '../../utils/errorMessage';
import { useToast } from '../../context/ToastContext';
import Card from '../ui/Card';
import Input from '../ui/Input';
import Button from '../ui/Button';
import SearchableSelect from '../ui/SearchableSelect';
import LoadingSpinner from '../ui/LoadingSpinner';
import InlineAlert from '../ui/InlineAlert';
import EmptyState from '../ui/EmptyState';

const fmt = (v) => Number(v || 0).toFixed(2);
const emptyRow = () => ({ product_id: '', product_label: '', shelf_id: '', shelf_label: '', quantity: '', unit_price: '', gst: '0', wht: '0', description: '' });

const OpeningStockPanel = () => {
    const { toast } = useToast();
    const [records, setRecords] = useState([]);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState('');
    const [saving, setSaving] = useState(false);
    const [rows, setRows] = useState([emptyRow()]);
    const [bannerError, setBannerError] = useState('');

    const loadRecords = useCallback(async () => {
        try {
            const res = await dataEntryApi.openingStock.getAll({ page_size: 500 });
            setRecords(res?.results ?? res ?? []);
            setLoadError('');
        } catch (err) {
            setLoadError(extractErrorMessage(err, 'Failed to load opening stock entries.'));
        }
    }, []);

    useEffect(() => {
        (async () => {
            setLoading(true);
            try {
                await loadRecords();
            } finally {
                setLoading(false);
            }
        })();
    }, [loadRecords]);

    const searchProducts = useCallback(async (query) => {
        const res = await purchasesApi.products.getAll({ search: query, page_size: 25 });
        const results = res?.results ?? res ?? [];
        return results.map(p => ({ value: p.id, label: `${p.name} (${p.code})` }));
    }, []);

    const searchShelves = useCallback(async (query) => {
        const res = await purchasesApi.shelves.getAll({ search: query, page_size: 25 });
        const results = res?.results ?? res ?? [];
        return results.map(s => ({ value: s.id, label: s.name }));
    }, []);

    const updateRow = (i, key, val) => setRows(rs => rs.map((r, idx) => idx === i ? { ...r, [key]: val } : r));
    const addRow = () => setRows(rs => [...rs, emptyRow()]);
    const removeRow = (i) => setRows(rs => rs.length > 1 ? rs.filter((_, idx) => idx !== i) : rs);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setBannerError('');

        const seen = new Set();
        const items = [];
        for (const r of rows) {
            if (!r.product_id) return setBannerError('Every row needs a product.');
            if (seen.has(r.product_id)) return setBannerError('A product is listed more than once.');
            seen.add(r.product_id);
            if (!r.shelf_id) return setBannerError('Every row needs a shelf.');
            if (!r.quantity || parseInt(r.quantity) <= 0) return setBannerError('Quantity must be greater than 0.');
            if (!r.unit_price || parseFloat(r.unit_price) <= 0) return setBannerError('Unit price must be greater than 0.');
            items.push({
                product_id: parseInt(r.product_id),
                shelf_id: parseInt(r.shelf_id),
                quantity: parseInt(r.quantity),
                unit_price: r.unit_price,
                gst: r.gst || 0,
                wht: r.wht || 0,
                description: r.description || '',
            });
        }

        setSaving(true);
        try {
            await dataEntryApi.openingStock.create({ items });
            toast.success('Opening stock added to inventory.');
            setRows([emptyRow()]);
            await loadRecords();
        } catch (err) {
            setBannerError(extractErrorMessage(err, 'Failed to add opening stock.'));
        } finally {
            setSaving(false);
        }
    };

    if (loading) {
        return <div className="flex justify-center py-16"><LoadingSpinner size="lg" /></div>;
    }

    return (
        <div className="space-y-6">
            <Card hover={false}>
                <div className="flex items-center gap-3 mb-5">
                    <div className="w-10 h-10 rounded-xl bg-primary-50 flex items-center justify-center flex-shrink-0">
                        <PackagePlus className="w-5 h-5 text-primary-600" />
                    </div>
                    <h3 className="font-semibold text-neutral-900">Add Opening Stock</h3>
                </div>
                <form onSubmit={handleSubmit} className="space-y-4">
                    {rows.map((row, i) => (
                        <motion.div
                            key={i}
                            initial={{ opacity: 0, y: 6 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="space-y-3 border border-neutral-100 rounded-xl p-4 bg-neutral-50/50"
                        >
                            {/* Row 1: Product, Shelf, Qty, Unit Price */}
                            <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
                                <div className="md:col-span-3">
                                    <SearchableSelect
                                        label="Product"
                                        value={row.product_id}
                                        selectedLabel={row.product_label}
                                        onChange={(v, option) => {
                                            updateRow(i, 'product_id', v);
                                            updateRow(i, 'product_label', option?.label ?? '');
                                        }}
                                        onSearch={searchProducts}
                                        placeholder="Search product..."
                                    />
                                </div>
                                <div className="md:col-span-3">
                                    <SearchableSelect
                                        label="Shelf"
                                        value={row.shelf_id}
                                        selectedLabel={row.shelf_label}
                                        onChange={(v, option) => {
                                            updateRow(i, 'shelf_id', v);
                                            updateRow(i, 'shelf_label', option?.label ?? '');
                                        }}
                                        onSearch={searchShelves}
                                        placeholder="Search shelf..."
                                    />
                                </div>
                                <div className="md:col-span-3">
                                    <Input label="Qty" type="number" min="1"
                                        value={row.quantity} onChange={(e) => updateRow(i, 'quantity', e.target.value)} placeholder="Qty" />
                                </div>
                                <div className="md:col-span-3">
                                    <Input label="Unit Price" type="number" step="0.01" min="0.01"
                                        value={row.unit_price} onChange={(e) => updateRow(i, 'unit_price', e.target.value)} placeholder="Price" />
                                </div>
                            </div>
                            {/* Row 2: GST, WHT, Remove */}
                            <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
                                <div className="md:col-span-2">
                                    <Input label="GST%" type="number" step="0.01" min="0"
                                        value={row.gst} onChange={(e) => updateRow(i, 'gst', e.target.value)} />
                                </div>
                                <div className="md:col-span-2">
                                    <Input label="WHT%" type="number" step="0.01" min="0"
                                        value={row.wht} onChange={(e) => updateRow(i, 'wht', e.target.value)} />
                                </div>
                                <div className="md:col-span-6" />
                                <div className="md:col-span-2">
                                    <Button type="button" variant="secondary" size="sm" className="w-full"
                                        icon={Trash2}
                                        onClick={() => removeRow(i)} disabled={rows.length === 1}>
                                        Remove
                                    </Button>
                                </div>
                            </div>
                        </motion.div>
                    ))}

                    <div className="flex items-center gap-3">
                        <Button type="button" variant="outline" size="sm" icon={Plus} onClick={addRow}>
                            Add Product
                        </Button>
                    </div>

                    <InlineAlert
                        variant="info"
                        message="Adds quantities to inventory (FIFO-ready). No cash or supplier-payable effect."
                    />
                    {bannerError && <InlineAlert variant="error" message={bannerError} />}
                    <Button type="submit" loading={saving} icon={PackagePlus} className="w-full sm:w-auto">
                        Add Opening Stock
                    </Button>
                </form>
            </Card>

            <Card hover={false}>
                <div className="flex items-center gap-3 mb-5">
                    <div className="w-10 h-10 rounded-xl bg-neutral-100 flex items-center justify-center flex-shrink-0">
                        <ClipboardList className="w-5 h-5 text-neutral-500" />
                    </div>
                    <h3 className="font-semibold text-neutral-900">Recorded Stock Entries ({records.length})</h3>
                </div>
                {loadError && <InlineAlert variant="error" message={loadError} onRetry={loadRecords} className="mb-4" />}
                {records.length === 0 ? (
                    <EmptyState
                        title="No opening stock entries yet"
                        description="Stock batches you add will appear here for audit."
                    />
                ) : (
                    <div className="space-y-4">
                        {records.map(order => (
                            <div key={order.id} className="border border-neutral-200 rounded-xl p-4">
                                <div className="flex items-center justify-between mb-2 flex-wrap gap-1">
                                    <span className="font-medium text-neutral-900">{order.order_number}</span>
                                    <span className="text-xs text-neutral-500">{new Date(order.created_at).toLocaleString()}</span>
                                </div>
                                <div className="overflow-x-auto">
                                    <table className="w-full text-sm">
                                        <thead>
                                            <tr className="text-left text-xs text-neutral-500 border-b border-neutral-100">
                                                <th className="py-1 pr-3">Product</th>
                                                <th className="py-1 pr-3 text-right">Qty</th>
                                                <th className="py-1 pr-3 text-right">Unit Price</th>
                                                <th className="py-1 text-right">Total</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-neutral-50">
                                            {(order.items || []).map((it, idx) => (
                                                <tr key={idx}>
                                                    <td className="py-1 pr-3">{it.product_name}</td>
                                                    <td className="py-1 pr-3 text-right">{it.quantity}</td>
                                                    <td className="py-1 pr-3 text-right">{fmt(it.unit_price)}</td>
                                                    <td className="py-1 text-right">{fmt(it.total_price)}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </Card>
        </div>
    );
};

export default OpeningStockPanel;
