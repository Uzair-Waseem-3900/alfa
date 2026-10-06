import { useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { Plus, Send, Trash2 } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { useProviders, usePurchaseRequestActions } from '../../hooks/useB2B';
import { b2bApi } from '../../services/b2bApi';
import { purchasesApi } from '../../services/purchasesApi';
import { extractErrorMessage } from '../../utils/errorMessage';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';
import BackLink from '../../components/ui/BackLink';
import Input from '../../components/ui/Input';
import Tabs from '../../components/ui/Tabs';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import EmptyState from '../../components/ui/EmptyState';
import InlineAlert from '../../components/ui/InlineAlert';
import SearchableSelect from '../../components/ui/SearchableSelect';
import ShelfAllocationEditor from '../../components/shared/ShelfAllocationEditor';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const sumQuantities = (rows) => rows.reduce((sum, r) => sum + (parseInt(r.quantity, 10) || 0), 0);

// Estimated line total, same formula invoices use: (price - discount) x qty, + GST, - WHT.
// Only shown when the partner shares its rates with us.
const estimateTotal = (line) => {
    if (line.price == null) return null;
    const qty = parseInt(line.quantity, 10) || 0;
    const effective = (parseFloat(line.price) || 0) - (parseFloat(line.discount) || 0);
    const gross = qty * effective;
    return gross + gross * ((parseFloat(line.gst) || 0) / 100) - gross * ((parseFloat(line.wht) || 0) / 100);
};

// Messages from a failed create (the backend lists every problem at once).
const createErrorMessages = (error) => {
    const items = error?.response?.data?.items;
    if (Array.isArray(items)) return items.map(String);
    if (typeof items === 'string') return [items];
    return [extractErrorMessage(error, 'Failed to send the request')];
};

const CreatePurchaseRequestPage = () => {
    const { user } = useAuth();
    const { toast } = useToast();
    const navigate = useNavigate();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const { providers, initialLoading: providersLoading, error: providersError, refetch: refetchProviders } = useProviders();
    const { create, mutating } = usePurchaseRequestActions();

    const [selected, setSelected] = useState('');
    const provider = selected || providers[0]?.key || '';
    const [lines, setLines] = useState([]);
    const [note, setNote] = useState('');
    const [errors, setErrors] = useState([]);
    // Chosen once when the form opens: a double-click or a retried send can then never create a second request.
    const [requestUuid] = useState(() => crypto.randomUUID());

    if (!isAdmin) {
        return <Navigate to="/dashboard" replace />;
    }

    // Live search in the PARTNER's priced catalog. Never returns a stock figure.
    const searchProducts = async (query) => {
        try {
            const data = await b2bApi.providers.searchProducts(provider, { search: query, page_size: 25 });
            return (data?.results || []).map((row) => ({
                value: row.code,
                label: `${row.code} - ${row.name}${row.in_catalog ? '' : '  (not in your catalog)'}`,
                ...row,
            }));
        } catch (error) {
            toast.error(extractErrorMessage(error, 'Could not search the partner right now'));
            return [];
        }
    };

    const searchShelves = async (query) => {
        const res = await purchasesApi.shelves.getAll({ search: query, page_size: 25 });
        const results = res?.results ?? res ?? [];
        return results.map((s) => ({ value: s.id, label: s.name, name: s.name }));
    };

    const addProduct = (_value, option) => {
        if (!option) return;
        if (!option.in_catalog) {
            toast.error(`"${option.name}" is not in your catalog with the same code and name, so it can't be requested.`);
            return;
        }
        if (lines.some((l) => l.product_id === option.local_product_id)) {
            toast.info('That product is already in the request.');
            return;
        }
        setErrors([]);
        setLines((prev) => [...prev, {
            key: option.code,
            product_id: option.local_product_id,
            code: option.code,
            name: option.name,
            price: option.selling_price ?? null,
            quantity: '1',
            discount: '0',
            gst: '0',
            wht: '0',
            allocations: [],
        }]);
    };

    const updateLine = (key, patch) => {
        setErrors([]);
        setLines((prev) => prev.map((l) => (l.key === key ? { ...l, ...patch } : l)));
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        const problems = [];
        if (lines.length === 0) problems.push('Add at least one product.');
        lines.forEach((l) => {
            const qty = parseInt(l.quantity, 10) || 0;
            if (qty < 1) problems.push(`${l.name} (${l.code}): enter a quantity of at least 1.`);
            else if (sumQuantities(l.allocations) !== qty) problems.push(`${l.name} (${l.code}): the shelves must add up to ${qty}.`);
        });
        if (problems.length) {
            setErrors(problems);
            return;
        }
        try {
            const result = await create({
                provider,
                request_uuid: requestUuid,
                note,
                items: lines.map((l) => ({
                    product_id: l.product_id,
                    quantity: parseInt(l.quantity, 10),
                    discount: l.discount === '' ? '0' : l.discount,
                    gst: l.gst === '' ? '0' : l.gst,
                    wht: l.wht === '' ? '0' : l.wht,
                    shelf_allocations: l.allocations
                        .filter((a) => a.shelf_id && a.quantity)
                        .map((a) => ({ shelf_id: parseInt(a.shelf_id, 10), quantity: parseInt(a.quantity, 10) })),
                })),
            });
            if (result?.notice) toast.warning(result.notice);
            else toast.success('Request sent');
            navigate(`/b2b/purchase-requests/${result.id}`);
        } catch (error) {
            setErrors(createErrorMessages(error));
        }
    };

    if (providersLoading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div>
                <BackLink to="/b2b/purchase-requests">Back to Purchase Requests</BackLink>
                <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900 mt-1">Create Purchase Request</h1>
                <p className="text-neutral-500 mt-1">
                    Pick products from the partner's priced catalog, choose quantities and the shelf each item goes to.
                    You'll only see stock the partner chooses to show: quantities are never shared.
                </p>
            </div>

            {providersError ? (
                <InlineAlert variant="error" title="Couldn't load partners" message={providersError} onRetry={refetchProviders} />
            ) : providers.length === 0 ? (
                <EmptyState title="No Partner Connected" description="No partner software is configured for this installation yet." />
            ) : (
                <form onSubmit={handleSubmit} className="space-y-6">
                    {providers.length > 1 && (
                        <Tabs
                            tabs={providers.map((p) => ({ value: p.key, label: p.key }))}
                            activeTab={provider}
                            onChange={(key) => { setSelected(key); setLines([]); setErrors([]); }}
                            className="overflow-x-auto"
                        />
                    )}

                    <Card className="p-6" hover={false}>
                        <h3 className="font-semibold text-neutral-900 mb-1">Products from {provider}</h3>
                        <p className="text-sm text-neutral-500 mb-4">
                            Search by name or code. Rates are shown only if {provider} shares its rate list with you.
                        </p>
                        <SearchableSelect
                            value=""
                            onChange={addProduct}
                            onSearch={searchProducts}
                            placeholder="Search the partner's products..."
                            disabled={mutating}
                        />
                    </Card>

                    {errors.length > 0 && (
                        <InlineAlert variant="error" title="The request can't be sent yet" message={errors.join('\n')} />
                    )}

                    {lines.length === 0 ? (
                        <EmptyState title="No Products Yet" description="Search above and select a product to add it to the request." />
                    ) : (
                        <div className="space-y-4">
                            {lines.map((line) => {
                                const qty = parseInt(line.quantity, 10) || 0;
                                const total = estimateTotal(line);
                                return (
                                    <Card key={line.key} className="p-5" hover={false}>
                                        <div className="flex items-start justify-between gap-3">
                                            <div>
                                                <p className="font-semibold text-neutral-900">
                                                    {line.name} <span className="text-neutral-400 text-sm font-normal">({line.code})</span>
                                                </p>
                                                <p className="text-sm text-neutral-600 mt-0.5">
                                                    Rate:{' '}
                                                    {line.price == null
                                                        ? <span className="text-neutral-500">Not allowed</span>
                                                        : <b>Rs. {fmt(line.price)}</b>}
                                                    {total != null && qty > 0 && <span className="ml-3">Estimated total: <b>Rs. {fmt(total)}</b></span>}
                                                </p>
                                            </div>
                                            <button
                                                type="button"
                                                onClick={() => setLines((prev) => prev.filter((l) => l.key !== line.key))}
                                                className="inline-flex items-center justify-center w-9 h-9 rounded-lg text-error-600 hover:bg-error-50 transition-colors"
                                                aria-label={`Remove ${line.name}`}
                                            >
                                                <Trash2 className="w-4 h-4" />
                                            </button>
                                        </div>

                                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
                                            <Input
                                                label="Quantity"
                                                type="number"
                                                min="1"
                                                value={line.quantity}
                                                onChange={(e) => updateLine(line.key, { quantity: e.target.value })}
                                            />
                                            <Input
                                                label="Discount (per unit)"
                                                type="number"
                                                step="any"
                                                value={line.discount}
                                                onChange={(e) => updateLine(line.key, { discount: e.target.value })}
                                            />
                                            <Input
                                                label="GST %"
                                                type="number"
                                                step="any"
                                                min="0"
                                                max="100"
                                                value={line.gst}
                                                onChange={(e) => updateLine(line.key, { gst: e.target.value })}
                                            />
                                            <Input
                                                label="WHT %"
                                                type="number"
                                                step="any"
                                                min="0"
                                                max="100"
                                                value={line.wht}
                                                onChange={(e) => updateLine(line.key, { wht: e.target.value })}
                                            />
                                        </div>
                                        <p className="text-xs text-neutral-400 mt-1">A negative discount is a surcharge.</p>

                                        <div className="mt-4">
                                            <p className="text-sm font-medium text-neutral-700 mb-2">Shelf these items will be put on (kept private, never sent)</p>
                                            <ShelfAllocationEditor
                                                mode="putaway"
                                                value={line.allocations}
                                                onChange={(next) => updateLine(line.key, { allocations: next })}
                                                onSearchShelves={searchShelves}
                                                requiredQuantity={qty}
                                                disabled={mutating}
                                            />
                                        </div>
                                    </Card>
                                );
                            })}
                        </div>
                    )}

                    <Card className="p-6" hover={false}>
                        <Input
                            label="Note (optional)"
                            value={note}
                            onChange={(e) => setNote(e.target.value)}
                            maxLength={500}
                            placeholder="Anything the partner should know"
                        />
                        <div className="flex justify-end gap-3 mt-5">
                            <Button type="button" variant="secondary" onClick={() => navigate('/b2b/purchase-requests')} disabled={mutating}>
                                Cancel
                            </Button>
                            <Button type="submit" icon={lines.length ? Send : Plus} loading={mutating} disabled={lines.length === 0}>
                                Send Request
                            </Button>
                        </div>
                    </Card>
                </form>
            )}
        </div>
    );
};

export default CreatePurchaseRequestPage;
