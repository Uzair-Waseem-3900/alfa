import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import PropTypes from 'prop-types';
import { Undo2, PackageOpen } from 'lucide-react';
import Badge from '../ui/Badge';
import Button from '../ui/Button';

const ReturnList = ({ returns, onAccept, isAdmin }) => {
    if (!returns || returns.length === 0) {
        return (
            <div className="text-center py-6 text-neutral-500">
                <PackageOpen className="w-8 h-8 mx-auto mb-2 text-neutral-300" />
                No returns for this invoice
            </div>
        );
    }

    const getStatusBadge = (status) => {
        const variants = {
            pending: 'pending',
            accepted: 'accepted',
        };
        return <Badge variant={variants[status] || 'default'}>{status}</Badge>;
    };

    return (
        <div className="space-y-3">
            {returns.map((returnItem) => (
                <motion.div
                    key={returnItem.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="p-4 bg-neutral-50 rounded-xl border border-neutral-200 hover:bg-neutral-100 hover:border-neutral-300 transition-colors"
                >
                    <div className="flex flex-col sm:flex-row justify-between items-start gap-3">
                        <div className="flex-1 min-w-0 w-full">
                            <div className="flex items-center gap-3 mb-1 flex-wrap">
                                <Link
                                    to={`/billing/returns/${returnItem.id}`}
                                    className="font-medium text-neutral-900 hover:text-primary-600 hover:underline flex items-center gap-1.5"
                                >
                                    <Undo2 className="w-3.5 h-3.5 text-neutral-400" />
                                    {returnItem.reference_number}
                                </Link>
                                {getStatusBadge(returnItem.status)}
                            </div>
                            <p className="text-sm text-neutral-500">
                                Created: {returnItem.created_at ? new Date(returnItem.created_at).toLocaleString() : 'N/A'}
                            </p>
                            {returnItem.note && (
                                <p className="text-sm text-neutral-600 mt-1">{returnItem.note}</p>
                            )}
                            {returnItem.items && returnItem.items.length > 0 && (
                                <div className="mt-2">
                                    <p className="text-sm text-neutral-500">Returned Items:</p>
                                    <div className="mt-1 space-y-1">
                                        {returnItem.items.map((item, idx) => (
                                            <div key={item.id || idx} className="text-sm flex justify-between items-center gap-2 bg-white p-2 rounded-lg border border-neutral-100">
                                                <span className="text-neutral-700 truncate">{item.product_name}</span>
                                                <span className="text-neutral-600 flex-shrink-0">&times; {item.quantity}</span>
                                                <span className="font-medium text-primary-600 flex-shrink-0">
                                                    {item.line_total ? parseFloat(item.line_total).toFixed(2) : '0.00'}
                                                </span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                            {returnItem.total_return_amount && (
                                <div className="mt-2 pt-2 border-t border-neutral-200">
                                    <span className="text-sm text-neutral-500">Total Return Amount: </span>
                                    <span className="font-medium text-primary-600">
                                        {parseFloat(returnItem.total_return_amount).toFixed(2)}
                                    </span>
                                </div>
                            )}
                        </div>
                        <div className="flex sm:flex-col items-start sm:items-end gap-2 w-full sm:w-auto flex-shrink-0">
                            {returnItem.status === 'pending' && isAdmin && (
                                <>
                                    {/* Shelf put-away is allocated on the return's own detail page —
                                        this list view stays compact rather than embedding the full
                                        allocator per item. */}
                                    <Link
                                        to={`/billing/returns/${returnItem.id}`}
                                        className="text-xs text-primary-600 hover:text-primary-700 hover:underline"
                                    >
                                        Allocate Shelves
                                    </Link>
                                    <Button
                                        size="sm"
                                        variant="success"
                                        onClick={() => onAccept(returnItem.id)}
                                    >
                                        Accept Return
                                    </Button>
                                </>
                            )}
                            {returnItem.accepted_at && (
                                <p className="text-xs text-neutral-400 sm:mt-2">
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
};

export default ReturnList;
