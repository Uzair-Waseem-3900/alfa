import { useState } from 'react';
import { Navigate } from 'react-router-dom';
import { Tags, RefreshCw, Send } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { useProviders, usePartnerRateList, useRequestAccess } from '../../hooks/useB2B';
import { extractErrorMessage } from '../../utils/errorMessage';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Table from '../../components/ui/Table';
import Badge from '../../components/ui/Badge';
import Tabs from '../../components/ui/Tabs';
import SearchBar from '../../components/ui/SearchBar';
import Pagination from '../../components/ui/Pagination';
import EmptyState from '../../components/ui/EmptyState';
import InlineAlert from '../../components/ui/InlineAlert';
import WakePartnerButton from '../../components/b2b/WakePartnerButton';
import { b2bApi } from '../../services/b2bApi';

const fmt = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : Number(value);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

// What the status card says and which action it offers for each access status.
// `action` is 'request' (send a request), 'refresh' (re-check) or null.
const STATUS_VIEW = {
    not_requested: {
        badge: { variant: 'default', label: 'Not requested' },
        text: (name) => `You haven't asked ${name} for their rate list yet.`,
        action: 'request', actionLabel: 'Request Rate List',
    },
    pending: {
        badge: { variant: 'pending', label: 'Pending' },
        text: (name) => `Waiting for ${name} to approve your request.`,
        action: 'refresh', actionLabel: 'Check Again',
    },
    rejected: {
        badge: { variant: 'error', label: 'Rejected' },
        text: (name) => `${name} did not approve your request.`,
        action: 'request', actionLabel: 'Request Again',
    },
    revoked: {
        badge: { variant: 'warning', label: 'Sharing stopped' },
        text: (name) => `${name} stopped sharing their rate list with you.`,
        action: 'request', actionLabel: 'Request Again',
    },
    approved: {
        badge: { variant: 'success', label: 'Approved' },
        text: (name) => `Live prices from ${name}. Always their latest rates; nothing is stored here.`,
        action: 'refresh', actionLabel: 'Refresh',
    },
};

const PartnerRatesPage = () => {
    const { user } = useAuth();
    const { toast } = useToast();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const { providers, initialLoading: providersLoading, error: providersError, refetch: refetchProviders } = useProviders();
    const [selected, setSelected] = useState('');
    const provider = selected || providers[0]?.key || '';

    const {
        data: rates, meta, page, setPage, loading, initialLoading, error: listError,
        filters, setFilters, status, detail, refetch,
    } = usePartnerRateList(provider);
    const { requestAccess, mutating } = useRequestAccess();

    const [searchTerm, setSearchTerm] = useState('');

    if (!isAdmin) {
        return <Navigate to="/dashboard" replace />;
    }

    const handleRequest = async () => {
        try {
            const result = await requestAccess(provider);
            if (result?.status === 'not_configured') {
                toast.error(result.detail || 'The partner did not accept this connection.');
            } else {
                toast.success('Request sent');
            }
            await refetch();
        } catch (error) {
            toast.error(extractErrorMessage(error, 'Failed to send the request'));
        }
    };

    const handleSearch = (value) => {
        setSearchTerm(value);
        setFilters({ ...filters, search: value });
    };

    const handleProviderChange = (key) => {
        setSelected(key);
        setSearchTerm('');
        setFilters({});
    };

    const columns = [
        {
            key: 'code',
            label: 'Code',
            width: '160px',
            render: (value) => <span className="font-mono text-sm text-neutral-700">{value}</span>,
        },
        {
            key: 'name',
            label: 'Product',
            render: (value) => <span className="font-medium text-neutral-900">{value}</span>,
        },
        {
            key: 'selling_price',
            label: 'Price (PKR)',
            width: '160px',
            render: (value) => <span className="font-semibold text-success-600">Rs. {fmt(value)}</span>,
        },
    ];

    const header = (
        <div>
            <div className="flex items-center gap-2.5">
                <Tags className="w-6 h-6 text-primary-600" />
                <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900">Partner Rate List</h1>
            </div>
            <p className="text-neutral-500 mt-1">See a partner software's current selling prices, live.</p>
        </div>
    );

    if (providersLoading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    if (providersError) {
        return (
            <div className="space-y-6">
                {header}
                <InlineAlert variant="error" title="Couldn't load partners" message={providersError} onRetry={refetchProviders} />
            </div>
        );
    }

    if (providers.length === 0) {
        return (
            <div className="space-y-6">
                {header}
                <EmptyState
                    title="No Partner Connected"
                    description="No partner software is configured for this installation yet."
                />
            </div>
        );
    }

    const view = STATUS_VIEW[status];
    const approved = status === 'approved';

    return (
        <div className="space-y-6">
            {header}

            {providers.length > 1 && (
                <Tabs
                    tabs={providers.map((p) => ({ value: p.key, label: p.key }))}
                    activeTab={provider}
                    onChange={handleProviderChange}
                    className="overflow-x-auto"
                />
            )}

            {provider && (
                <WakePartnerButton
                    partnerLabel={provider}
                    wake={() => b2bApi.providers.wake(provider)}
                    onAwake={refetch}
                />
            )}

            {initialLoading ? (
                <div className="flex items-center justify-center py-16">
                    <LoadingSpinner size="lg" />
                </div>
            ) : listError ? (
                <InlineAlert variant="error" title="Couldn't reach the partner" message={listError} onRetry={refetch} />
            ) : status === 'not_configured' ? (
                <InlineAlert variant="warning" title="Connection not accepted" message={detail} onRetry={refetch} retryLabel="Try Again" />
            ) : view ? (
                <Card className="p-5" hover={false}>
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                        <div className="space-y-1.5">
                            <div className="flex items-center gap-2.5 flex-wrap">
                                <h2 className="text-lg font-semibold text-neutral-900">{provider}</h2>
                                <Badge variant={view.badge.variant}>{view.badge.label}</Badge>
                            </div>
                            <p className="text-sm text-neutral-600">{view.text(provider)}</p>
                        </div>
                        {view.action === 'request' && (
                            <Button icon={Send} onClick={handleRequest} loading={mutating}>
                                {view.actionLabel}
                            </Button>
                        )}
                        {view.action === 'refresh' && (
                            <Button variant="secondary" icon={RefreshCw} onClick={refetch} loading={loading}>
                                {view.actionLabel}
                            </Button>
                        )}
                    </div>
                </Card>
            ) : null}

            {approved && !listError && (
                <>
                    <SearchBar onSearch={handleSearch} placeholder="Search by product name or code..." value={searchTerm} />

                    {loading ? (
                        <div className="flex items-center justify-center py-16">
                            <LoadingSpinner size="lg" />
                        </div>
                    ) : rates.length === 0 ? (
                        <EmptyState
                            title="No Products Found"
                            description={searchTerm ? 'No priced product matches your search.' : 'This partner has no priced products yet.'}
                        />
                    ) : (
                        <>
                            <Table columns={columns} data={rates} />
                            {meta.totalPages > 1 && (
                                <Pagination currentPage={meta.currentPage} totalPages={meta.totalPages} onPageChange={setPage} />
                            )}
                        </>
                    )}
                </>
            )}
        </div>
    );
};

export default PartnerRatesPage;
