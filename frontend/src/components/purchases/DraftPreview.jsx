import { motion } from 'framer-motion';
import PropTypes from 'prop-types';
import { AlertTriangle } from 'lucide-react';
import Card from '../ui/Card';
import Badge from '../ui/Badge';

const DraftPreview = ({ items, totals, warnings }) => {
    const subtotal = parseFloat(totals?.subtotal) || 0;
    const totalCogs = parseFloat(totals?.total_cogs) || 0;
    const grossProfit = parseFloat(totals?.gross_profit) || 0;

    // Calculate GST and WHT totals from items
    const gstTotal = items.reduce((sum, item) => {
        const lineTotal = parseFloat(item.line_total) || 0;
        const gst = parseFloat(item.gst) || 0;
        return sum + (lineTotal * gst / 100);
    }, 0);

    const whtTotal = items.reduce((sum, item) => {
        const lineTotal = parseFloat(item.line_total) || 0;
        const wht = parseFloat(item.wht) || 0;
        return sum + (lineTotal * wht / 100);
    }, 0);

    const grandTotal = subtotal + gstTotal - whtTotal;

    return (
        <Card className="p-6">
            <h3 className="font-semibold text-neutral-900 mb-4">Order Preview</h3>

            {warnings && (warnings.missing_rate || warnings.missing_stock) && (
                <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
                    <div>
                        <p className="text-sm text-amber-700">
                            {warnings.missing_rate && 'Some products are missing selling prices. '}
                            {warnings.missing_stock && 'Some products have insufficient stock.'}
                        </p>
                        <p className="text-xs text-amber-600 mt-1">
                            Preview only — no stock reserved, no prices committed. Confirm to finalise.
                        </p>
                    </div>
                </div>
            )}

            <div className="space-y-2 max-h-60 overflow-y-auto">
                {items.map((item, index) => (
                    <motion.div
                        key={index}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className="flex justify-between text-sm p-2 border-b border-neutral-100"
                    >
                        <div>
                            <span className="font-medium">{item.product_name}</span>
                            <span className="text-neutral-500 ml-2">× {item.quantity}</span>
                            {item.rate_missing && (
                                <Badge variant="warning" className="ml-2">No Rate</Badge>
                            )}
                            {item.stock_insufficient && (
                                <Badge variant="error" className="ml-2">Low Stock</Badge>
                            )}
                        </div>
                        <span className="font-medium">
                            {item.line_total ? parseFloat(item.line_total).toFixed(2) : 'N/A'}
                        </span>
                    </motion.div>
                ))}
            </div>

            <div className="mt-4 pt-4 border-t border-neutral-200 space-y-1">
                <div className="flex justify-between text-sm">
                    <span className="text-neutral-500">Subtotal</span>
                    <span className="font-medium">{subtotal.toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-sm">
                    <span className="text-neutral-500">GST Total</span>
                    <span className="font-medium">{gstTotal.toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-sm">
                    <span className="text-neutral-500">WHT Total</span>
                    <span className="font-medium">{whtTotal.toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-lg font-bold pt-2 border-t border-neutral-200">
                    <span>Grand Total</span>
                    <span className="text-primary-600">{grandTotal.toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-sm pt-1">
                    <span className="text-neutral-500">Total COGS</span>
                    <span className="font-medium">{totalCogs.toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-sm">
                    <span className="text-neutral-500">Gross Profit</span>
                    <span className="font-medium text-success-600">{grossProfit.toFixed(2)}</span>
                </div>
            </div>

            <p className="text-xs text-neutral-400 mt-4 italic">
                Preview only — no stock reserved, no prices committed. Confirm to finalise.
            </p>
        </Card>
    );
};

DraftPreview.propTypes = {
    items: PropTypes.array.isRequired,
    totals: PropTypes.shape({
        subtotal: PropTypes.string,
        total_cogs: PropTypes.string,
        gross_profit: PropTypes.string,
    }).isRequired,
    warnings: PropTypes.shape({
        missing_rate: PropTypes.bool,
        missing_stock: PropTypes.bool,
    }),
};

export default DraftPreview;
