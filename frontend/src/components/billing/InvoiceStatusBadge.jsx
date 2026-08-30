import { FileEdit, CheckCircle2, RotateCcw, Undo2 } from 'lucide-react';
import Badge from '../ui/Badge';

const InvoiceStatusBadge = ({ status }) => {
    const variants = {
        draft: 'draft',
        confirmed: 'confirmed',
        partial: 'warning',
        returned: 'info',
    };

    const labels = {
        draft: 'Draft',
        confirmed: 'Confirmed',
        partial: 'Partial Return',
        returned: 'Returned',
    };

    const icons = {
        draft: FileEdit,
        confirmed: CheckCircle2,
        partial: RotateCcw,
        returned: Undo2,
    };

    const Icon = icons[status];

    return (
        <Badge variant={variants[status] || 'default'} className="gap-1">
            {Icon && <Icon className="w-3 h-3" />}
            {labels[status] || status}
        </Badge>
    );
};

export default InvoiceStatusBadge;