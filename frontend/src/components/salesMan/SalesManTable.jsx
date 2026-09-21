import PropTypes from 'prop-types';
import { Trash2, Handshake } from 'lucide-react';
import Table from '../ui/Table';
import EmptyState from '../ui/EmptyState';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toLocaleString('en-PK', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

const SalesManTable = ({ salesMen, onRowClick, onDelete, isAdmin }) => {
    const columns = [
        { key: 'code', label: 'Code', width: '110px' },
        { key: 'name', label: 'Name' },
        { key: 'phone', label: 'Phone', render: (value) => value || 'N/A' },
        { key: 'total_customers', label: 'Customers', width: '110px' },
        {
            key: 'total_outstanding',
            label: 'Total Outstanding',
            width: '160px',
            render: (value) => <span className="font-medium text-neutral-900">Rs. {fmt(value)}</span>,
        },
        {
            key: 'actions',
            label: 'Actions',
            width: '80px',
            render: (_, row) => isAdmin && (
                <button
                    onClick={(e) => { e.stopPropagation(); onDelete(row.id); }}
                    className="p-2 min-w-[36px] min-h-[36px] flex items-center justify-center rounded-lg text-error-600 hover:bg-error-50 hover:text-error-700 transition-colors"
                    title="Delete sales man"
                    aria-label="Delete sales man"
                >
                    <Trash2 className="w-4 h-4" />
                </button>
            ),
        },
    ];

    if (salesMen.length === 0) {
        return (
            <EmptyState
                icon={<Handshake className="w-8 h-8 text-neutral-400" />}
                title="No Sales Men Found"
                description="Add a sales man to get started"
            />
        );
    }

    return <Table columns={columns} data={salesMen} onRowClick={onRowClick} />;
};

SalesManTable.propTypes = {
    salesMen: PropTypes.array.isRequired,
    onRowClick: PropTypes.func,
    onDelete: PropTypes.func,
    isAdmin: PropTypes.bool,
};

export default SalesManTable;
