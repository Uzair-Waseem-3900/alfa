import { useState } from 'react';
import Modal from '../common/Modal';
import Input from '../common/Input';
import Button from '../common/Button';
import InlineAlert from '../ui/InlineAlert';

const ChangePasswordModal = ({ isOpen, onClose, onSubmit, loading, isSuperuser }) => {
    const [formData, setFormData] = useState({
        email: '',
        new_password: '',
        confirm_password: '',
    });

    const [errors, setErrors] = useState({});
    const [apiError, setApiError] = useState('');

    const handleChange = (e) => {
        const { name, value } = e.target;
        setFormData(prev => ({ ...prev, [name]: value }));
        if (errors[name]) {
            setErrors(prev => ({ ...prev, [name]: '' }));
        }
        if (apiError) {
            setApiError('');
        }
    };

    const validate = () => {
        const newErrors = {};
        if (isSuperuser && !formData.email) {
            newErrors.email = 'Email is required';
        }
        if (!formData.new_password) {
            newErrors.new_password = 'Password is required';
        } else if (formData.new_password.length < 8) {
            newErrors.new_password = 'Password must be at least 8 characters';
        }
        if (!formData.confirm_password) {
            newErrors.confirm_password = 'Please confirm your password';
        } else if (formData.new_password !== formData.confirm_password) {
            newErrors.confirm_password = 'Passwords do not match';
        }
        setErrors(newErrors);
        return Object.keys(newErrors).length === 0;
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setApiError('');

        if (!validate()) {
            return;
        }

        try {
            let data;
            if (isSuperuser) {
                data = {
                    email: formData.email,
                    new_password: formData.new_password,
                    confirm_password: formData.confirm_password,
                };
            } else {
                data = {
                    new_password: formData.new_password,
                    confirm_password: formData.confirm_password,
                };
            }

            await onSubmit(data);
            // Reset form on success
            setFormData({
                email: '',
                new_password: '',
                confirm_password: '',
            });
            onClose();
        } catch (error) {
            // Handle API errors
            const errorData = error.response?.data;
            if (errorData) {
                if (typeof errorData === 'object') {
                    // Handle field-specific errors
                    const fieldErrors = {};
                    Object.keys(errorData).forEach(key => {
                        if (key === 'confirm_password' || key === 'new_password' || key === 'email') {
                            fieldErrors[key] = errorData[key][0] || 'Invalid input';
                        } else {
                            setApiError(errorData[key] || 'An error occurred');
                        }
                    });
                    setErrors(prev => ({ ...prev, ...fieldErrors }));
                } else {
                    setApiError(errorData);
                }
            } else {
                setApiError('Failed to change password. Please try again.');
            }
        }
    };

    const handleClose = () => {
        setFormData({
            email: '',
            new_password: '',
            confirm_password: '',
        });
        setErrors({});
        setApiError('');
        onClose();
    };

    return (
        <Modal
            isOpen={isOpen}
            onClose={handleClose}
            title={isSuperuser ? 'Change User Password' : 'Change Password'}
        >
            <form onSubmit={handleSubmit} className="space-y-4">
                {isSuperuser && (
                    <Input
                        label="User Email"
                        type="email"
                        name="email"
                        value={formData.email}
                        onChange={handleChange}
                        placeholder="user@example.com"
                        error={errors.email}
                        required
                    />
                )}

                <Input
                    label="New Password"
                    type="password"
                    name="new_password"
                    value={formData.new_password}
                    onChange={handleChange}
                    placeholder="Enter new password (min 8 characters)"
                    error={errors.new_password}
                    required
                />

                <Input
                    label="Confirm Password"
                    type="password"
                    name="confirm_password"
                    value={formData.confirm_password}
                    onChange={handleChange}
                    placeholder="Confirm new password"
                    error={errors.confirm_password}
                    required
                />

                {apiError && <InlineAlert variant="error" message={apiError} />}

                <div className="flex justify-end gap-3 pt-4">
                    <Button type="button" variant="secondary" onClick={handleClose}>
                        Cancel
                    </Button>
                    <Button type="submit" loading={loading}>
                        Change Password
                    </Button>
                </div>
            </form>
        </Modal>
    );
};

export default ChangePasswordModal;