import { useState } from 'react';
import Select from '../ui/Select';
import SearchableSelect from '../ui/SearchableSelect';
import Input from '../ui/Input';
import Button from '../ui/Button';
import { useToast } from '../../context/ToastContext';
import { extractErrorMessage } from '../../utils/errorMessage';

/**
 * Reusable multi-shelf allocation row editor.
 *
 * mode='consumption' -> stock is LEAVING (sale, purchase return, lost inventory). The
 *                        candidate shelf set is already small (only shelves currently
 *                        holding this product), so it's a plain dropdown — pass the
 *                        prefetched candidate list via `shelves`.
 * mode='putaway'      -> stock is ARRIVING (purchase receiving, invoice-return
 *                        acceptance, mark-as-found). Any shelf is valid, and a large
 *                        factory can have hundreds of them, so this is a backend-driven
 *                        search bar instead — pass an `onSearchShelves(query)` function.
 *
 * value: [{ shelf_id, quantity, shelf_name? }] — shelf_name is carried along purely for
 *        display in putaway mode (SearchableSelect needs a label for a value that isn't
 *        in its current search results), not sent to the backend.
 * onChange(nextValue)
 * shelves: [{ id, name, available_quantity? }] — consumption mode only, the prefetched candidate list.
 * onSearchShelves(query): async (query) => [{ value, label, name?, available_quantity? }] — putaway mode only.
 * requiredQuantity: the number `value`'s quantities must sum to exactly.
 * productId: consumption mode only, needed to call `autoAllocateApi`.
 * autoAllocateApi: consumption mode only — async (productId, quantity, excludeShelfIds) =>
 *        { allocations: [{ shelf_id, shelf_name, quantity }], shortfall } — parent-injected
 *        network call (same precedent as `onSearchShelves`), one of
 *        `purchasesApi.shelves.autoAllocate` / `billingApi.shelves.autoAllocate` depending on
 *        which app's endpoint the page belongs to. When omitted, no Auto-Allocate button is shown.
 */
const ShelfAllocationEditor = ({
    value = [],
    onChange,
    shelves = [],
    onSearchShelves,
    requiredQuantity = 0,
    mode = 'putaway',
    disabled = false,
    productId,
    autoAllocateApi,
}) => {
    const { toast } = useToast();
    const [autoAllocating, setAutoAllocating] = useState(false);
    const [autoAllocateShortfall, setAutoAllocateShortfall] = useState(0);
    const allocations = value;
    const allocatedTotal = allocations.reduce((sum, a) => sum + (parseInt(a.quantity, 10) || 0), 0);
    const remaining = requiredQuantity - allocatedTotal;
    const usedShelfIds = new Set(allocations.map((a) => String(a.shelf_id)).filter(Boolean));

    const handleAddRow = () => {
        onChange([...allocations, { shelf_id: '', quantity: remaining > 0 ? remaining : '', shelf_name: '' }]);
    };

    const handleUpdateRow = (index, patch) => {
        onChange(allocations.map((a, i) => (i === index ? { ...a, ...patch } : a)));
    };

    const handleRemoveRow = (index) => {
        onChange(allocations.filter((_, i) => i !== index));
    };

    // Fills the remaining gap from OTHER shelves — never touches rows the
    // user already has. Existing rows are excluded from the candidate set
    // the backend picks from, and the response is appended, not merged.
    const handleAutoAllocate = async () => {
        if (remaining <= 0 || !autoAllocateApi) return;
        setAutoAllocating(true);
        setAutoAllocateShortfall(0);
        try {
            const excludeShelfIds = allocations.map((a) => a.shelf_id).filter(Boolean);
            const data = await autoAllocateApi(productId, remaining, excludeShelfIds);
            const newRows = (data?.allocations || []).map((a) => ({
                shelf_id: a.shelf_id,
                quantity: a.quantity,
                shelf_name: a.shelf_name || '',
            }));
            // Read `allocations` fresh via onChange's functional-update-like
            // pattern isn't available here (onChange takes a value, not an
            // updater), so this still appends to the value captured at
            // click-time — safe because the whole row set is disabled below
            // while a request is in flight, so nothing else can change it
            // out from under this response.
            if (newRows.length > 0) {
                onChange([...allocations, ...newRows]);
            }
            if (data?.shortfall > 0) {
                setAutoAllocateShortfall(data.shortfall);
            }
        } catch (error) {
            toast.error(extractErrorMessage(error, 'Failed to auto-allocate shelves'));
        } finally {
            setAutoAllocating(false);
        }
    };

    // A shelf already picked on another row of this same allocation can't
    // be picked again (the unique_together constraint on the backend would
    // reject it anyway) — filtered out per row, whichever mode is active.
    const usedElsewhere = (index) =>
        new Set(
            allocations
                .filter((_, i) => i !== index)
                .map((a) => String(a.shelf_id))
                .filter(Boolean)
        );

    const dropdownOptions = (index) =>
        shelves
            .filter((s) => String(s.id) === String(allocations[index].shelf_id) || !usedElsewhere(index).has(String(s.id)))
            .map((s) => ({
                value: s.id,
                label: s.available_quantity != null ? `${s.name} (${s.available_quantity} available)` : s.name,
            }));

    const searchForRow = (index) => async (query) => {
        const results = await onSearchShelves(query);
        const exclude = usedElsewhere(index);
        return (results || []).filter((r) => !exclude.has(String(r.value)));
    };

    const allRowsUsed = mode === 'consumption' && shelves.length > 0 && usedShelfIds.size >= shelves.length;

    return (
        <div className="space-y-2">
            {allocations.map((a, index) => (
                <div key={index} className="flex items-start gap-2">
                    <div className="flex-1">
                        {mode === 'consumption' ? (
                            <Select
                                value={a.shelf_id}
                                onChange={(e) => handleUpdateRow(index, { shelf_id: e.target.value })}
                                options={dropdownOptions(index)}
                                placeholder="Select shelf"
                                disabled={disabled || autoAllocating}
                            />
                        ) : (
                            <SearchableSelect
                                value={a.shelf_id}
                                selectedLabel={a.shelf_name}
                                onChange={(val, option) =>
                                    handleUpdateRow(index, { shelf_id: val, shelf_name: option?.name || option?.label || '' })
                                }
                                onSearch={searchForRow(index)}
                                placeholder="Search shelf by name..."
                                disabled={disabled || autoAllocating}
                            />
                        )}
                    </div>
                    <div className="w-28 shrink-0">
                        <Input
                            type="number"
                            min="1"
                            value={a.quantity}
                            onChange={(e) => handleUpdateRow(index, { quantity: e.target.value })}
                            placeholder="Qty"
                            disabled={disabled || autoAllocating}
                        />
                    </div>
                    <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        onClick={() => handleRemoveRow(index)}
                        disabled={disabled || autoAllocating}
                    >
                        Remove
                    </Button>
                </div>
            ))}

            <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                    <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        onClick={handleAddRow}
                        disabled={disabled || autoAllocating || allRowsUsed}
                    >
                        + Add Shelf
                    </Button>
                    {mode === 'consumption' && autoAllocateApi && (
                        <Button
                            type="button"
                            variant="secondary"
                            size="sm"
                            onClick={handleAutoAllocate}
                            disabled={disabled || remaining <= 0}
                            loading={autoAllocating}
                        >
                            Auto-Allocate
                        </Button>
                    )}
                </div>
                <span
                    className={`text-sm font-medium ${
                        remaining === 0
                            ? 'text-green-600'
                            : remaining < 0
                                ? 'text-red-600'
                                : 'text-amber-600'
                    }`}
                >
                    {remaining === 0
                        ? `Fully allocated (${allocatedTotal}/${requiredQuantity})`
                        : remaining > 0
                            ? `${remaining} of ${requiredQuantity} remaining to allocate`
                            : `Over-allocated by ${-remaining}`}
                </span>
            </div>

            {mode === 'consumption' && shelves.length === 0 && (
                <p className="text-sm text-red-600">
                    No shelf currently holds stock of this product — nothing can be allocated.
                </p>
            )}

            {autoAllocateShortfall > 0 && (
                <p className="text-sm text-amber-600">
                    Auto-allocate could only cover {allocatedTotal} of {requiredQuantity} — {autoAllocateShortfall} short of total stock across all shelves. Add more manually if more becomes available.
                </p>
            )}
        </div>
    );
};

export default ShelfAllocationEditor;
