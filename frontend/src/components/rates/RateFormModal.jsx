import { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import Modal from '../ui/Modal';
import Input from '../ui/Input';
import Button from '../ui/Button';
import InlineAlert from '../ui/InlineAlert';
import { extractErrorMessage } from '../../utils/errorMessage';

const FIELD_KEYS = ['selling_price', 'note', 'product_id'];

const RateFormModal = ({
    isOpen,
    onClose,
    onSubmit,
    product,
    existingRate,
    loading = false,
}) => {
    const [formData, setFormData] = useState({
        selling_price: '',
        note: '',
    });
    const [errors, setErrors] = useState({});
    const [apiError, setApiError] = useState('');

    useEffect(() => {
        if (isOpen) {
            if (existingRate) {
                setFormData({
                    selling_price: existingRate.selling_price || '',
                    note: '',
                });
            } else {
                setFormData({
                    selling_price: '',
                    note: '',
                });
            }
            setErrors({});
            setApiError('');
        }
    }, [isOpen, existingRate]);

    const handleChange = (e) => {
        const { name, value } = e.target;
        setFormData(prev => ({ ...prev, [name]: value }));
        if (errors[name]) {
            setErrors(prev => ({ ...prev, [name]: '' }));
        }
        if (apiError) setApiError('');
    };

    const validate = () => {
        const newErrors = {};
        if (!formData.selling_price || parseFloat(formData.selling_price) <= 0) {
            newErrors.selling_price = 'Selling price must be greater than 0';
        }
        setErrors(newErrors);
        return Object.keys(newErrors).length === 0;
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setApiError('');
        if (!validate()) return;

        const data = {
            selling_price: parseFloat(formData.selling_price),
            note: formData.note || '',
        };

        if (!existingRate) {
            data.product_id = product.id;
        }

        try {
            await onSubmit(data);
        } catch (error) {
            const responseData = error?.response?.data;
            if (responseData && typeof responseData === 'object' && !Array.isArray(responseData)) {
                const fieldErrors = {};
                let genericMessage = '';
                Object.keys(responseData).forEach((key) => {
                    const val = Array.isArray(responseData[key]) ? responseData[key][0] : responseData[key];
                    if (FIELD_KEYS.includes(key)) {
                        fieldErrors[key] = val;
                    } else {
                        genericMessage = val || genericMessage;
                    }
                });
                if (Object.keys(fieldErrors).length) setErrors(prev => ({ ...prev, ...fieldErrors }));
                if (genericMessage) setApiError(genericMessage);
            } else {
                setApiError(extractErrorMessage(error, 'Failed to save rate'));
            }
        }
    };

    const isEdit = !!existingRate;

    return (
        <Modal
            isOpen={isOpen}
            onClose={onClose}
            title={isEdit ? 'Edit Price' : 'Set Price'}
            size="md"
        >
            <form onSubmit={handleSubmit} className="space-y-4">
                <div className="p-4 bg-neutral-50 rounded-lg">
                    <p className="text-sm text-neutral-500">Product</p>
                    <p className="font-medium text-neutral-900">{product?.name}</p>
                    <p className="text-sm text-neutral-500">Code: {product?.code}</p>
                </div>

                {isEdit && (
                    <div className="p-3 bg-blue-50 rounded-lg">
                        <p className="text-sm text-neutral-500">Current Price</p>
                        <p className="font-medium text-primary-600">
                            Rs. {parseFloat(existingRate.selling_price).toFixed(2)}
                        </p>
                    </div>
                )}

                <Input
                    label="New Selling Price"
                    type="number"
                    step="0.01"
                    min="0.01"
                    name="selling_price"
                    value={formData.selling_price}
                    onChange={handleChange}
                    placeholder="Enter selling price"
                    error={errors.selling_price}
                    required
                />

                <Input
                    label="Note (Optional)"
                    name="note"
                    value={formData.note}
                    onChange={handleChange}
                    placeholder={isEdit ? "Reason for price change..." : "Reason for setting this price..."}
                />

                {apiError && <InlineAlert variant="error" message={apiError} />}

                <div className="flex justify-end gap-3 pt-4 border-t border-neutral-200">
                    <Button
                        type="button"
                        variant="secondary"
                        onClick={onClose}
                    >
                        Cancel
                    </Button>
                    <Button type="submit" loading={loading}>
                        {isEdit ? 'Update Price' : 'Set Price'}
                    </Button>
                </div>
            </form>
        </Modal>
    );
};

RateFormModal.propTypes = {
    isOpen: PropTypes.bool.isRequired,
    onClose: PropTypes.func.isRequired,
    onSubmit: PropTypes.func.isRequired,
    product: PropTypes.object,
    existingRate: PropTypes.object,
    loading: PropTypes.bool,
};

export default RateFormModal;