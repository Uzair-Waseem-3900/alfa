import { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { CalendarClock } from 'lucide-react';
import Modal from '../ui/Modal';
import Input from '../ui/Input';
import Button from '../ui/Button';
import { extractErrorMessage } from '../../utils/errorMessage';

const ExtendDueDateModal = ({ isOpen, onClose, onSubmit, currentDueDate, loading }) => {
    const [dueDate, setDueDate] = useState(currentDueDate || '');
    const [error, setError] = useState('');

    useEffect(() => {
        if (isOpen) {
            setDueDate(currentDueDate || '');
            setError('');
        }
    }, [isOpen, currentDueDate]);

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!dueDate) {
            setError('Please pick a due date.');
            return;
        }
        setError('');
        try {
            await onSubmit(dueDate);
        } catch (err) {
            setError(extractErrorMessage(err, 'Failed to update due date.'));
        }
    };

    return (
        <Modal isOpen={isOpen} onClose={onClose} title="Extend Due Date">
            <form onSubmit={handleSubmit} className="space-y-4">
                <div className="flex items-center gap-3 rounded-xl bg-primary-50 border border-primary-100 p-3">
                    <div className="w-9 h-9 rounded-lg bg-white flex items-center justify-center shadow-sm shrink-0">
                        <CalendarClock className="w-5 h-5 text-primary-600" />
                    </div>
                    <p className="text-sm text-primary-700">
                        Choose a new payment due date for this invoice.
                    </p>
                </div>

                <Input
                    label="New Due Date"
                    type="date"
                    value={dueDate}
                    onChange={(e) => setDueDate(e.target.value)}
                    error={error}
                    required
                />

                <div className="flex justify-end gap-3 pt-2">
                    <Button type="button" variant="secondary" onClick={onClose} disabled={loading}>
                        Cancel
                    </Button>
                    <Button type="submit" loading={loading}>
                        Save
                    </Button>
                </div>
            </form>
        </Modal>
    );
};

ExtendDueDateModal.propTypes = {
    isOpen: PropTypes.bool.isRequired,
    onClose: PropTypes.func.isRequired,
    onSubmit: PropTypes.func.isRequired,
    currentDueDate: PropTypes.string,
    loading: PropTypes.bool,
};

export default ExtendDueDateModal;
