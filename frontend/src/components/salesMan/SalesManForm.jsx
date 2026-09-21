import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import PropTypes from 'prop-types';
import { User, Hash, MapPin, Phone } from 'lucide-react';
import Input from '../ui/Input';
import Button from '../ui/Button';
import { useToast } from '../../context/ToastContext';
import { extractErrorMessage } from '../../utils/errorMessage';

// Fields the backend can attach a validation error to (see
// sales_man/serializers.py SalesManWriteSerializer and
// sales_man/services.py create_sales_man/update_sales_man).
const KNOWN_FIELDS = ['name', 'code', 'address', 'phone'];

const SalesManForm = ({ initialData, onSubmit, onCancel, loading }) => {
    const { toast } = useToast();
    const [formData, setFormData] = useState({ name: '', code: '', address: '', phone: '' });
    const [errors, setErrors] = useState({});

    useEffect(() => {
        if (initialData) {
            setFormData({
                name: initialData.name || '',
                code: initialData.code || '',
                address: initialData.address || '',
                phone: initialData.phone || '',
            });
        } else {
            setFormData({ name: '', code: '', address: '', phone: '' });
        }
        setErrors({});
    }, [initialData]);

    const handleChange = (e) => {
        const { name, value } = e.target;
        setFormData(prev => ({ ...prev, [name]: value }));
        if (errors[name]) {
            setErrors(prev => ({ ...prev, [name]: '' }));
        }
    };

    const validate = () => {
        const newErrors = {};
        if (!formData.name.trim()) newErrors.name = 'Name is required';
        if (!formData.code.trim()) newErrors.code = 'Code is required';
        setErrors(newErrors);
        return Object.keys(newErrors).length === 0;
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!validate()) return;

        try {
            await onSubmit(formData);
        } catch (error) {
            const data = error?.response?.data;
            const fieldErrors = {};
            if (data && typeof data === 'object') {
                KNOWN_FIELDS.forEach((field) => {
                    if (data[field]) {
                        fieldErrors[field] = Array.isArray(data[field]) ? data[field][0] : data[field];
                    }
                });
            }
            if (Object.keys(fieldErrors).length > 0) {
                setErrors(fieldErrors);
            } else {
                toast.error(extractErrorMessage(error, 'Failed to save sales man.'));
            }
        }
    };

    return (
        <motion.form
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            onSubmit={handleSubmit}
            className="space-y-4"
            noValidate
        >
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Input
                    label="Name"
                    name="name"
                    icon={User}
                    value={formData.name}
                    onChange={handleChange}
                    placeholder="Enter sales man name"
                    error={errors.name}
                    required
                />
                <Input
                    label="Code"
                    name="code"
                    icon={Hash}
                    value={formData.code}
                    onChange={handleChange}
                    placeholder="Enter unique employee code"
                    error={errors.code}
                    required
                />
            </div>
            <Input
                label="Address"
                name="address"
                icon={MapPin}
                value={formData.address}
                onChange={handleChange}
                placeholder="Enter address (optional)"
                error={errors.address}
            />
            <Input
                label="Phone"
                name="phone"
                icon={Phone}
                value={formData.phone}
                onChange={handleChange}
                placeholder="Enter phone number (optional)"
                error={errors.phone}
            />
            <div className="flex justify-end gap-3 pt-4">
                <Button type="button" variant="secondary" onClick={onCancel} disabled={loading} className="min-w-[100px]">
                    Cancel
                </Button>
                <Button type="submit" loading={loading} className="min-w-[160px]">
                    {initialData ? 'Update Sales Man' : 'Create Sales Man'}
                </Button>
            </div>
        </motion.form>
    );
};

SalesManForm.propTypes = {
    initialData: PropTypes.object,
    onSubmit: PropTypes.func.isRequired,
    onCancel: PropTypes.func.isRequired,
    loading: PropTypes.bool,
};

export default SalesManForm;
