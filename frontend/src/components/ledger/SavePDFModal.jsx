import { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import Modal from '../ui/Modal';
import Input from '../ui/Input';
import Button from '../ui/Button';

const SavePDFModal = ({
    isOpen,
    onClose,
    onSubmit,
    loading,
    defaultFileName,
    dateFrom,
    dateTo
}) => {
    const [formData, setFormData] = useState({
        file_name: defaultFileName || '',
        date_from: dateFrom || '',
        date_to: dateTo || '',
    });

    useEffect(() => {
        if (isOpen) {
            setFormData({
                file_name: defaultFileName || '',
                date_from: dateFrom || '',
                date_to: dateTo || '',
            });
        }
    }, [isOpen, defaultFileName, dateFrom, dateTo]);

    const handleChange = (e) => {
        const { name, value } = e.target;
        setFormData(prev => ({ ...prev, [name]: value }));
    };

    const handleSubmit = (e) => {
        e.preventDefault();
        const data = {};
        if (formData.file_name) data.file_name = formData.file_name;
        if (formData.date_from) data.date_from = formData.date_from;
        if (formData.date_to) data.date_to = formData.date_to;
        onSubmit(data);
    };

    return (
        <Modal
            isOpen={isOpen}
            onClose={onClose}
            title="Save Ledger PDF"
            size="md"
        >
            <form onSubmit={handleSubmit} className="space-y-4">
                <Input
                    label="File Name"
                    name="file_name"
                    value={formData.file_name}
                    onChange={handleChange}
                    placeholder="Enter file name"
                />
                <p className="text-xs text-neutral-500">
                    Default: Ledger_{defaultFileName || 'supplier'}
                </p>
                <div className="grid grid-cols-2 gap-3">
                    <Input
                        label="Date From"
                        type="date"
                        name="date_from"
                        value={formData.date_from}
                        onChange={handleChange}
                    />
                    <Input
                        label="Date To"
                        type="date"
                        name="date_to"
                        value={formData.date_to}
                        onChange={handleChange}
                    />
                </div>
                <div className="flex justify-end gap-3 pt-4">
                    <Button type="button" variant="secondary" onClick={onClose}>
                        Cancel
                    </Button>
                    <Button type="submit" loading={loading}>
                        Save PDF
                    </Button>
                </div>
            </form>
        </Modal>
    );
};

SavePDFModal.propTypes = {
    isOpen: PropTypes.bool.isRequired,
    onClose: PropTypes.func.isRequired,
    onSubmit: PropTypes.func.isRequired,
    loading: PropTypes.bool,
    defaultFileName: PropTypes.string,
    dateFrom: PropTypes.string,
    dateTo: PropTypes.string,
};

export default SavePDFModal;