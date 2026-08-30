import PropTypes from 'prop-types';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Trash2, Wallet, Banknote, Smartphone, Landmark } from 'lucide-react';
import Button from '../ui/Button';
import EmptyState from '../ui/EmptyState';

const METHOD_ICONS = {
    cash: Banknote,
    jazzcash: Smartphone,
    easypaisa: Smartphone,
    bank: Landmark,
};

const PaymentHistoryList = ({ payments, onDelete, isAdmin = false }) => {
    if (!payments || payments.length === 0) {
        return (
            <EmptyState
                title="No payments yet"
                description="Payments recorded against this order will appear here."
            />
        );
    }

    return (
        <div className="space-y-2.5">
            {payments.map((payment, index) => {
                const MethodIcon = METHOD_ICONS[payment.method] || Wallet;
                return (
                    <motion.div
                        key={payment.id}
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: index * 0.03 }}
                        className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 bg-neutral-50 rounded-xl border border-neutral-100"
                    >
                        <div className="flex items-start gap-3 min-w-0">
                            <div className="w-9 h-9 rounded-lg bg-primary-50 text-primary-600 flex items-center justify-center flex-shrink-0">
                                <MethodIcon className="w-4.5 h-4.5" />
                            </div>
                            <div className="min-w-0">
                                {payment.reference_number ? (
                                    <Link
                                        to={`/purchases/payments/ref/${payment.reference_number}`}
                                        className="font-medium text-primary-700 hover:text-primary-800 hover:underline break-all"
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
                                            &bull; {new Date(payment.payment_date).toLocaleDateString()}
                                        </span>
                                    )}
                                </p>
                                {payment.note && (
                                    <p className="text-xs text-neutral-400 mt-0.5 break-words">{payment.note}</p>
                                )}
                            </div>
                        </div>
                        <div className="flex items-center justify-between sm:justify-end gap-3 pl-12 sm:pl-0">
                            <div className="text-right">
                                <p className="font-semibold text-success-600 tabular-nums">
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
                                    aria-label="Delete payment"
                                >
                                    <span className="hidden sm:inline">Delete</span>
                                </Button>
                            )}
                        </div>
                    </motion.div>
                );
            })}
        </div>
    );
};

PaymentHistoryList.propTypes = {
    payments: PropTypes.array,
    onDelete: PropTypes.func,
    isAdmin: PropTypes.bool,
};

export default PaymentHistoryList;
