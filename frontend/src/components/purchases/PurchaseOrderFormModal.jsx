import { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import Modal from '../ui/Modal';
import Input from '../ui/Input';
import Select from '../ui/Select';
import SearchableSelect from '../ui/SearchableSelect';
import Button from '../ui/Button';
import LineItemRow from './LineItemRow';
import DraftPreview from './DraftPreview';
import MethodSplitPicker, { isSplitBalanced } from '../paymentMethods/MethodSplitPicker';

const emptyFormData = {
    supplier: '',
    supplier_label: '',
    payment_type: 'after_delivery',
    advance_amount: '',
    description: '',
    items: [],
};

// Shared by PurchaseOrdersPage (create) and PurchaseOrderDetailPage (edit,
// draft orders only) — the backend's update endpoint doesn't accept a
// supplier change (PurchaseOrderUpdateSerializer has no supplier field),
// so the supplier selector is read-only whenever initialData is provided.
const PurchaseOrderFormModal = ({
    isOpen, onClose, onSubmit, onSearchProducts, onSearchSuppliers,
    initialData, title, submitLabel,
}) => {
    const isEdit = Boolean(initialData);
    const [formData, setFormData] = useState(initialData || emptyFormData);
    const [methodAllocations, setMethodAllocations] = useState([]);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (isOpen) {
            setFormData(initialData || emptyFormData);
            setMethodAllocations([]);
            setError('');
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isOpen]);

    const isAdvance = formData.payment_type === 'advance';
    const advanceAmountValue = parseFloat(formData.advance_amount) || 0;
    // On edit, the backend never silently reuses the old split — a fresh
    // method pick is only required when the advance amount is actually
    // being set to a new value (including switching to advance for the
    // first time). On create there's no "original" to compare against, so
    // any advance always needs a pick.
    const advanceChanged = isAdvance && (
        !isEdit ||
        initialData?.payment_type !== 'advance' ||
        String(formData.advance_amount) !== String(initialData?.advance_amount)
    );

    const handleAddItem = () => {
        setFormData(prev => ({
            ...prev,
            items: [...prev.items, { product: '', quantity: 1, unit_price: 0, gst: 0, wht: 0, description: '' }],
        }));
    };

    const handleUpdateItem = (index, field, value) => {
        setFormData(prev => ({
            ...prev,
            items: prev.items.map((item, i) => i === index ? { ...item, [field]: value } : item),
        }));
    };

    const handleRemoveItem = (index) => {
        setFormData(prev => ({ ...prev, items: prev.items.filter((_, i) => i !== index) }));
    };

    const calculatePreview = () => {
        const items = formData.items.map(item => {
            const gross = (item.quantity || 0) * (item.unit_price || 0);
            const gstAmount = gross * ((item.gst || 0) / 100);
            const whtAmount = gross * ((item.wht || 0) / 100);
            const total = gross + gstAmount - whtAmount;

            return {
                product_name: item.product_label || 'Unknown',
                quantity: item.quantity || 0,
                line_total: total,
                rate_missing: false,
                stock_insufficient: false,
            };
        });

        const subtotal = items.reduce((sum, item) => sum + (item.line_total || 0), 0);
        return {
            items,
            totals: {
                subtotal: subtotal.toFixed(2),
                total_cogs: '0.00',
                gross_profit: '0.00',
            },
            warnings: { missing_rate: false, missing_stock: false },
        };
    };

    const handleFormSubmit = async (e) => {
        e.preventDefault();
        setError('');

        if (!isEdit && !formData.supplier) {
            setError('Please select a supplier.');
            return;
        }
        if (formData.items.length === 0) {
            setError('Please add at least one item to the order.');
            return;
        }
        if (formData.items.some(item => !item.product)) {
            setError('Please select a product for all items.');
            return;
        }
        if (formData.items.some(item => !item.quantity || item.quantity <= 0)) {
            setError('Please enter a valid quantity for all items.');
            return;
        }
        if (formData.items.some(item => !item.unit_price || item.unit_price <= 0)) {
            setError('Please enter a valid unit price for all items.');
            return;
        }
        if (advanceChanged && !isSplitBalanced(advanceAmountValue, methodAllocations)) {
            setError('Payment method split must add up to the full advance amount.');
            return;
        }

        const payload = {
            ...(isEdit ? {} : { supplier_id: parseInt(formData.supplier) }),
            payment_type: formData.payment_type,
            advance_amount: isAdvance ? advanceAmountValue : 0,
            ...(advanceChanged ? { method_allocations: methodAllocations } : {}),
            description: formData.description || '',
            items: formData.items.map(item => ({
                product_id: parseInt(item.product),
                quantity: parseInt(item.quantity) || 0,
                unit_price: parseFloat(item.unit_price) || 0,
                gst: parseFloat(item.gst) || 0,
                wht: parseFloat(item.wht) || 0,
                description: item.description || '',
            })),
        };

        setLoading(true);
        try {
            await onSubmit(payload);
        } catch (err) {
            console.error('Failed to submit order:', err);
            if (err.response?.data) {
                const errorData = err.response.data;
                if (typeof errorData === 'object') {
                    const errorMessages = Object.entries(errorData)
                        .map(([key, value]) => key === 'items'
                            ? `${key}: ${JSON.stringify(value)}`
                            : `${key}: ${Array.isArray(value) ? value.join(', ') : value}`)
                        .join('\n');
                    setError(`Validation Error:\n${errorMessages}`);
                } else {
                    setError(errorData || 'Failed to save order. Please check your input.');
                }
            } else {
                setError(err.message || 'Failed to save order. Please try again.');
            }
        } finally {
            setLoading(false);
        }
    };

    return (
        <Modal isOpen={isOpen} onClose={onClose} title={title} size="xl">
            <form onSubmit={handleFormSubmit} className="space-y-6">
                <div className="space-y-4">
                    <SearchableSelect
                        label="Supplier"
                        value={formData.supplier}
                        selectedLabel={formData.supplier_label}
                        onChange={(value, option) => setFormData({
                            ...formData,
                            supplier: value,
                            supplier_label: option?.label ?? '',
                        })}
                        onSearch={onSearchSuppliers}
                        placeholder="Search supplier by name or code"
                        disabled={isEdit}
                        required={!isEdit}
                    />
                    {isEdit && (
                        <p className="text-xs text-neutral-400 -mt-3">Supplier can't be changed after a draft is created.</p>
                    )}

                    <div className="grid grid-cols-2 gap-4">
                        <Select
                            label="Payment Type"
                            value={formData.payment_type}
                            onChange={(e) => setFormData({ ...formData, payment_type: e.target.value })}
                            options={[
                                { value: 'advance', label: 'Advance' },
                                { value: 'after_delivery', label: 'After Delivery' },
                            ]}
                            required
                        />

                        {formData.payment_type === 'advance' && (
                            <Input
                                label="Advance Amount (PKR)"
                                type="number"
                                step="0.01"
                                min="0"
                                value={formData.advance_amount}
                                onChange={(e) => setFormData({ ...formData, advance_amount: e.target.value })}
                                placeholder="Enter advance amount"
                                required
                            />
                        )}
                    </div>

                    {isAdvance && (
                        <div>
                            {advanceChanged ? (
                                <>
                                    <p className="text-sm font-medium text-neutral-700 mb-2">Advance Payment Method</p>
                                    {isEdit && (
                                        <p className="text-xs text-neutral-500 mb-2">
                                            The advance amount changed — pick how the new amount was paid.
                                        </p>
                                    )}
                                    <MethodSplitPicker
                                        totalAmount={advanceAmountValue}
                                        value={methodAllocations}
                                        onChange={setMethodAllocations}
                                    />
                                </>
                            ) : (
                                <p className="text-xs text-neutral-500">
                                    Advance amount unchanged — keeping the existing payment method split.
                                </p>
                            )}
                        </div>
                    )}

                    <Input
                        label="Description"
                        value={formData.description}
                        onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                        placeholder="Order description (optional)"
                    />
                </div>

                <div>
                    <div className="flex items-center justify-between mb-4">
                        <h3 className="font-semibold text-neutral-900">Line Items</h3>
                        <Button size="sm" onClick={handleAddItem} type="button">
                            Add Item
                        </Button>
                    </div>

                    <div className="space-y-3 max-h-[500px] overflow-y-auto">
                        {formData.items.length === 0 ? (
                            <p className="text-center text-neutral-500 py-8">No items added yet. Click "Add Item" to start.</p>
                        ) : (
                            formData.items.map((item, index) => (
                                <LineItemRow
                                    key={index}
                                    index={index}
                                    item={item}
                                    onSearchProducts={onSearchProducts}
                                    onUpdate={handleUpdateItem}
                                    onRemove={handleRemoveItem}
                                    canEdit={true}
                                />
                            ))
                        )}
                    </div>
                </div>

                {error && (
                    <div className="p-4 bg-error-50 border border-error-200 rounded-lg">
                        <p className="text-sm text-error-600 whitespace-pre-wrap">{error}</p>
                    </div>
                )}

                {formData.items.length > 0 && (
                    <DraftPreview {...calculatePreview()} />
                )}

                <div className="flex justify-end gap-3 pt-4 border-t border-neutral-200">
                    <Button type="button" variant="secondary" onClick={onClose}>
                        Cancel
                    </Button>
                    <Button
                        type="submit"
                        loading={loading}
                        disabled={advanceChanged && !isSplitBalanced(advanceAmountValue, methodAllocations)}
                    >
                        {submitLabel}
                    </Button>
                </div>
            </form>
        </Modal>
    );
};

PurchaseOrderFormModal.propTypes = {
    isOpen: PropTypes.bool.isRequired,
    onClose: PropTypes.func.isRequired,
    onSubmit: PropTypes.func.isRequired,
    onSearchProducts: PropTypes.func.isRequired,
    onSearchSuppliers: PropTypes.func.isRequired,
    initialData: PropTypes.object,
    title: PropTypes.string.isRequired,
    submitLabel: PropTypes.string.isRequired,
};

export default PurchaseOrderFormModal;
