import { useState } from 'react';
import PropTypes from 'prop-types';
import { Plus, Trash2, Undo2 } from 'lucide-react';
import Input from '../ui/Input';
import Select from '../ui/Select';
import Button from '../ui/Button';
import InlineAlert from '../ui/InlineAlert';
import EmptyState from '../ui/EmptyState';

const ReturnForm = ({ onSubmit, onCancel, loading, orderItems, initialItems, initialNote, submitLabel }) => {
    const [items, setItems] = useState(initialItems || []);
    const [note, setNote] = useState(initialNote || '');
    const [errors, setErrors] = useState({});
    const [formError, setFormError] = useState('');

    const handleAddItem = () => {
        setItems(prev => [
            ...prev,
            { purchase_item_id: '', quantity: 1 }
        ]);
    };

    const handleUpdateItem = (index, field, value) => {
        setItems(prev => prev.map((item, i) =>
            i === index ? { ...item, [field]: value } : item
        ));
        if (errors[`item_${index}`]) {
            setErrors(prev => ({ ...prev, [`item_${index}`]: '' }));
        }
    };

    const handleRemoveItem = (index) => {
        setItems(prev => prev.filter((_, i) => i !== index));
        const newErrors = { ...errors };
        delete newErrors[`item_${index}`];
        setErrors(newErrors);
    };

    const getReturnableItems = () => {
        return orderItems.filter(item => (item.returnable_quantity || 0) > 0);
    };

    const validate = () => {
        const newErrors = {};
        items.forEach((item, index) => {
            if (!item.purchase_item_id) {
                newErrors[`item_${index}`] = 'Please select an item';
            }
            if (!item.quantity || item.quantity <= 0) {
                newErrors[`item_${index}`] = 'Quantity must be greater than 0';
            }
            const selectedItem = orderItems.find(i => i.id === parseInt(item.purchase_item_id));
            if (selectedItem && item.quantity > selectedItem.returnable_quantity) {
                newErrors[`item_${index}`] = `Max returnable: ${selectedItem.returnable_quantity}`;
            }
        });
        setErrors(newErrors);
        return Object.keys(newErrors).length === 0;
    };

    const handleSubmit = (e) => {
        e.preventDefault();
        setFormError('');
        if (!validate()) return;
        if (items.length === 0) {
            setFormError('Please add at least one item to return.');
            return;
        }
        onSubmit({
            items: items.map(item => ({
                purchase_item_id: parseInt(item.purchase_item_id),
                quantity: parseInt(item.quantity) || 0,
            })),
            note: note,
        });
    };

    const hasReturnableItems = getReturnableItems().length > 0;

    return (
        <form onSubmit={handleSubmit} className="space-y-5">
            {!hasReturnableItems ? (
                <EmptyState
                    title="Nothing left to return"
                    description="All items on this order have already been fully returned."
                />
            ) : (
                <>
                    <div>
                        <div className="flex items-center justify-between mb-3">
                            <h4 className="font-semibold text-neutral-900">Items to Return</h4>
                            <Button size="sm" variant="secondary" icon={Plus} onClick={handleAddItem}>
                                Add Item
                            </Button>
                        </div>

                        {items.length === 0 ? (
                            <div className="text-center py-8 bg-neutral-50 rounded-xl border border-dashed border-neutral-300">
                                <p className="text-neutral-500 text-sm">Click "Add Item" to start adding items to return</p>
                            </div>
                        ) : (
                            <div className="space-y-3 max-h-72 overflow-y-auto pr-1">
                                {items.map((item, index) => {
                                    const selectedItem = orderItems.find(i => i.id === parseInt(item.purchase_item_id));
                                    const returnableQty = selectedItem?.returnable_quantity || 0;

                                    return (
                                        <div key={index} className="grid grid-cols-1 md:grid-cols-[2fr_1fr_auto] gap-3 p-4 bg-neutral-50 rounded-xl border border-neutral-200">
                                            <Select
                                                label="Product"
                                                value={item.purchase_item_id}
                                                onChange={(e) => handleUpdateItem(index, 'purchase_item_id', e.target.value)}
                                                options={[
                                                    { value: '', label: 'Select item' },
                                                    ...getReturnableItems().map(i => ({
                                                        value: i.id,
                                                        label: `${i.product_name} (Returnable: ${i.returnable_quantity})`,
                                                    })),
                                                ]}
                                                required
                                            />
                                            <div>
                                                <Input
                                                    label="Quantity"
                                                    type="number"
                                                    min="1"
                                                    max={returnableQty || undefined}
                                                    value={item.quantity || ''}
                                                    onChange={(e) => handleUpdateItem(index, 'quantity', e.target.value ? parseInt(e.target.value) : '')}
                                                    required
                                                />
                                                {returnableQty > 0 && (
                                                    <p className="text-xs text-neutral-500 mt-1">Max: {returnableQty}</p>
                                                )}
                                            </div>
                                            <div className="flex items-end">
                                                <Button
                                                    size="sm"
                                                    variant="danger"
                                                    icon={Trash2}
                                                    onClick={() => handleRemoveItem(index)}
                                                    className="w-full md:w-11 md:px-0"
                                                    aria-label="Remove item"
                                                >
                                                    <span className="md:hidden">Remove</span>
                                                </Button>
                                            </div>
                                            {errors[`item_${index}`] && (
                                                <p className="md:col-span-3 text-sm text-error-600 -mt-1">{errors[`item_${index}`]}</p>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </div>

                    <Input
                        label="Note (Optional)"
                        value={note}
                        onChange={(e) => setNote(e.target.value)}
                        placeholder="Reason for return..."
                    />

                    {formError && <InlineAlert variant="error" message={formError} />}

                    <div className="flex justify-end gap-3 pt-4 border-t border-neutral-200">
                        <Button type="button" variant="secondary" onClick={onCancel}>
                            Cancel
                        </Button>
                        <Button type="submit" loading={loading} disabled={items.length === 0} icon={Undo2}>
                            {submitLabel || 'Create Return'}
                        </Button>
                    </div>
                </>
            )}
        </form>
    );
};

ReturnForm.propTypes = {
    onSubmit: PropTypes.func.isRequired,
    onCancel: PropTypes.func.isRequired,
    loading: PropTypes.bool,
    orderItems: PropTypes.array,
    initialItems: PropTypes.array,
    initialNote: PropTypes.string,
    submitLabel: PropTypes.string,
};

export default ReturnForm;
