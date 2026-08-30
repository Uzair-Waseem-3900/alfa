import Badge from '../ui/Badge';

const OrderStatusBadge = ({ status }) => {
    const variants = {
        draft: 'draft',
        confirmed: 'confirmed',
    };

    const labels = {
        draft: 'Draft',
        confirmed: 'Confirmed',
    };

    return <Badge variant={variants[status] || 'default'}>{labels[status] || status}</Badge>;
};

export default OrderStatusBadge;
