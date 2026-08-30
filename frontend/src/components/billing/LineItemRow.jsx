import { motion } from 'framer-motion';
import PropTypes from 'prop-types';
import { Minus, Plus, Trash2, Package } from 'lucide-react';
import Input from '../ui/Input';
import SearchableSelect from '../ui/SearchableSelect';

const LineItemRow = ({
    index,
    item,
    onSearchProducts,
    onUpdate,
    onRemove,
    canEdit = true,
    errors,
}) => {
    const calculateTotals = () => {
        const gross = (item.quantity || 0) * (item.selling_price || 0);
        const gstAmount = gross * ((item.gst || 0) / 100);
        const whtAmount = gross * ((item.wht || 0) / 100);
        const total = gross + gstAmount - whtAmount;
        return { gross, gstAmount, whtAmount, total };
    };

    const totals = calculateTotals();
    const effectivePrice = (item.selling_price || 0) - (item.discount || 0);

    const stepQuantity = (delta) => {
        const next = Math.max(1, (parseInt(item.quantity, 10) || 0) + delta);
        onUpdate(index, 'quantity', next);
    };

    return (
        <motion.div
            layout
            initial={{ opacity: 0, y: -12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, x: 40, scale: 0.96, transition: { duration: 0.2 } }}
            transition={{ duration: 0.25 }}
            className="relative bg-white border border-neutral-200 rounded-xl p-4 shadow-sm hover:shadow-md hover:border-primary-200 transition-all"
        >
            <div className="flex items-center gap-2 mb-3">
                <div className="w-7 h-7 rounded-lg bg-primary-50 text-primary-600 flex items-center justify-center text-xs font-semibold shrink-0">
                    {index + 1}
                </div>
                <span className="text-xs font-medium text-neutral-400 uppercase tracking-wide">Line Item</span>
            </div>

            {/* Row 1: Product and Quantity */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-3">
                <div className="col-span-1 md:col-span-3">
                    <SearchableSelect
                        label="Product"
                        value={item.product_id || ''}
                        selectedLabel={item.product_label}
                        onChange={(value, option) => {
                            onUpdate(index, 'product_id', parseInt(value));
                            onUpdate(index, 'product_label', option?.label ?? '');
                            onUpdate(index, 'selling_price', option?.sellingPrice ?? 0);
                        }}
                        onSearch={onSearchProducts}
                        placeholder="Search product by name or code"
                        disabled={!canEdit}
                        error={errors?.product_id}
                        required
                    />
                </div>
                <div className="col-span-1">
                    <label className="block text-sm font-medium text-neutral-700 mb-1.5">
                        Quantity<span className="text-error-500 ml-1">*</span>
                    </label>
                    <div className="flex items-stretch rounded-xl border border-neutral-200 overflow-hidden focus-within:ring-2 focus-within:ring-primary-500/20 focus-within:border-primary-500">
                        <button
                            type="button"
                            onClick={() => stepQuantity(-1)}
                            disabled={!canEdit}
                            aria-label="Decrease quantity"
                            className="min-w-[44px] min-h-[44px] flex items-center justify-center bg-neutral-50 text-neutral-500 hover:bg-neutral-100 hover:text-neutral-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            <Minus className="w-4 h-4" />
                        </button>
                        <input
                            type="number"
                            min="1"
                            value={item.quantity || ''}
                            onChange={(e) => onUpdate(index, 'quantity', parseInt(e.target.value) || 0)}
                            disabled={!canEdit}
                            required
                            className="w-full min-h-[44px] text-center outline-none disabled:bg-neutral-50 disabled:cursor-not-allowed [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                        />
                        <button
                            type="button"
                            onClick={() => stepQuantity(1)}
                            disabled={!canEdit}
                            aria-label="Increase quantity"
                            className="min-w-[44px] min-h-[44px] flex items-center justify-center bg-neutral-50 text-neutral-500 hover:bg-neutral-100 hover:text-neutral-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            <Plus className="w-4 h-4" />
                        </button>
                    </div>
                    {errors?.quantity && <p className="mt-1.5 text-sm text-error-500">{errors.quantity}</p>}
                </div>
            </div>

            {/* Row 2: Discount, GST, WHT */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
                <div>
                    <Input
                        label="Discount"
                        type="number"
                        step="0.01"
                        value={item.discount || ''}
                        onChange={(e) => onUpdate(index, 'discount', parseFloat(e.target.value) || 0)}
                        disabled={!canEdit}
                        placeholder="0"
                        error={errors?.discount}
                    />
                    <p className="text-xs text-neutral-400 mt-1">Effective Price: {effectivePrice.toFixed(2)}</p>
                </div>
                <div>
                    <Input
                        label="GST %"
                        type="number"
                        step="0.01"
                        min="0"
                        value={item.gst || ''}
                        onChange={(e) => onUpdate(index, 'gst', parseFloat(e.target.value) || 0)}
                        disabled={!canEdit}
                        placeholder="0"
                        error={errors?.gst}
                    />
                </div>
                <div>
                    <Input
                        label="WHT %"
                        type="number"
                        step="0.01"
                        min="0"
                        value={item.wht || ''}
                        onChange={(e) => onUpdate(index, 'wht', parseFloat(e.target.value) || 0)}
                        disabled={!canEdit}
                        placeholder="0"
                        error={errors?.wht}
                    />
                </div>
            </div>

            {/* Row 3: Selling Price, Gross, Total, Remove */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="col-span-1">
                    <div className="text-sm bg-neutral-50 p-2.5 rounded-lg h-full flex flex-col justify-center">
                        <p className="text-neutral-500 text-xs flex items-center gap-1">
                            <Package className="w-3 h-3" /> Selling Price
                        </p>
                        <p className="font-medium text-neutral-700">
                            {item.selling_price ? parseFloat(item.selling_price).toFixed(2) : '0.00'}
                        </p>
                    </div>
                </div>
                <div className="col-span-1">
                    <div className="text-sm bg-neutral-50 p-2.5 rounded-lg h-full flex flex-col justify-center">
                        <p className="text-neutral-500 text-xs">Gross Amount</p>
                        <p className="font-medium text-neutral-700">{totals.gross.toFixed(2)}</p>
                    </div>
                </div>
                <div className="col-span-1">
                    <div className="text-sm bg-primary-50 p-2.5 rounded-lg h-full flex flex-col justify-center">
                        <p className="text-primary-500 text-xs">Line Total</p>
                        <p className="font-semibold text-primary-700">{totals.total.toFixed(2)}</p>
                    </div>
                </div>
                <div className="col-span-1">
                    {canEdit && (
                        <button
                            type="button"
                            onClick={() => onRemove(index)}
                            aria-label="Remove line item"
                            className="w-full h-full min-h-[44px] flex items-center justify-center gap-1.5 rounded-lg border border-error-200 text-error-600 hover:bg-error-50 transition-colors text-sm font-medium"
                        >
                            <Trash2 className="w-4 h-4" />
                            <span className="hidden sm:inline">Remove</span>
                        </button>
                    )}
                </div>
            </div>
        </motion.div>
    );
};

LineItemRow.propTypes = {
    index: PropTypes.number.isRequired,
    item: PropTypes.object.isRequired,
    onSearchProducts: PropTypes.func.isRequired,
    onUpdate: PropTypes.func.isRequired,
    onRemove: PropTypes.func.isRequired,
    canEdit: PropTypes.bool,
    errors: PropTypes.object,
};

export default LineItemRow;
