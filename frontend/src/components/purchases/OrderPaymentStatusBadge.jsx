import Badge from '../ui/Badge';

const OrderPaymentStatusBadge = ({ status }) => {
    const variants = {
        unpaid: 'unpaid',
        partial: 'partial',
        paid: 'paid',
    };

    const labels = {
        unpaid: 'Unpaid',
        partial: 'Partial',
        paid: 'Paid',
    };

    return <Badge variant={variants[status] || 'default'}>{labels[status] || status}</Badge>;
};

export default OrderPaymentStatusBadge;
