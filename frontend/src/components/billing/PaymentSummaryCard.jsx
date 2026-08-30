import PropTypes from 'prop-types';
import { Receipt, Wallet, AlertCircle } from 'lucide-react';
import Card from '../ui/Card';
import PaymentStatusBadge from './PaymentStatusBadge';

const toAmount = (value) => (typeof value === 'string' ? parseFloat(value) : (Number(value) || 0));

const PaymentSummaryCard = ({ summary }) => {
    if (!summary) return null;

    return (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
            <Card hover={false} className="p-4 sm:p-5">
                <div className="flex items-center gap-2 text-neutral-500">
                    <Receipt className="w-4 h-4" />
                    <p className="text-xs sm:text-sm font-medium">Grand Total</p>
                </div>
                <p className="text-lg sm:text-xl font-bold text-neutral-900 mt-1 tabular-nums">
                    {toAmount(summary.grand_total).toFixed(2)}
                </p>
            </Card>
            <Card hover={false} className="p-4 sm:p-5">
                <div className="flex items-center gap-2 text-success-600">
                    <Wallet className="w-4 h-4" />
                    <p className="text-xs sm:text-sm font-medium">Total Paid</p>
                </div>
                <p className="text-lg sm:text-xl font-bold text-success-600 mt-1 tabular-nums">
                    {toAmount(summary.total_paid).toFixed(2)}
                </p>
            </Card>
            <Card hover={false} className="p-4 sm:p-5">
                <div className="flex items-center gap-2 text-error-600">
                    <AlertCircle className="w-4 h-4" />
                    <p className="text-xs sm:text-sm font-medium">Credit Outstanding</p>
                </div>
                <p className="text-lg sm:text-xl font-bold text-error-600 mt-1 tabular-nums">
                    {toAmount(summary.credit_outstanding).toFixed(2)}
                </p>
            </Card>
            <Card hover={false} className="p-4 sm:p-5">
                <p className="text-xs sm:text-sm font-medium text-neutral-500">Payment Status</p>
                <div className="mt-2">
                    <PaymentStatusBadge status={summary.payment_status} />
                </div>
            </Card>
        </div>
    );
};

PaymentSummaryCard.propTypes = {
    summary: PropTypes.object,
};

export default PaymentSummaryCard;
