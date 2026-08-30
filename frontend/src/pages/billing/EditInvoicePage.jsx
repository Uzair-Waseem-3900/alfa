import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useParams, useNavigate } from 'react-router-dom';
import { Plus, ListPlus, CalendarDays, Wallet, FileWarning } from 'lucide-react';
import { billingApi } from '../../services/billingApi';
import { ratesApi } from '../../services/ratesApi';
import { useToast } from '../../context/ToastContext';
import Button from '../../components/ui/Button';
import BackLink from '../../components/ui/BackLink';
import Input from '../../components/ui/Input';
import Select from '../../components/ui/Select';
import SearchableSelect from '../../components/ui/SearchableSelect';
import Card from '../../components/ui/Card';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import InlineAlert from '../../components/ui/InlineAlert';
import EmptyState from '../../components/ui/EmptyState';
import LineItemRow from '../../components/billing/LineItemRow';
import DraftPreviewPanel from '../../components/billing/DraftPreviewPanel';
import MethodSplitPicker, { isSplitBalanced } from '../../components/paymentMethods/MethodSplitPicker';
import { extractErrorMessage } from '../../utils/errorMessage';

const firstMsg = (val) => (Array.isArray(val) ? val[0] : val);

const EditInvoicePage = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const { toast } = useToast();
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState('');
    const [saving, setSaving] = useState(false);
    const [invoice, setInvoice] = useState(null);
    const [preview, setPreview] = useState(null);

    const [formData, setFormData] = useState({
        customer_id: '',
        payment_type: 'after_delivery',
        advance_amount: '',
        payment_due_date: '',
        items: [],
    });
    // The advance amount as originally loaded — used to detect whether the
    // user is actually changing it, since a fresh method split is only
    // required (and only sent) when the advance amount is being set to a
    // new value, never silently reused from the old one.
    const [originalAdvance, setOriginalAdvance] = useState({ payment_type: 'after_delivery', advance_amount: '' });
    const [methodAllocations, setMethodAllocations] = useState([]);

    const [generalError, setGeneralError] = useState('');
    const [fieldErrors, setFieldErrors] = useState({});
    const [itemErrors, setItemErrors] = useState([]);

    useEffect(() => {
        loadData();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [id]);

    const loadData = async () => {
        setLoading(true);
        setLoadError('');
        try {
            const invoiceData = await billingApi.invoices.getById(id);
            setInvoice(invoiceData);

            // Populate form data
            setFormData({
                customer_id: invoiceData.customer?.id || '',
                payment_type: invoiceData.payment_type || 'after_delivery',
                advance_amount: invoiceData.advance_amount || '',
                payment_due_date: invoiceData.payment_due_date || '',
                items: invoiceData.items?.map(item => ({
                    product_id: item.product,
                    product_label: item.product_code ? `${item.product_code} - ${item.product_name}` : item.product_name,
                    quantity: item.quantity,
                    discount: item.discount || 0,
                    gst: item.gst || 0,
                    wht: item.wht || 0,
                    selling_price: item.selling_price || 0,
                    _key: `existing-${item.id}`,
                })) || [],
            });
            setOriginalAdvance({
                payment_type: invoiceData.payment_type || 'after_delivery',
                advance_amount: invoiceData.advance_amount || '',
            });

            // Set preview if available
            if (invoiceData.draft_preview) {
                setPreview(invoiceData.draft_preview);
            }
        } catch (error) {
            setLoadError(extractErrorMessage(error, 'Failed to load invoice.'));
        } finally {
            setLoading(false);
        }
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

            if (data.quantity) {
                nextGeneralError = nextGeneralError || firstMsg(data.quantity);
            }
            if (data.status) {
                nextGeneralError = nextGeneralError || firstMsg(data.status);
            }
        }

        if (!nextGeneralError && !Object.keys(nextFieldErrors).length) {
            nextGeneralError = extractErrorMessage(error, 'Failed to update invoice.');
        }

        setFieldErrors(nextFieldErrors);
        setItemErrors(nextItemErrors);
        setGeneralError(nextGeneralError);
        toast.error(nextGeneralError || 'Failed to update invoice.');
    };

    const isAdvance = formData.payment_type === 'advance';
    const advanceAmountValue = parseFloat(formData.advance_amount) || 0;
    // The backend never silently reuses the old split — a fresh method pick
    // is required whenever the advance amount is being set to a new value,
    // including switching payment_type to advance for the first time.
    const advanceChanged = isAdvance && (
        originalAdvance.payment_type !== 'advance' ||
        String(formData.advance_amount) !== String(originalAdvance.advance_amount)
    );

    const handleSubmit = async (e) => {
        e.preventDefault();
        setGeneralError('');
        setFieldErrors({});
        setItemErrors([]);

        if (advanceChanged && !isSplitBalanced(advanceAmountValue, methodAllocations)) {
            setGeneralError('Payment method split must add up to the full advance amount.');
            return;
        }

        setSaving(true);
        try {
            const data = {
                payment_type: formData.payment_type,
                advance_amount: isAdvance ? advanceAmountValue : 0,
                ...(advanceChanged ? { method_allocations: methodAllocations } : {}),
                payment_due_date: formData.payment_due_date || undefined,
                items: formData.items.map(item => ({
                    product_id: parseInt(item.product_id),
                    quantity: parseInt(item.quantity) || 0,
                    discount: parseFloat(item.discount) || 0,
                    gst: parseFloat(item.gst) || 0,
                    wht: parseFloat(item.wht) || 0,
                })),
            };
            await billingApi.invoices.update(id, data);
            toast.success('Draft invoice updated.');
            navigate(`/billing/invoices/${id}`);
        } catch (error) {
            applyServerErrors(error);
        } finally {
            setSaving(false);
        }
    };

    const handleCancel = () => {
        navigate(`/billing/invoices/${id}`);
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    if (loadError) {
        return (
            <div className="space-y-4">
                <InlineAlert variant="error" message={loadError} onRetry={loadData} />
                <Button onClick={() => navigate('/billing/invoices')}>Back to Invoices</Button>
            </div>
        );
    }

    if (!invoice || invoice.status !== 'draft') {
        return (
            <EmptyState
                title="Invoice Not Editable"
                description="Only draft invoices can be edited."
                icon={<FileWarning className="w-8 h-8 text-neutral-400" />}
            >
                <Button onClick={() => navigate('/billing/invoices')} className="mt-4">
                    Back to Invoices
                </Button>
            </EmptyState>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <BackLink to={`/billing/invoices/${id}`}>Back to Invoice</BackLink>
                    <h1 className="text-3xl font-bold text-neutral-900 mt-2">Edit Invoice</h1>
                    <p className="text-neutral-500">{invoice.bill_number}</p>
                </div>
                <div className="flex gap-3">
                    <Button variant="secondary" onClick={handleCancel}>
                        Cancel
                    </Button>
                    <Button
                        onClick={handleSubmit}
                        loading={saving}
                        disabled={advanceChanged && !isSplitBalanced(advanceAmountValue, methodAllocations)}
                    >
                        Update Draft
                    </Button>
                </div>
            </div>

            {generalError && (
                <InlineAlert variant="error" message={generalError} />
            )}

            <form onSubmit={handleSubmit} className="space-y-6">
                <Card className="p-6" hover={false}>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <SearchableSelect
                            label="Customer"
                            value={formData.customer_id}
                            onChange={() => {}}
                            options={invoice.customer ? [{
                                value: invoice.customer.id,
                                label: invoice.customer.code ? `${invoice.customer.code} - ${invoice.customer.name}` : invoice.customer.name,
                            }] : []}
                            disabled={true}
                            required
                        />

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
                            {advanceChanged ? (
                                <>
                                    <p className="text-sm font-medium text-neutral-700 mb-2">Advance Payment Method</p>
                                    <p className="text-xs text-neutral-500 mb-2">
                                        The advance amount changed — pick how the new amount was received.
                                    </p>
                                    <MethodSplitPicker
                                        totalAmount={advanceAmountValue}
                                        value={methodAllocations}
                                        onChange={setMethodAllocations}
                                        error={fieldErrors.method_allocations}
                                    />
                                </>
                            ) : (
                                <p className="text-xs text-neutral-500">
                                    Advance amount unchanged — keeping the existing payment method split.
                                </p>
                            )}
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

                    <div className="space-y-3 max-h-[600px] overflow-y-auto pr-1">
                        {formData.items.length === 0 ? (
                            <EmptyState
                                title="No items added yet"
                                description='Click "Add Item" to start.'
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
                </Card>

                {formData.items.length > 0 && preview && (
                    <DraftPreviewPanel preview={preview} />
                )}
            </form>
        </div>
    );
};

export default EditInvoicePage;
