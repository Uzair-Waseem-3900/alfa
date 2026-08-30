import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { extractErrorMessage } from '../utils/errorMessage';
import { usersApi } from '../utils/api';
import Input from '../components/common/Input';
import Button from '../components/common/Button';
import Card from '../components/common/Card';
import ChangePasswordModal from '../components/users/ChangePasswordModal';

const Profile = () => {
    const { user, updateUser } = useAuth();
    const { toast } = useToast();
    const [formData, setFormData] = useState({
        first_name: user?.first_name || '',
        last_name: user?.last_name || '',
    });
    const [loading, setLoading] = useState(false);
    const [showPasswordModal, setShowPasswordModal] = useState(false);

    const handleChange = (e) => {
        const { name, value } = e.target;
        setFormData(prev => ({ ...prev, [name]: value }));
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        try {
            const updatedUser = await usersApi.updateProfile(formData);
            updateUser(updatedUser);
            toast.success('Profile updated successfully');
        } catch (error) {
            console.error('Failed to update profile:', error);
            toast.error(extractErrorMessage(error, 'Failed to update profile'));
        } finally {
            setLoading(false);
        }
    };

    const handleChangePassword = async (data) => {
        // data will contain { new_password, confirm_password }
        await usersApi.changeOwnPassword(data);
        toast.success('Password changed successfully');
    };

    if (!user) return null;

    return (
        <div className="max-w-2xl mx-auto space-y-6">
            <div>
                <h1 className="text-3xl font-bold text-neutral-900">Profile</h1>
                <p className="text-neutral-500 mt-1">Manage your account settings</p>
            </div>

            <Card className="p-6">
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div className="flex items-center gap-4 pb-4 border-b border-neutral-200">
                        <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-primary-600 to-accent-600 flex items-center justify-center text-white text-2xl font-semibold">
                            {user.first_name?.[0]}{user.last_name?.[0]}
                        </div>
                        <div>
                            <p className="text-sm text-neutral-500">Role</p>
                            <p className="font-semibold text-neutral-900 capitalize">{user.role}</p>
                            <p className="text-sm text-neutral-500">{user.email}</p>
                        </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <Input
                            label="First Name"
                            name="first_name"
                            value={formData.first_name}
                            onChange={handleChange}
                            placeholder="John"
                            required
                        />
                        <Input
                            label="Last Name"
                            name="last_name"
                            value={formData.last_name}
                            onChange={handleChange}
                            placeholder="Doe"
                            required
                        />
                    </div>

                    <Input
                        label="Email"
                        type="email"
                        value={user.email}
                        disabled
                    />

                    <div className="flex gap-3 pt-4">
                        <Button type="submit" loading={loading}>
                            Update Profile
                        </Button>
                        <Button
                            type="button"
                            variant="secondary"
                            onClick={() => setShowPasswordModal(true)}
                        >
                            Change Password
                        </Button>
                    </div>
                </form>
            </Card>

            <ChangePasswordModal
                isOpen={showPasswordModal}
                onClose={() => setShowPasswordModal(false)}
                onSubmit={handleChangePassword}
                loading={loading}
                isSuperuser={false}
            />
        </div>
    );
};

export default Profile;