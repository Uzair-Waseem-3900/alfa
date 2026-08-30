import { useState } from 'react';
import { motion } from 'framer-motion';
import SearchBar from '../common/SearchBar';

const UserFilters = ({ onFilter, onSearch, onRoleFilter }) => {
    const [role, setRole] = useState('');

    const handleRoleChange = (e) => {
        const value = e.target.value;
        setRole(value);
        onRoleFilter(value);
    };

    return (
        <motion.div
            className="flex flex-col sm:flex-row gap-4 mb-6"
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
        >
            <SearchBar
                onSearch={onSearch}
                placeholder="Search users by name or email..."
                className="flex-1"
            />

            <div className="flex gap-3">
                <select
                    value={role}
                    onChange={handleRoleChange}
                    className="px-4 py-2.5 bg-white border border-neutral-200 rounded-xl focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 outline-none transition-all"
                >
                    <option value="">All Roles</option>
                    <option value="user">User</option>
                    <option value="admin">Admin</option>
                    <option value="superuser">Superuser</option>
                </select>

                <button
                    onClick={onFilter}
                    className="px-4 py-2.5 bg-primary-600 text-white rounded-xl hover:bg-primary-700 transition-colors"
                >
                    Apply Filters
                </button>
            </div>
        </motion.div>
    );
};

export default UserFilters;