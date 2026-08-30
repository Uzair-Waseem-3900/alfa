import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
    ShieldAlert, FileQuestion, ScrollText, Info, AlertTriangle,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { assetsApi } from '../../services/assetsApi';
import { useAssetValuationEntries, useAssetStats } from '../../hooks/useAssets';
import { extractErrorMessage } from '../../utils/errorMessage';
import { todayLocalDate } from '../../utils/helpers';
import MethodSplitPicker, { isSplitBalanced } from '../../components/paymentMethods/MethodSplitPicker';
import BackLink from '../../components/ui/BackLink';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';
import Modal from '../../components/ui/Modal';
import Input from '../../components/ui/Input';
import Select from '../../components/ui/Select';
import Badge from '../../components/ui/Badge';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Table from '../../components/ui/Table';
import Pagination from '../../components/ui/Pagination';
import InlineAlert from '../../components/ui/InlineAlert';
import EmptyState from '../../components/ui/EmptyState';
import ConfirmDialog from '../../components/ui/ConfirmDialog';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const emptyDisposeFieldErrors = { disposal_type: '', disposal_date: '', sale_amount: '', reason: '' };

const AssetDetailPage = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const [asset, setAsset] = useState(null);
    const [loading, setLoading] = useState(true);
    const [notFound, setNotFound] = useState(false);
    const [fetchError, setFetchError] = useState('');

    const {
        data: entries, meta, page, setPage, loading: entriesLoading, error: entriesError,
        refetch: refetchEntries,
    } = useAssetValuationEntries({ asset_id: id });
    const { refetch: refetchStats } = useAssetStats();

    const [showRevalueModal, setShowRevalueModal] = useState(false);
    const [revalueForm, setRevalueForm] = useState({
        new_worth: '', revaluation_date: todayLocalDate(), note: '',
    });
    const [revalueLoading, setRevalueLoading] = useState(false);
    const [revalueError, setRevalueError] = useState('');
    const [revalueFieldError, setRevalueFieldError] = useState('');

    const [showDisposeModal, setShowDisposeModal] = useState(false);
    const [disposeForm, setDisposeForm] = useState({
        disposal_type: 'scrapped', disposal_date: todayLocalDate(),
        sale_amount: '', reason: '',
    });
    const [disposeLoading, setDisposeLoading] = useState(false);
    const [disposeError, setDisposeError] = useState('');
    const [disposeFieldErrors, setDisposeFieldErrors] = useState(emptyDisposeFieldErrors);
    const [disposeMethodAllocations, setDisposeMethodAllocations] = useState([]);
    const [disposeSplitError, setDisposeSplitError] = useState('');
    // Disposal is irreversible, so the form modal only stages the payload —
    // the actual API call only fires after the user confirms in the
    // dedicated ConfirmDialog gate below.
    const [showDisposeConfirm, setShowDisposeConfirm] = useState(false);
    const [pendingDisposePayload, setPendingDisposePayload] = useState(null);

    useEffect(() => {
        fetchAsset();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [id]);

    const fetchAsset = async () => {
        setLoading(true);
        setFetchError('');
        setNotFound(false);
        try {
            const data = await assetsApi.items.getById(id);
            setAsset(data);
        } catch (error) {
            console.error('Failed to fetch asset:', error);
            setAsset(null);
            if (error.response?.status === 404) {
                setNotFound(true);
            } else {
                setFetchError(extractErrorMessage(error, 'Failed to load asset'));
            }
        } finally {
            setLoading(false);
        }
    };

    const handleRevalue = async (e) => {
        e.preventDefault();
        setRevalueError('');
        setRevalueFieldError('');
        setRevalueLoading(true);
        try {
            await assetsApi.items.revalue(id, { ...revalueForm, new_worth: parseFloat(revalueForm.new_worth) });
            setShowRevalueModal(false);
            setRevalueForm({ new_worth: '', revaluation_date: todayLocalDate(), note: '' });
            toast.success('Asset revalued successfully');
            await Promise.all([fetchAsset(), refetchEntries(), refetchStats()]);
        } catch (error) {
            const data = error.response?.data;
            const nwError = Array.isArray(data?.new_worth) ? data.new_worth[0] : data?.new_worth;
            if (nwError) {
                setRevalueFieldError(nwError);
            } else {
                setRevalueError(extractErrorMessage(error, 'Failed to revalue asset'));
            }
        } finally {
            setRevalueLoading(false);
        }
    };

    // Step 1: stage the dispose payload and hand off to the ConfirmDialog —
    // no API call happens here since this is an irreversible action.
    const handleDisposeFormSubmit = (e) => {
        e.preventDefault();
        const payload = { ...disposeForm };
        if (payload.disposal_type === 'scrapped') {
            delete payload.sale_amount;
        } else {
            payload.sale_amount = parseFloat(payload.sale_amount);
            // Only a "sold" disposal moves cash — "scrapped" never sends
            // method_allocations at all.
            payload.method_allocations = disposeMethodAllocations;
        }
        setDisposeError('');
        setDisposeFieldErrors(emptyDisposeFieldErrors);
        setDisposeSplitError('');
        setPendingDisposePayload(payload);
        setShowDisposeModal(false);
        setShowDisposeConfirm(true);
    };

    // Step 2: user confirmed in the dialog — now actually call the API.
    const confirmDispose = async () => {
        if (!pendingDisposePayload) return;
        setDisposeLoading(true);
        try {
            await assetsApi.items.dispose(id, pendingDisposePayload);
            setShowDisposeConfirm(false);
            setPendingDisposePayload(null);
            toast.success('Asset disposed successfully');
            await Promise.all([fetchAsset(), refetchStats()]);
        } catch (error) {
            // Reopen the form with the error surfaced so the admin can adjust
            // and retry, instead of losing their input.
            setShowDisposeConfirm(false);
            setShowDisposeModal(true);
            const data = error.response?.data;
            const saleError = Array.isArray(data?.sale_amount) ? data.sale_amount[0] : data?.sale_amount;
            const typeError = Array.isArray(data?.disposal_type) ? data.disposal_type[0] : data?.disposal_type;
            const methodError = data?.method_allocations || data?.splits;
            if (saleError || typeError) {
                setDisposeFieldErrors({ ...emptyDisposeFieldErrors, sale_amount: saleError || '', disposal_type: typeError || '' });
            }
            if (methodError) {
                setDisposeSplitError(Array.isArray(methodError) ? methodError[0] : methodError);
            }
            if (!saleError && !typeError && !methodError) {
                setDisposeError(extractErrorMessage(error, 'Failed to dispose asset'));
            }
        } finally {
            setDisposeLoading(false);
        }
    };

    const columns = [
        { key: 'period', label: 'Period' },
        {
            key: 'entry_type',
            label: 'Type',
            render: (v) => v === 'depreciation'
                ? <Badge variant="warning" size="sm">Depreciation</Badge>
                : <Badge variant="info" size="sm">Revaluation</Badge>,
        },
        { key: 'rate_applied', label: 'Rate', render: (v) => v ? `${(parseFloat(v) * 100).toFixed(2)}%` : <span className="text-neutral-300">—</span> },
        { key: 'worth_before', label: 'Worth Before', render: (v) => `Rs. ${fmt(v)}` },
        {
            key: 'amount',
            label: 'Change',
            render: (v) => (
                <span className={parseFloat(v) < 0 ? 'text-error-600 font-semibold' : 'text-success-600 font-semibold'}>
                    {parseFloat(v) >= 0 ? '+' : ''}Rs. {fmt(v)}
                </span>
            ),
        },
        { key: 'worth_after', label: 'Worth After', render: (v) => <span className="font-semibold">Rs. {fmt(v)}</span> },
        { key: 'note', label: 'Note', render: (v) => v || <span className="text-neutral-300">—</span> },
    ];

    if (!isAdmin) {
        return (
            <div className="text-center py-16">
                <div className="w-16 h-16 rounded-full bg-error-50 flex items-center justify-center mx-auto mb-4">
                    <ShieldAlert className="w-8 h-8 text-error-500" />
                </div>
                <h2 className="text-2xl font-semibold text-neutral-900">Access Denied</h2>
                <p className="text-neutral-500 mt-2">Only admins or superusers can view assets.</p>
            </div>
        );
    }

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    if (notFound) {
        return (
            <div className="text-center py-16">
                <div className="w-16 h-16 rounded-full bg-neutral-100 flex items-center justify-center mx-auto mb-4">
                    <FileQuestion className="w-8 h-8 text-neutral-400" />
                </div>
                <h2 className="text-2xl font-semibold text-neutral-900">Asset Not Found</h2>
                <p className="text-neutral-500 mt-2">It may have been removed, or the link is incorrect.</p>
                <BackLink to="/assets/items" className="mt-4 inline-flex">Back to Assets</BackLink>
            </div>
        );
    }

    if (fetchError || !asset) {
        return (
            <div className="space-y-4">
                <BackLink to="/assets/items">Back to Assets</BackLink>
                <InlineAlert variant="error" message={fetchError || 'Failed to load asset'} onRetry={fetchAsset} />
            </div>
        );
    }

    const isRevaluationCategory = asset.valuation_method === 'revaluation';
    const accumulatedChange = parseFloat(asset.cost) - parseFloat(asset.current_worth);

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                <div>
                    <BackLink to="/assets/items">Back to Assets</BackLink>
                    <div className="flex items-center gap-3 mt-2">
                        <h1 className="text-3xl font-bold text-neutral-900">{asset.name}</h1>
                        {asset.is_disposed
                            ? <Badge variant="error">Disposed</Badge>
                            : <Badge variant="success">Active</Badge>}
                    </div>
                    <p className="text-neutral-500 mt-1">{asset.category_name} &middot; {asset.acquisition_type === 'new' ? 'New purchase' : 'Existing asset'}</p>
                </div>
                {!asset.is_disposed && (
                    <div className="flex gap-2">
                        {isRevaluationCategory && (
                            <Button variant="secondary" onClick={() => { setRevalueError(''); setRevalueFieldError(''); setShowRevalueModal(true); }}>
                                Revalue
                            </Button>
                        )}
                        <Button
                            variant="danger"
                            onClick={() => {
                                setDisposeError('');
                                setDisposeFieldErrors(emptyDisposeFieldErrors);
                                setDisposeMethodAllocations([]);
                                setDisposeSplitError('');
                                setShowDisposeModal(true);
                            }}
                        >
                            Dispose
                        </Button>
                    </div>
                )}
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <Card className="p-4">
                    <p className="text-xs text-neutral-500 mb-1">Cost</p>
                    <p className="text-xl font-bold text-info-600">Rs. {fmt(asset.cost)}</p>
                </Card>
                <Card className="p-4">
                    <p className="text-xs text-neutral-500 mb-1">Current Worth</p>
                    <p className="text-xl font-bold text-purple-600">Rs. {fmt(asset.current_worth)}</p>
                </Card>
                {!isRevaluationCategory && (
                    <Card className="p-4">
                        <p className="text-xs text-neutral-500 mb-1">Accumulated Depreciation</p>
                        <p className="text-xl font-bold text-orange-600">Rs. {fmt(accumulatedChange)}</p>
                    </Card>
                )}
                <Card className="p-4">
                    <p className="text-xs text-neutral-500 mb-1">Acquisition Date</p>
                    <p className="text-xl font-bold text-neutral-900">{new Date(asset.acquisition_date).toLocaleDateString()}</p>
                </Card>
            </div>

            {asset.note && (
                <Card className="p-4">
                    <p className="text-sm text-neutral-500">Note</p>
                    <p className="font-medium">{asset.note}</p>
                </Card>
            )}

            <div className="space-y-4">
                <h2 className="text-lg font-semibold text-neutral-900">Valuation History</h2>
                {entriesError && (
                    <InlineAlert variant="error" message={entriesError} onRetry={refetchEntries} />
                )}
                {entriesLoading ? (
                    <div className="flex items-center justify-center py-8">
                        <LoadingSpinner size="lg" />
                    </div>
                ) : entries.length === 0 ? (
                    <EmptyState
                        icon={<ScrollText className="w-8 h-8 text-neutral-400" />}
                        title="No History Yet"
                        description={isRevaluationCategory ? 'Revalue this asset to create the first entry.' : 'Depreciation entries appear automatically as months pass.'}
                    />
                ) : (
                    <>
                        <Table columns={columns} data={entries} />
                        {meta.totalPages > 1 && (
                            <Pagination currentPage={meta.currentPage} totalPages={meta.totalPages} onPageChange={setPage} />
                        )}
                    </>
                )}
            </div>

            {/* Revalue Modal */}
            <Modal
                isOpen={showRevalueModal}
                onClose={() => setShowRevalueModal(false)}
                title="Revalue Asset"
                size="lg"
            >
                <form onSubmit={handleRevalue} className="space-y-4">
                    <p className="text-sm text-neutral-500">
                        Current worth: <strong>Rs. {fmt(asset.current_worth)}</strong>
                    </p>
                    <Input
                        label="New Worth (PKR)"
                        type="number"
                        step="0.01"
                        min="0"
                        value={revalueForm.new_worth}
                        onChange={(e) => setRevalueForm({ ...revalueForm, new_worth: e.target.value })}
                        error={revalueFieldError}
                        required
                    />
                    <Input
                        label="Revaluation Date"
                        type="date"
                        value={revalueForm.revaluation_date}
                        onChange={(e) => setRevalueForm({ ...revalueForm, revaluation_date: e.target.value })}
                        required
                    />
                    <Input
                        label="Note"
                        value={revalueForm.note}
                        onChange={(e) => setRevalueForm({ ...revalueForm, note: e.target.value })}
                        placeholder="e.g. 2026 market appraisal"
                    />
                    {revalueError && <InlineAlert variant="error" message={revalueError} />}
                    <div className="flex justify-end gap-3 pt-4">
                        <Button type="button" variant="secondary" onClick={() => setShowRevalueModal(false)}>
                            Cancel
                        </Button>
                        <Button type="submit" loading={revalueLoading}>
                            Revalue
                        </Button>
                    </div>
                </form>
            </Modal>

            {/* Dispose Modal — stages the payload; the real submit happens
                after confirmation in the ConfirmDialog below. */}
            <Modal
                isOpen={showDisposeModal}
                onClose={() => setShowDisposeModal(false)}
                title="Dispose Asset"
                size="lg"
            >
                <form onSubmit={handleDisposeFormSubmit} className="space-y-4">
                    <Select
                        label="Disposal Type"
                        value={disposeForm.disposal_type}
                        onChange={(e) => {
                            const value = e.target.value;
                            setDisposeForm({ ...disposeForm, disposal_type: value });
                            // Switching to "scrapped" drops any staged split — it's
                            // never sent then, since scrapping doesn't move cash.
                            if (value !== 'sold') {
                                setDisposeMethodAllocations([]);
                                setDisposeSplitError('');
                            }
                        }}
                        options={[
                            { value: 'scrapped', label: 'Scrapped — no longer usable, no cash involved' },
                            { value: 'sold', label: 'Sold — enter sale amount, cash in hand increases' },
                        ]}
                        error={disposeFieldErrors.disposal_type}
                        required
                    />
                    <Input
                        label="Disposal Date"
                        type="date"
                        value={disposeForm.disposal_date}
                        onChange={(e) => setDisposeForm({ ...disposeForm, disposal_date: e.target.value })}
                        required
                    />
                    {disposeForm.disposal_type === 'sold' && (
                        <Input
                            label="Sale Amount (PKR)"
                            type="number"
                            step="0.01"
                            min="0.01"
                            value={disposeForm.sale_amount}
                            onChange={(e) => setDisposeForm({ ...disposeForm, sale_amount: e.target.value })}
                            error={disposeFieldErrors.sale_amount}
                            required
                        />
                    )}
                    <Input
                        label="Reason"
                        value={disposeForm.reason}
                        onChange={(e) => setDisposeForm({ ...disposeForm, reason: e.target.value })}
                        placeholder={disposeForm.disposal_type === 'scrapped' ? 'e.g. damaged beyond repair' : 'e.g. upgraded to newer model'}
                    />

                    {disposeForm.disposal_type === 'sold' && disposeForm.sale_amount && (
                        <div className="flex items-start gap-2.5 p-3 bg-info-50 rounded-xl">
                            <Info className="w-4 h-4 text-info-600 flex-shrink-0 mt-0.5" />
                            <p className="text-sm text-info-700">
                                Cash in hand will increase by <strong>Rs. {fmt(disposeForm.sale_amount)}</strong>.
                                Gain/loss vs. current worth (Rs. {fmt(asset.current_worth)}) will be computed automatically:{' '}
                                <strong className={parseFloat(disposeForm.sale_amount) - parseFloat(asset.current_worth) >= 0 ? 'text-success-600' : 'text-error-600'}>
                                    Rs. {fmt(parseFloat(disposeForm.sale_amount || 0) - parseFloat(asset.current_worth))}
                                </strong>
                            </p>
                        </div>
                    )}
                    {disposeForm.disposal_type === 'scrapped' && (
                        <div className="flex items-start gap-2.5 p-3 bg-warning-50 rounded-xl">
                            <AlertTriangle className="w-4 h-4 text-warning-600 flex-shrink-0 mt-0.5" />
                            <p className="text-sm text-warning-700">No cash movement — this asset will simply be removed from active totals.</p>
                        </div>
                    )}

                    {disposeForm.disposal_type === 'sold' && (
                        <MethodSplitPicker
                            totalAmount={disposeForm.sale_amount}
                            value={disposeMethodAllocations}
                            onChange={setDisposeMethodAllocations}
                            error={disposeSplitError}
                        />
                    )}

                    {disposeError && <InlineAlert variant="error" message={disposeError} />}

                    <div className="flex justify-end gap-3 pt-4">
                        <Button type="button" variant="secondary" onClick={() => setShowDisposeModal(false)}>
                            Cancel
                        </Button>
                        <Button
                            type="submit"
                            variant="danger"
                            disabled={disposeForm.disposal_type === 'sold' && !isSplitBalanced(disposeForm.sale_amount, disposeMethodAllocations)}
                        >
                            Review &amp; Dispose
                        </Button>
                    </div>
                </form>
            </Modal>

            {/* Final irreversible-action gate */}
            <ConfirmDialog
                isOpen={showDisposeConfirm}
                onClose={() => { setShowDisposeConfirm(false); setShowDisposeModal(true); }}
                onConfirm={confirmDispose}
                title="Confirm Asset Disposal"
                message={
                    pendingDisposePayload
                        ? `Dispose "${asset.name}" as ${pendingDisposePayload.disposal_type}${pendingDisposePayload.disposal_type === 'sold' ? ` for Rs. ${fmt(pendingDisposePayload.sale_amount)}` : ''}? This cannot be undone.`
                        : 'This cannot be undone.'
                }
                confirmText="Confirm Disposal"
                variant="danger"
                loading={disposeLoading}
            />
        </div>
    );
};

export default AssetDetailPage;
