import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import PropTypes from 'prop-types';
import { ArrowRight, Undo2 } from 'lucide-react';
import Badge from '../ui/Badge';
import Button from '../ui/Button';
import EmptyState from '../ui/EmptyState';

const ReturnList = ({ returns, onAccept, isAdmin, orderItems = [] }) => {
    if (!returns || returns.length === 0) {
        return (
            <EmptyState
                title="No returns yet"
                description="Returns filed against this order will appear here."
            />
        );
    }

    const getStatusBadge = (status) => {
        const variants = {
            pending: 'pending',
            accepted: 'accepted',
        };
        return <Badge variant={variants[status] || 'default'}>{status}</Badge>;
    };

    // unit_price/total_amount on a return item are only snapshotted from the
    // original purchase item when the return is ACCEPTED (by design — see
    // PurchaseReturnItem's model docstring) — a pending return legitimately
    // has 0.00 there. Preview the same total the accept step will compute
    // (gross + gst - wht, matching purchases.utils.calculate_total_price)
    // from the original order item's unit_price, so pending returns don't
    // display a misleading 0.00.
    const previewItemTotal = (item) => {
        const orderItem = orderItems.find((oi) => oi.product_code === item.product_code);
        if (!orderItem) return 0;
        const unitPrice = parseFloat(orderItem.unit_price) || 0;
        const gross = unitPrice * item.quantity;
        const gstAmount = gross * ((parseFloat(item.gst) || 0) / 100);
        const whtAmount = gross * ((parseFloat(item.wht) || 0) / 100);
        return gross + gstAmount - whtAmount;
    };

    const displayItemTotal = (returnItem, item) => (
        returnItem.status === 'accepted'
            ? (parseFloat(item.total_amount) || 0)
            : previewItemTotal(item)
    );

    const displayReturnTotal = (returnItem) => (
        returnItem.status === 'accepted'
            ? (parseFloat(returnItem.total_return_amount) || 0)
            : (returnItem.items || []).reduce((sum, item) => sum + previewItemTotal(item), 0)
    );

    return (
        <div className="space-y-3">
            {returns.map((returnItem, index) => (
                <motion.div
                    key={returnItem.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: index * 0.04 }}
                    className="p-4 sm:p-5 bg-neutral-50 rounded-xl border border-neutral-100 hover:bg-neutral-100/70 hover:border-neutral-200 transition-colors"
                >
                    <div className="flex flex-col sm:flex-row justify-between items-start gap-4">
                        <div className="flex-1 min-w-0 w-full">
                            <div className="flex items-center gap-3 mb-1 flex-wrap">
                                <div className="w-8 h-8 rounded-lg bg-primary-50 text-primary-600 flex items-center justify-center flex-shrink-0">
                                    <Undo2 className="w-4 h-4" />
                                </div>
                                <p className="font-semibold text-neutral-900">{returnItem.reference_number}</p>
                                {getStatusBadge(returnItem.status)}
                            </div>
                            <p className="text-sm text-neutral-500 pl-11">
                                Created: {returnItem.created_at ? new Date(returnItem.created_at).toLocaleString() : 'N/A'}
                            </p>
                            {returnItem.note && (
                                <p className="text-sm text-neutral-600 mt-1 pl-11">{returnItem.note}</p>
                            )}
                            {returnItem.items && returnItem.items.length > 0 && (
                                <div className="mt-3 pl-0 sm:pl-11">
                                    <p className="text-xs font-medium text-neutral-500 uppercase tracking-wide mb-1.5">Returned Items</p>
                                    <div className="space-y-1">
                                        {returnItem.items.map((item, idx) => (
                                            <div key={item.id || idx} className="text-sm flex justify-between items-center gap-3 bg-white p-2.5 rounded-lg border border-neutral-100">
                                                <span className="text-neutral-700 truncate">{item.product_name}</span>
                                                <span className="text-neutral-500 flex-shrink-0">&times; {item.quantity}</span>
                                                <span className="font-medium text-primary-700 tabular-nums flex-shrink-0">
                                                    {displayItemTotal(returnItem, item).toFixed(2)}
                                                </span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                            {returnItem.items && returnItem.items.length > 0 && (
                                <div className="mt-2 pt-2 pl-0 sm:pl-11 border-t border-neutral-200">
                                    <span className="text-sm text-neutral-500">Total Return Amount: </span>
                                    <span className="font-semibold text-primary-700 tabular-nums">
                                        {displayReturnTotal(returnItem).toFixed(2)}
                                    </span>
                                </div>
                            )}
                        </div>
                        <div className="text-right w-full sm:w-auto flex-shrink-0">
                            {returnItem.status === 'pending' && isAdmin && (
                                <Link to={`/purchases/returns/${returnItem.id}`} className="block sm:inline-block">
                                    <Button size="sm" variant="success" icon={ArrowRight} className="w-full sm:w-auto">
                                        Allocate & Accept
                                    </Button>
                                </Link>
                            )}
                            {returnItem.accepted_at && (
                                <p className="text-xs text-neutral-400 mt-2">
                                    Accepted: {new Date(returnItem.accepted_at).toLocaleString()}
                                </p>
                            )}
                            {returnItem.accepted_by && (
                                <p className="text-xs text-neutral-400">
                                    By: {returnItem.accepted_by}
                                </p>
                            )}
                        </div>
                    </div>
                </motion.div>
            ))}
        </div>
    );
};

ReturnList.propTypes = {
    returns: PropTypes.array,
    onAccept: PropTypes.func,
    isAdmin: PropTypes.bool,
    orderItems: PropTypes.array,
};

export default ReturnList;
