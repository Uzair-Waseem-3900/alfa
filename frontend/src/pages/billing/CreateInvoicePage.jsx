import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { Plus, Receipt, ListPlus, User, CalendarDays, Wallet } from 'lucide-react';
import { billingApi } from '../../services/billingApi';
import { ratesApi } from '../../services/ratesApi';
import { creditScoreApi } from '../../services/creditScoreApi';
import { useToast } from '../../context/ToastContext';
import { creditScoreColorClass, daysFromTodayLocalDate } from '../../utils/helpers';
import Button from '../../components/ui/Button';
import Input from '../../components/ui/Input';
import Select from '../../components/ui/Select';
import SearchableSelect from '../../components/ui/SearchableSelect';
import Card from '../../components/ui/Card';
import InlineAlert from '../../components/ui/InlineAlert';
import EmptyState from '../../components/ui/EmptyState';
import LineItemRow from '../../components/billing/LineItemRow';
import MethodSplitPicker, { isSplitBalanced } from '../../components/paymentMethods/MethodSplitPicker';
import { extractErrorMessage } from '../../utils/errorMessage';

const defaultDueDate = () => daysFromTodayLocalDate(7);

// Normalizes a DRF field error value (string, or list-of-strings) to a
// single display string.
const firstMsg = (val) => (Array.isArray(val) ? val[0] : val);

const CreateInvoicePage = () => {
    const navigate = useNavigate();
    const { toast } = useToast();
    const [loading, setLoading] = useState(false);
    const [selectedCustomerLabel, setSelectedCustomerLabel] = useState('');
    const [creditScore, setCreditScore] = useState(null);

    const [formData, setFormData] = useState({
        customer_id: '',
        payment_type: 'after_delivery',
        advance_amount: '',
        payment_due_date: defaultDueDate(),
        items: [],
    });
    const [methodAllocations, setMethodAllocations] = useState([]);

    // Backend validation errors, mapped onto the relevant UI element.
    const [generalError, setGeneralError] = useState('');
    const [fieldErrors, setFieldErrors] = useState({});
    const [itemErrors, setItemErrors] = useState([]);

    const searchCustomers = async (query) => {
        const res = await billingApi.customers.getAll({ search: query, page_size: 25 });
        const results = res?.results ?? res ?? [];
        return results.map(c => ({ value: c.id, label: `${c.code} - ${c.name}` }));
    };

    // Fires only once, right after a customer is actually selected — not on
    // every search keystroke.
    const handleCustomerSelect = (value, option) => {
        setFormData(prev => ({ ...prev, customer_id: value }));
        setSelectedCustomerLabel(option?.label ?? '');
        setCreditScore(null);
        if (!value) return;
        creditScoreApi.customers.getById(value)
            .then(setCreditScore)
            .catch(() => setCreditScore(null));
    };

    // Products come from the rate list, not the Purchases app — normal users
    // have no Purchases access, but rates are viewable by everyone, and every
    // rate already carries its product + selling price.
    const searchProducts = async (query) => {
        const res = await ratesApi.getAll({ search: query, page_size: 25 });
        const results = res?.results ?? res ?? [];
        return results
            .filter(rate => rate.product?.id)
            .map(rate => ({
                value: rate.product.id,
                label: `${rate.product.code} - ${rate.product.name} (${rate.selling_price ?? 'No price'})`,
                sellingPrice: rate.selling_price || 0,
            }));
    };

    const handleAddItem = () => {
        setFormData(prev => ({
            ...prev,
            items: [
                ...prev.items,
                { product_id: '', quantity: 1, discount: 0, gst: 0, wht: 0, selling_price: 0, _key: `${Date.now()}-${prev.items.length}` }
            ]
        }));
    };

    const handleUpdateItem = (index, field, value) => {
        setFormData(prev => ({
            ...prev,
            items: prev.items.map((item, i) => {
                if (i === index) {
                    return { ...item, [field]: value };
                }
                return item;
            })
        }));
    };

    const handleRemoveItem = (index) => {
        setFormData(prev => ({
            ...prev,
            items: prev.items.filter((_, i) => i !== index)
        }));
        setItemErrors(prev => prev.filter((_, i) => i !== index));
    };

    // Calculate totals
    const calculateTotals = () => {
        let subtotal = 0;
        let gstTotal = 0;
        let whtTotal = 0;
        let grandTotal = 0;

        formData.items.forEach(item => {
            const quantity = parseInt(item.quantity) || 0;
            const sellingPrice = parseFloat(item.selling_price) || 0;
            const discount = parseFloat(item.discount) || 0;
            const gst = parseFloat(item.gst) || 0;
            const wht = parseFloat(item.wht) || 0;

            const effectivePrice = sellingPrice - discount;
            const lineTotal = quantity * effectivePrice;
            const gstAmount = lineTotal * (gst / 100);
            const whtAmount = lineTotal * (wht / 100);
            const total = lineTotal + gstAmount - whtAmount;

            subtotal += lineTotal;
            gstTotal += gstAmount;
            whtTotal += whtAmount;
            grandTotal += total;
        });

        return { subtotal, gstTotal, whtTotal, grandTotal };
    };

    const applyServerErrors = (error) => {
        const data = error?.response?.data;
        const nextFieldErrors = {};
        let nextGeneralError = '';
        let nextItemErrors = [];

        if (data && typeof data === 'object') {
            if (data.advance_amount) nextFieldErrors.advance_amount = firstMsg(data.advance_amount);
            if (data.method_allocations || data.splits) {
                nextFieldErrors.method_allocations = firstMsg(data.method_allocations || data.splits);
            }
            if (data.payment_due_date) nextFieldErrors.payment_due_date = firstMsg(data.payment_due_date);
            if (data.customer_id) nextFieldErrors.customer_id = firstMsg(data.customer_id);

            if (data.items) {
                if (Array.isArray(data.items)) {
                    nextItemErrors = data.items.map(entry => {
                        if (!entry || typeof entry !== 'object') return null;
                        return Object.fromEntries(
                            Object.entries(entry).map(([k, v]) => [k, firstMsg(v)])
                        );
                    });
                    nextGeneralError = 'Please fix the highlighted line item(s) below.';
                } else {
                    nextGeneralError = firstMsg(data.items);
                }
            }

            // Service-level errors that aren't tied to a specific field
            // (e.g. stock shortfalls) surface as a top-level "quantity" key.
            if (data.quantity) {
                nextGeneralError = nextGeneralError || firstMsg(data.quantity);
            }
        }

        if (!nextGeneralError && !Object.keys(nextFieldErrors).length) {
            nextGeneralError = extractErrorMessage(error, 'Failed to create invoice.');
        }

        setFieldErrors(nextFieldErrors);
        setItemErrors(nextItemErrors);
        setGeneralError(nextGeneralError);
        toast.error(nextGeneralError || 'Failed to create invoice.');
    };

    const isAdvance = formData.payment_type === 'advance';
    const advanceAmountValue = parseFloat(formData.advance_amount) || 0;

    const handleSubmit = async (e) => {
        e.preventDefault();
        setGeneralError('');
        setFieldErrors({});
        setItemErrors([]);

        if (isAdvance && !isSplitBalanced(advanceAmountValue, methodAllocations)) {
            setGeneralError('Payment method split must add up to the full advance amount.');
            return;
        }

        setLoading(true);
        try {
            const data = {
                customer_id: parseInt(formData.customer_id),
                payment_type: formData.payment_type,
                advance_amount: isAdvance ? advanceAmountValue : 0,
                ...(isAdvance ? { method_allocations: methodAllocations } : {}),
                payment_due_date: formData.payment_due_date || undefined,
                items: formData.items.map(item => ({
                    product_id: parseInt(item.product_id),
                    quantity: parseInt(item.quantity) || 0,
                    discount: parseFloat(item.discount) || 0,
                    gst: parseFloat(item.gst) || 0,
                    wht: parseFloat(item.wht) || 0,
                })),
            };
            const result = await billingApi.invoices.create(data);
            toast.success('Draft invoice created.');
            navigate(`/billing/invoices/${result.id}`);
        } catch (error) {
            applyServerErrors(error);
        } finally {
            setLoading(false);
        }
    };

    const handleCancel = () => {
        navigate('/billing/invoices');
    };

    const totals = calculateTotals();

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <h1 className="text-3xl font-bold text-neutral-900">Create Invoice</h1>
                    <p className="text-neutral-500 mt-1">Create a new draft invoice</p>
                </div>
                <div className="flex gap-3">
                    <Button variant="secondary" onClick={handleCancel}>
                        Cancel
                    </Button>
                    <Button
                        onClick={handleSubmit}
                        loading={loading}
                        icon={Receipt}
                        disabled={isAdvance && !isSplitBalanced(advanceAmountValue, methodAllocations)}
                    >
                        Create Draft
                    </Button>
                </div>
            </div>

            {generalError && (
                <InlineAlert variant="error" message={generalError} />
            )}

            <form onSubmit={handleSubmit} className="space-y-6">
                <Card className="p-6" hover={false}>
                    <div className="flex items-center gap-2 mb-5">
                        <div className="w-8 h-8 rounded-lg bg-primary-50 flex items-center justify-center">
                            <User className="w-4 h-4 text-primary-600" />
                        </div>
                        <h3 className="font-semibold text-neutral-900">Customer &amp; Terms</h3>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <SearchableSelect
                                label="Customer"
                                value={formData.customer_id}
                                selectedLabel={selectedCustomerLabel}
                                onChange={handleCustomerSelect}
                                onSearch={searchCustomers}
                                placeholder="Search customer by name or code"
                                error={fieldErrors.customer_id}
                                required
                            />
                            {creditScore && (
                                <p className={`text-sm mt-1 font-medium ${creditScoreColorClass(creditScore.tier)}`}>
                                    Credit Score: {creditScore.score}
                                </p>
                            )}
                        </div>

                        <Input
                            label="Due Date"
                            type="date"
                            icon={CalendarDays}
                            value={formData.payment_due_date}
                            onChange={(e) => setFormData(prev => ({ ...prev, payment_due_date: e.target.value }))}
                            error={fieldErrors.payment_due_date}
                            required
                        />
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                        <Select
                            label="Payment Type"
                            value={formData.payment_type}
                            onChange={(e) => setFormData(prev => ({ ...prev, payment_type: e.target.value }))}
                            options={[
                                { value: 'advance', label: 'Advance' },
                                { value: 'after_delivery', label: 'After Delivery' },
                            ]}
                            required
                        />

                        {formData.payment_type === 'advance' && (
                            <Input
                                label="Advance Amount (PKR)"
                                type="number"
                                step="0.01"
                                min="0"
                                icon={Wallet}
                                value={formData.advance_amount}
                                onChange={(e) => setFormData(prev => ({ ...prev, advance_amount: e.target.value }))}
                                placeholder="Enter advance amount"
                                error={fieldErrors.advance_amount}
                                required
                            />
                        )}
                    </div>

                    {isAdvance && (
                        <div className="mt-4">
                            <p className="text-sm font-medium text-neutral-700 mb-2">Advance Payment Method</p>
                            <MethodSplitPicker
                                totalAmount={advanceAmountValue}
                                value={methodAllocations}
                                onChange={setMethodAllocations}
                                error={fieldErrors.method_allocations}
                            />
                        </div>
                    )}
                </Card>

                <Card className="p-6" hover={false}>
                    <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-2">
                            <div className="w-8 h-8 rounded-lg bg-primary-50 flex items-center justify-center">
                                <ListPlus className="w-4 h-4 text-primary-600" />
                            </div>
                            <h3 className="font-semibold text-neutral-900">Line Items</h3>
                        </div>
                        <Button size="sm" onClick={handleAddItem} icon={Plus}>
                            Add Item
                        </Button>
                    </div>

                    <div className="space-y-3">
                        {formData.items.length === 0 ? (
                            <EmptyState
                                title="No items added yet"
                                description='Click "Add Item" to start building this invoice.'
                            />
                        ) : (
                            <AnimatePresence initial={false}>
                                {formData.items.map((item, index) => (
                                    <LineItemRow
                                        key={item._key || index}
                                        index={index}
                                        item={item}
                                        onSearchProducts={searchProducts}
                                        onUpdate={handleUpdateItem}
                                        onRemove={handleRemoveItem}
                                        canEdit={true}
                                        errors={itemErrors[index] || undefined}
                                    />
                                ))}
                            </AnimatePresence>
                        )}
                    </div>

                    {/* Totals Summary */}
                    {formData.items.length > 0 && (
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            className="mt-6 pt-4 border-t border-neutral-200"
                        >
                            <div className="flex flex-col items-end space-y-2 max-w-xs ml-auto">
                                <div className="flex justify-between w-full">
                                    <span className="text-sm text-neutral-500">Subtotal:</span>
                                    <span className="text-sm font-medium text-neutral-900">
                                        PKR {totals.subtotal.toFixed(2)}
                                    </span>
                                </div>
                                <div className="flex justify-between w-full">
                                    <span className="text-sm text-neutral-500">GST Total:</span>
                                    <span className="text-sm font-medium text-neutral-900">
                                        PKR {totals.gstTotal.toFixed(2)}
                                    </span>
                                </div>
                                <div className="flex justify-between w-full">
                                    <span className="text-sm text-neutral-500">WHT Total:</span>
                                    <span className="text-sm font-medium text-neutral-900">
                                        PKR {totals.whtTotal.toFixed(2)}
                                    </span>
                                </div>
                                <div className="flex justify-between w-full pt-2 border-t border-neutral-200">
                                    <span className="text-base font-semibold text-neutral-900">Grand Total:</span>
                                    <span className="text-base font-bold text-primary-600">
                                        PKR {totals.grandTotal.toFixed(2)}
                                    </span>
                                </div>
                            </div>
                        </motion.div>
                    )}
                </Card>
            </form>
        </div>
    );
};

export default CreateInvoicePage;
