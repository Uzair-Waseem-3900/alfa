import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import Input from '../common/Input';
import Button from '../common/Button';
import InlineAlert from '../ui/InlineAlert';
import { extractErrorMessage } from '../../utils/errorMessage';

const FIELD_KEYS = ['email', 'first_name', 'last_name', 'password', 'role'];

const UserForm = ({ initialData, onSubmit, onCancel, loading }) => {
    const [formData, setFormData] = useState({
        email: '',
        first_name: '',
        last_name: '',
        password: '',
        role: 'user',
    });

    const [errors, setErrors] = useState({});
    const [apiError, setApiError] = useState('');

    useEffect(() => {
        if (initialData) {
            setFormData({
                email: initialData.email || '',
                first_name: initialData.first_name || '',
                last_name: initialData.last_name || '',
                password: '',
                role: initialData.role || 'user',
            });
        }
    }, [initialData]);

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
        if (!formData.first_name) newErrors.first_name = 'First name is required';
        if (!formData.last_name) newErrors.last_name = 'Last name is required';
        if (!initialData && !formData.email) newErrors.email = 'Email is required';
        if (!initialData && !formData.password) newErrors.password = 'Password is required';
        if (!initialData && formData.password && formData.password.length < 8) {
            newErrors.password = 'Password must be at least 8 characters';
        }
        setErrors(newErrors);
        return Object.keys(newErrors).length === 0;
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setApiError('');
        if (!validate()) return;

        const submitData = { ...formData };
        if (initialData) {
            delete submitData.password;
            delete submitData.email;
        }

        try {
            await onSubmit(submitData);
        } catch (error) {
            const data = error?.response?.data;
            if (data && typeof data === 'object' && !Array.isArray(data)) {
                const fieldErrors = {};
                let genericMessage = '';
                Object.keys(data).forEach((key) => {
                    const val = Array.isArray(data[key]) ? data[key][0] : data[key];
                    if (FIELD_KEYS.includes(key)) {
                        fieldErrors[key] = val;
                    } else {
                        genericMessage = val || genericMessage;
                    }
                });
                if (Object.keys(fieldErrors).length) setErrors(prev => ({ ...prev, ...fieldErrors }));
                if (genericMessage) setApiError(genericMessage);
            } else {
                setApiError(extractErrorMessage(error, 'Failed to save user'));
            }
        }
    };

    return (
        <motion.form
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            onSubmit={handleSubmit}
            className="space-y-4"
        >
            <div className="grid grid-cols-2 gap-4">
                <Input
                    label="First Name"
                    name="first_name"
                    value={formData.first_name}
                    onChange={handleChange}
                    placeholder="John"
                    error={errors.first_name}
                    required
                />
                <Input
                    label="Last Name"
                    name="last_name"
                    value={formData.last_name}
                    onChange={handleChange}
                    placeholder="Doe"
                    error={errors.last_name}
                    required
                />
            </div>

            <Input
                label="Email"
                type="email"
                name="email"
                value={formData.email}
                onChange={handleChange}
                placeholder="john@example.com"
                error={errors.email}
                disabled={!!initialData}
                required={!initialData}
            />

            <Input
                label={initialData ? 'New Password (optional)' : 'Password'}
                type="password"
                name="password"
                value={formData.password}
                onChange={handleChange}
                placeholder={initialData ? 'Leave blank to keep current' : 'Enter password'}
                error={errors.password}
                required={!initialData}
            />

            <div>
                <label className="block text-sm font-medium text-neutral-700 mb-1.5">
                    Role
                </label>
                <select
                    name="role"
                    value={formData.role}
                    onChange={handleChange}
                    className="w-full px-4 py-3 bg-white border border-neutral-200 rounded-xl focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 outline-none transition-all"
                >
                    <option value="user">User</option>
                    <option value="admin">Admin</option>
                </select>
            </div>

            {apiError && <InlineAlert variant="error" message={apiError} />}

            <div className="flex justify-end gap-3 pt-4">
                <Button type="button" variant="secondary" onClick={onCancel}>
                    Cancel
                </Button>
                <Button type="submit" loading={loading}>
                    {initialData ? 'Update User' : 'Create User'}
                </Button>
            </div>
        </motion.form>
    );
};

export default UserForm;