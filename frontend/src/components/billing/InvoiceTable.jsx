import PropTypes from 'prop-types';
import { Pencil, Trash2, CheckCircle2, Printer, CalendarClock } from 'lucide-react';
import Table from '../ui/Table';
import Button from '../ui/Button';
import EmptyState from '../ui/EmptyState';
import InvoiceStatusBadge from './InvoiceStatusBadge';
import PaymentStatusBadge from './PaymentStatusBadge';

const InvoiceTable = ({
    invoices,
    onRowClick,
    onEdit,
    onDelete,
    onConfirm,
    onPrint,
    onExtendDueDate,
    isAdmin,
    showActions = true
}) => {
    const columns = [
        { key: 'bill_number', label: 'Bill #', width: '120px', render: (value) => <span className="font-medium text-neutral-900">{value}</span> },
        {
            key: 'customer',
            label: 'Customer',
            render: (value) => value?.name || 'N/A'
        },
        {
            key: 'status',
            label: 'Status',
            render: (value) => <InvoiceStatusBadge status={value} />
        },
        {
            key: 'grand_total',
            label: 'Total (PKR)',
            render: (value) => {
                const num = typeof value === 'string' ? parseFloat(value) : value;
                return <span className="font-medium">{isNaN(num) ? '0.00' : num.toFixed(2)}</span>;
            }
        },
        {
            key: 'payment_status',
            label: 'Payment',
            render: (value) => <PaymentStatusBadge status={value} />
        },
        {
            key: 'credit_outstanding',
            label: 'Outstanding (PKR)',
            render: (value) => {
                const num = typeof value === 'string' ? parseFloat(value) : value;
                return isNaN(num) ? '0.00' : num.toFixed(2);
            }
        },
        {
            key: 'payment_due_date',
            label: 'Due Date',
            render: (value) => value ? new Date(value).toLocaleDateString() : 'N/A'
        },
        {
            key: 'confirmed_at',
            label: 'Confirmed',
            render: (value) => value ? new Date(value).toLocaleDateString() : 'N/A'
        },
        {
            key: 'created_at',
            label: 'Created',
            render: (value) => new Date(value).toLocaleDateString()
        },
    ];

    if (showActions) {
        columns.push({
            key: 'actions',
            label: 'Actions',
            width: '220px',
            render: (_, row) => (
                <div className="flex gap-1.5 flex-wrap">
                    {row.status === 'draft' && (
                        <>
                            <Button
                                size="sm"
                                variant="secondary"
                                icon={Pencil}
                                onClick={(e) => { e.stopPropagation(); onEdit(row); }}
                            >
                                Edit
                            </Button>
                            <Button
                                size="sm"
                                variant="danger"
                                icon={Trash2}
                                onClick={(e) => { e.stopPropagation(); onDelete(row.id); }}
                            >
                                Delete
                            </Button>
                            {isAdmin && (
                                <Button
                                    size="sm"
                                    variant="success"
                                    icon={CheckCircle2}
                                    onClick={(e) => { e.stopPropagation(); onConfirm(row.id); }}
                                >
                                    Confirm
                                </Button>
                            )}
                        </>
                    )}
                    {row.status !== 'draft' && (
                        <>
                            {isAdmin && (
                                <Button
                                    size="sm"
                                    variant="secondary"
                                    title="Print"
                                    onClick={(e) => { e.stopPropagation(); onPrint(row.id, false); }}
                                >
                                    <Printer className="w-4 h-4 shrink-0" />
                                </Button>
                            )}
                            {isAdmin && row.payment_status !== 'paid' && onExtendDueDate && (
                                <Button
                                    size="sm"
                                    variant="secondary"
                                    title="Extend Due Date"
                                    onClick={(e) => { e.stopPropagation(); onExtendDueDate(row); }}
                                >
                                    <CalendarClock className="w-4 h-4 shrink-0" />
                                </Button>
                            )}
                        </>
                    )}
                </div>
            ),
        });
    }

    if (invoices.length === 0) {
        return (
            <EmptyState
                title="No Invoices Found"
                description="Try adjusting your search or filters"
            />
        );
    }

    return <Table columns={columns} data={invoices} onRowClick={onRowClick} />;
};

InvoiceTable.propTypes = {
    invoices: PropTypes.array.isRequired,
    onRowClick: PropTypes.func,
    onEdit: PropTypes.func,
    onDelete: PropTypes.func,
    onConfirm: PropTypes.func,
    onPrint: PropTypes.func,
    onExtendDueDate: PropTypes.func,
    isAdmin: PropTypes.bool,
    showActions: PropTypes.bool,
};

export default InvoiceTable;
