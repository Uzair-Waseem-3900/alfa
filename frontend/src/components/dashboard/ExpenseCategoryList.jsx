import { useState } from 'react';
import { motion } from 'framer-motion';
import PropTypes from 'prop-types';
import Button from '../ui/Button';
import Input from '../ui/Input';
import Modal from '../ui/Modal';
import LoadingSpinner from '../ui/LoadingSpinner';
import ConfirmDialog from '../ui/ConfirmDialog';

const ExpenseCategoryList = ({ categories, loading, onCreate, onUpdate, onDelete }) => {
    const [showModal, setShowModal] = useState(false);
    const [editingCategory, setEditingCategory] = useState(null);
    const [formData, setFormData] = useState({ name: '', description: '' });
    const [formLoading, setFormLoading] = useState(false);
    const [deleteConfirm, setDeleteConfirm] = useState(null);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setFormLoading(true);
        try {
            if (editingCategory) {
                await onUpdate(editingCategory.id, formData);
            } else {
                await onCreate(formData);
            }
            setShowModal(false);
            resetForm();
        } catch (error) {
            console.error('Failed to save category:', error);
        } finally {
            setFormLoading(false);
        }
    };

    const handleEdit = (category) => {
        setEditingCategory(category);
        setFormData({ name: category.name, description: category.description || '' });
        setShowModal(true);
    };

    const resetForm = () => {
        setFormData({ name: '', description: '' });
        setEditingCategory(null);
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center py-8">
                <LoadingSpinner size="md" />
            </div>
        );
    }

    return (
        <div>
            <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold text-neutral-900">Expense Categories</h3>
                <Button
                    size="sm"
                    onClick={() => {
                        resetForm();
                        setShowModal(true);
                    }}
                >
                    Add Category
                </Button>
            </div>

            {categories.length === 0 ? (
                <p className="text-center text-neutral-500 py-4">No categories yet</p>
            ) : (
                <div className="space-y-2">
                    {categories.map((category) => (
                        <motion.div
                            key={category.id}
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            className="flex items-center justify-between p-3 bg-neutral-50 rounded-lg hover:bg-neutral-100 transition-colors"
                        >
                            <div>
                                <p className="font-medium text-neutral-900">{category.name}</p>
                                {category.description && (
                                    <p className="text-sm text-neutral-500">{category.description}</p>
                                )}
                            </div>
                            <div className="flex gap-2">
                                <button
                                    onClick={() => handleEdit(category)}
                                    className="text-primary-600 hover:text-primary-700 text-sm"
                                >
                                    Edit
                                </button>
                                <button
                                    onClick={() => setDeleteConfirm(category)}
                                    className="text-error-600 hover:text-error-700 text-sm"
                                >
                                    Delete
                                </button>
                            </div>
                        </motion.div>
                    ))}
                </div>
            )}

            {/* Create/Edit Modal */}
            <Modal
                isOpen={showModal}
                onClose={() => {
                    setShowModal(false);
                    resetForm();
                }}
                title={editingCategory ? 'Edit Category' : 'Add Category'}
            >
                <form onSubmit={handleSubmit} className="space-y-4">
                    <Input
                        label="Name"
                        value={formData.name}
                        onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                        placeholder="Enter category name"
                        required
                    />
                    <Input
                        label="Description"
                        value={formData.description}
                        onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                        placeholder="Enter description (optional)"
                    />
                    <div className="flex justify-end gap-3 pt-4">
                        <Button
                            type="button"
                            variant="secondary"
                            onClick={() => {
                                setShowModal(false);
                                resetForm();
                            }}
                        >
                            Cancel
                        </Button>
                        <Button type="submit" loading={formLoading}>
                            {editingCategory ? 'Update' : 'Create'}
                        </Button>
                    </div>
                </form>
            </Modal>

            {/* Delete Confirmation */}
            <ConfirmDialog
                isOpen={!!deleteConfirm}
                onClose={() => setDeleteConfirm(null)}
                onConfirm={() => onDelete(deleteConfirm?.id)}
                title="Delete Category"
                message={`Are you sure you want to delete "${deleteConfirm?.name}"?`}
            />
        </div>
    );
};

ExpenseCategoryList.propTypes = {
    categories: PropTypes.array.isRequired,
    loading: PropTypes.bool,
    onCreate: PropTypes.func.isRequired,
    onUpdate: PropTypes.func.isRequired,
    onDelete: PropTypes.func.isRequired,
};

export default ExpenseCategoryList;