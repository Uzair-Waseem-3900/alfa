import { CircleDollarSign, CircleAlert, CircleCheckBig } from 'lucide-react';
import Badge from '../ui/Badge';

const PaymentStatusBadge = ({ status }) => {
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

    const icons = {
        unpaid: CircleAlert,
        partial: CircleDollarSign,
        paid: CircleCheckBig,
    };

    const Icon = icons[status];

    return (
        <Badge variant={variants[status] || 'default'} className="gap-1">
            {Icon && <Icon className="w-3 h-3" />}
            {labels[status] || status}
        </Badge>
    );
};

export default PaymentStatusBadge;