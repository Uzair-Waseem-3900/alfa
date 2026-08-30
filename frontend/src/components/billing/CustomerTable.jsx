import PropTypes from 'prop-types';
import { Pencil, Trash2, Users } from 'lucide-react';
import Table from '../ui/Table';
import Badge from '../ui/Badge';
import EmptyState from '../ui/EmptyState';

const TIER_BADGE_VARIANT = {
    good: 'success',
    average: 'warning',
    poor: 'error',
};

const CustomerTable = ({ customers, onRowClick, onEdit, onDelete, isAdmin }) => {
    const columns = [
        { key: 'code', label: 'Code', width: '110px' },
        { key: 'name', label: 'Name' },
        { key: 'address', label: 'Address' },
        { key: 'mobile', label: 'Mobile', render: (value) => value || 'N/A' },
        {
            key: 'credit_score',
            label: 'Credit Score',
            width: '140px',
            render: (value, row) => value === null || value === undefined ? (
                <span className="text-neutral-400">N/A</span>
            ) : (
                <span className="flex items-center gap-2">
                    <span className="font-medium text-neutral-900">{value}</span>
                    <Badge variant={TIER_BADGE_VARIANT[row.credit_tier] || 'default'}>
                        {row.credit_tier}
                    </Badge>
                </span>
            ),
        },
        {
            key: 'created_at',
            label: 'Created',
            render: (value) => new Date(value).toLocaleDateString()
        },
        {
            key: 'is_deleted',
            label: 'Status',
            render: (value) => (
                <Badge variant={value ? 'error' : 'success'}>
                    {value ? 'Deleted' : 'Active'}
                </Badge>
            ),
        },
        {
            key: 'actions',
            label: 'Actions',
            width: '110px',
            render: (_, row) => isAdmin && !row.is_deleted && (
                <div className="flex items-center gap-1">
                    <button
                        onClick={(e) => { e.stopPropagation(); onEdit(row); }}
                        className="p-2 min-w-[36px] min-h-[36px] flex items-center justify-center rounded-lg text-primary-600 hover:bg-primary-50 hover:text-primary-700 transition-colors"
                        title="Edit customer"
                        aria-label="Edit customer"
                    >
                        <Pencil className="w-4 h-4" />
                    </button>
                    <button
                        onClick={(e) => { e.stopPropagation(); onDelete(row.id); }}
                        className="p-2 min-w-[36px] min-h-[36px] flex items-center justify-center rounded-lg text-error-600 hover:bg-error-50 hover:text-error-700 transition-colors"
                        title="Delete customer"
                        aria-label="Delete customer"
                    >
                        <Trash2 className="w-4 h-4" />
                    </button>
                </div>
            ),
        },
    ];

    if (customers.length === 0) {
        return (
            <EmptyState
                icon={<Users className="w-8 h-8 text-neutral-400" />}
                title="No Customers Found"
                description="Try adjusting your search or filters"
            />
        );
    }

    return <Table columns={columns} data={customers} onRowClick={onRowClick} />;
};

CustomerTable.propTypes = {
    customers: PropTypes.array.isRequired,
    onRowClick: PropTypes.func,
    onEdit: PropTypes.func,
    onDelete: PropTypes.func,
    isAdmin: PropTypes.bool,
};

export default CustomerTable;
