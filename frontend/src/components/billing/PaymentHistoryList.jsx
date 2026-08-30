import PropTypes from 'prop-types';
import { Link } from 'react-router-dom';
import { Wallet, Trash2 } from 'lucide-react';
import Button from '../ui/Button';
import EmptyState from '../ui/EmptyState';

const PaymentHistoryList = ({ payments, onDelete, isAdmin = false }) => {
    if (!payments || payments.length === 0) {
        return (
            <EmptyState
                icon={<Wallet className="w-10 h-10 text-neutral-300" />}
                title="No payments yet"
                description="Payments recorded for this invoice will appear here."
            />
        );
    }

    return (
        <div className="space-y-2">
            {payments.map((payment) => (
                <div
                    key={payment.id}
                    className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 sm:p-4 bg-neutral-50 rounded-xl border border-neutral-100"
                >
                    <div className="min-w-0">
                        {parseFloat(payment.amount) > 0 ? (
                            <Link
                                to={`/billing/payments/${payment.id}`}
                                className="font-medium text-primary-600 hover:text-primary-700 hover:underline break-all"
                            >
                                {payment.reference_number}
                            </Link>
                        ) : (
                            <p className="font-medium">{payment.reference_number}</p>
                        )}
                        <p className="text-sm text-neutral-500">
                            {Array.isArray(payment.allocations) && payment.allocations.length > 0
                                ? payment.allocations.map((a) => `${a.payment_method_name}: ${parseFloat(a.amount).toFixed(2)}`).join(', ')
                                : (payment.method_display || payment.method)}
                            {payment.payment_date && (
                                <span className="ml-2">
                                    • {new Date(payment.payment_date).toLocaleDateString()}
                                </span>
                            )}
                        </p>
                        {payment.note && (
                            <p className="text-xs text-neutral-400 mt-0.5 truncate">{payment.note}</p>
                        )}
                    </div>
                    <div className="flex items-center justify-between sm:justify-end gap-3">
                        <div className="text-right">
                            <p className="font-medium text-success-600 tabular-nums">
                                {typeof payment.amount === 'string'
                                    ? parseFloat(payment.amount).toFixed(2)
                                    : '0.00'}
                            </p>
                            <p className="text-xs text-neutral-500">
                                {payment.created_by || 'System'}
                            </p>
                        </div>
                        {isAdmin && onDelete && (
                            <Button
                                size="sm"
                                variant="danger"
                                icon={Trash2}
                                onClick={() => onDelete(payment.id)}
                            >
                                <span className="hidden sm:inline">Delete</span>
                            </Button>
                        )}
                    </div>
                </div>
            ))}
        </div>
    );
};

PaymentHistoryList.propTypes = {
    payments: PropTypes.array,
    onDelete: PropTypes.func,
    isAdmin: PropTypes.bool,
};

export default PaymentHistoryList;
