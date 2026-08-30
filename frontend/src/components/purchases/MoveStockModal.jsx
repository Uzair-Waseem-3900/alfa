import { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { purchasesApi } from '../../services/purchasesApi';
import Modal from '../ui/Modal';
import Input from '../ui/Input';
import SearchableSelect from '../ui/SearchableSelect';
import Button from '../ui/Button';

const emptyFormData = {
    product: '',
    product_label: '',
    quantity: '',
    to_shelf: '',
    to_shelf_label: '',
};

// Opened from a shelf's detail page — the current shelf is implicitly the
// "from" shelf, so it's excluded from the destination-shelf search results.
const MoveStockModal = ({ isOpen, onClose, fromShelfId, onSuccess }) => {
    const [formData, setFormData] = useState(emptyFormData);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (isOpen) {
            setFormData(emptyFormData);
            setError('');
        }
    }, [isOpen]);

    const handleSearchProducts = async (query) => {
        const res = await purchasesApi.products.getAll({ search: query, page_size: 25 });
        const results = res.results || res;
        return results.map((p) => ({ value: p.id, label: `${p.name} (${p.code})` }));
    };

    const handleSearchShelves = async (query) => {
        const res = await purchasesApi.shelves.getAll({ search: query, page_size: 25 });
        const results = res.results || res;
        return results
            .filter((s) => String(s.id) !== String(fromShelfId))
            .map((s) => ({ value: s.id, label: s.name }));
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');

        if (!formData.product) {
            setError('Please select a product.');
            return;
        }
        if (!formData.to_shelf) {
            setError('Please select a destination shelf.');
            return;
        }
        const qty = parseInt(formData.quantity, 10);
        if (!qty || qty <= 0) {
            setError('Please enter a valid quantity greater than zero.');
            return;
        }

        setLoading(true);
        try {
            await purchasesApi.shelves.moveStock({
                from_shelf_id: parseInt(fromShelfId, 10),
                to_shelf_id: parseInt(formData.to_shelf, 10),
                product_id: parseInt(formData.product, 10),
                quantity: qty,
            });
            onSuccess();
        } catch (err) {
            console.error('Failed to move stock:', err);
            const data = err.response?.data;
            if (data && typeof data === 'object') {
                const messages = Object.entries(data)
                    .map(([key, value]) => `${key === 'detail' ? '' : `${key}: `}${Array.isArray(value) ? value.join(', ') : value}`)
                    .join('\n');
                setError(messages);
            } else if (typeof data === 'string') {
                setError(data);
            } else {
                setError(err.message || 'Failed to move stock. Please try again.');
            }
        } finally {
            setLoading(false);
        }
    };

    return (
        <Modal isOpen={isOpen} onClose={onClose} title="Move Stock">
            <form onSubmit={handleSubmit} className="space-y-4">
                <SearchableSelect
                    label="Product"
                    value={formData.product}
                    selectedLabel={formData.product_label}
                    onChange={(value, option) => setFormData({
                        ...formData,
                        product: value,
                        product_label: option?.label ?? '',
                    })}
                    onSearch={handleSearchProducts}
                    placeholder="Search product by name or code"
                    required
                />

                <Input
                    label="Quantity"
                    type="number"
                    min="1"
                    value={formData.quantity}
                    onChange={(e) => setFormData({ ...formData, quantity: e.target.value })}
                    placeholder="Enter quantity to move"
                    required
                />

                <SearchableSelect
                    label="Destination Shelf"
                    value={formData.to_shelf}
                    selectedLabel={formData.to_shelf_label}
                    onChange={(value, option) => setFormData({
                        ...formData,
                        to_shelf: value,
                        to_shelf_label: option?.label ?? '',
                    })}
                    onSearch={handleSearchShelves}
                    placeholder="Search destination shelf by name"
                    required
                />

                {error && (
                    <div className="p-4 bg-error-50 border border-error-200 rounded-lg">
                        <p className="text-sm text-error-600 whitespace-pre-wrap">{error}</p>
                    </div>
                )}

                <div className="flex justify-end gap-3 pt-4 border-t border-neutral-200">
                    <Button type="button" variant="secondary" onClick={onClose}>
                        Cancel
                    </Button>
                    <Button type="submit" loading={loading}>
                        Move Stock
                    </Button>
                </div>
            </form>
        </Modal>
    );
};

MoveStockModal.propTypes = {
    isOpen: PropTypes.bool.isRequired,
    onClose: PropTypes.func.isRequired,
    fromShelfId: PropTypes.oneOfType([PropTypes.string, PropTypes.number]).isRequired,
    onSuccess: PropTypes.func.isRequired,
};

export default MoveStockModal;
