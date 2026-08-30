import PropTypes from 'prop-types';
import Card from '../ui/Card';
import OrderPaymentStatusBadge from './OrderPaymentStatusBadge';

const OrderSummaryCard = ({ summary }) => {
    if (!summary) return null;

    return (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Card className="p-4">
                <p className="text-sm text-neutral-500">Net Payable</p>
                <p className="text-xl font-bold text-neutral-900">
                    {typeof summary.net_payable === 'string'
                        ? parseFloat(summary.net_payable).toFixed(2)
                        : '0.00'}
                </p>
            </Card>
            <Card className="p-4">
                <p className="text-sm text-neutral-500">Total Paid</p>
                <p className="text-xl font-bold text-success-600">
                    {typeof summary.total_paid === 'string'
                        ? parseFloat(summary.total_paid).toFixed(2)
                        : '0.00'}
                </p>
            </Card>
            <Card className="p-4">
                <p className="text-sm text-neutral-500">Payable Outstanding</p>
                <p className="text-xl font-bold text-error-600">
                    {typeof summary.payable_outstanding === 'string'
                        ? parseFloat(summary.payable_outstanding).toFixed(2)
                        : '0.00'}
                </p>
            </Card>
            <Card className="p-4">
                <p className="text-sm text-neutral-500">Payment Status</p>
                <OrderPaymentStatusBadge status={summary.payment_status} />
            </Card>
        </div>
    );
};

OrderSummaryCard.propTypes = {
    summary: PropTypes.object,
};

export default OrderSummaryCard;
