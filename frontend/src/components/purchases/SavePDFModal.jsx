import { useState } from 'react';
import PropTypes from 'prop-types';
import Modal from '../ui/Modal';
import Input from '../ui/Input';
import Button from '../ui/Button';

const SavePDFModal = ({ isOpen, onClose, onSubmit, loading, defaultFileName }) => {
    const [fileName, setFileName] = useState(defaultFileName || '');

    const handleSubmit = (e) => {
        e.preventDefault();
        onSubmit(fileName || defaultFileName);
    };

    return (
        <Modal
            isOpen={isOpen}
            onClose={onClose}
            title="Save PDF"
            size="md"
        >
            <form onSubmit={handleSubmit} className="space-y-4">
                <Input
                    label="File Name"
                    value={fileName}
                    onChange={(e) => setFileName(e.target.value)}
                    placeholder="Enter file name"
                    required
                />
                <p className="text-xs text-neutral-500">
                    Default: {defaultFileName}
                </p>
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
};

export default SavePDFModal;
