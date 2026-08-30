import { useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import {
    History, ShieldAlert, SlidersHorizontal, X,
    PlusCircle, PencilLine, Trash2, RefreshCw, AlertOctagon,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { usersApi } from '../utils/api';
import { activityLogApi } from '../services/activityLogApi';
import { extractErrorMessage } from '../utils/errorMessage';
import { useActivityLogEvents, useActivityLogStats } from '../hooks/useActivityLog';
import Card from '../components/ui/Card';
import Table from '../components/ui/Table';
import Badge from '../components/ui/Badge';
import Button from '../components/ui/Button';
import SearchBar from '../components/ui/SearchBar';
import FilterBar from '../components/ui/FilterBar';
import Pagination from '../components/ui/Pagination';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import InlineAlert from '../components/ui/InlineAlert';
import EmptyState from '../components/ui/EmptyState';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import Switch from '../components/ui/Switch';

const ACTION_META = {
    create: { label: 'Create', variant: 'success', icon: PlusCircle },
    update: { label: 'Update', variant: 'info', icon: PencilLine },
    delete: { label: 'Delete', variant: 'error', icon: Trash2 },
    state_change: { label: 'State Change', variant: 'warning', icon: RefreshCw },
};

const ACTION_OPTIONS = [
    { value: '', label: 'All Actions' },
    { value: 'create', label: 'Create' },
    { value: 'update', label: 'Update' },
    { value: 'delete', label: 'Delete' },
    { value: 'state_change', label: 'State Change' },
];

const formatTimestamp = (value) => {
    if (!value) return 'N/A';
    return new Date(value).toLocaleString('en-US', {
        year: 'numeric', month: 'short', day: 'numeric',
        hour: '2-digit', minute: '2-digit',
    });
};

const StatBox = ({ label, value, tone = 'neutral' }) => {
    const tones = {
        neutral: 'text-neutral-900',
        success: 'text-success-600',
        info: 'text-info-600',
        error: 'text-error-600',
        warning: 'text-warning-600',
    };
    return (
        <Card className="p-4" hover={false}>
            <p className="text-xs text-neutral-500 mb-1">{label}</p>
            <p className={`text-2xl font-bold tabular-nums ${tones[tone]}`}>
                {value === null || value === undefined ? '—' : value.toLocaleString()}
            </p>
        </Card>
    );
};

const ActionBadge = ({ action, actionDisplay }) => {
    const meta = ACTION_META[action] || { label: actionDisplay || action, variant: 'default', icon: History };
    const Icon = meta.icon;
    return (
        <Badge variant={meta.variant} className="gap-1 whitespace-nowrap">
            <Icon className="w-3 h-3" />
            {meta.label}
        </Badge>
    );
};

const ActivityLogPage = () => {
    const { user } = useAuth();
    const { toast } = useToast();

    const [searchTerm, setSearchTerm] = useState('');
    const [highRisk, setHighRisk] = useState(false);
    const [showFilters, setShowFilters] = useState(false);
    const [users, setUsers] = useState([]);
    const [showDisableConfirm, setShowDisableConfirm] = useState(false);
    const [togglingTracking, setTogglingTracking] = useState(false);

    const {
        data: events, meta, page, setPage, loading, initialLoading, error: listError,
        filters, setFilters, refetch,
    } = useActivityLogEvents(searchTerm, highRisk);

    const {
        data: stats, loading: statsLoading, error: statsError, refetch: refetchStats,
    } = useActivityLogStats();

    // Superuser-only page. Non-superusers are redirected (backend also enforces).
    const isSuperuser = user?.role === 'superuser';

    useEffect(() => {
        if (!isSuperuser) return;
        (async () => {
            try {
                const response = await usersApi.getAll({ page_size: 500 });
                const list = Array.isArray(response) ? response : (response?.results || []);
                setUsers(list);
            } catch (err) {
                console.error('Failed to load users for filter:', err);
            }
        })();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isSuperuser]);

    if (!isSuperuser) {
        return <Navigate to="/dashboard" replace />;
    }

    const handleApplyFilters = (filterValues) => {
        setFilters(filterValues);
    };

    const handleResetFilters = () => {
        setFilters({});
        setSearchTerm('');
        setHighRisk(false);
    };

    const handleSearch = (value) => {
        setSearchTerm(value);
        setPage(1);
    };

    const toggleHighRisk = () => {
        setHighRisk((prev) => !prev);
        setPage(1);
    };

    // Turning tracking OFF stops every future write to the audit trail —
    // confirm first. Turning it back ON has no downside, so it fires
    // immediately with no confirmation step.
    const applyTrackingToggle = async (enabled) => {
        setTogglingTracking(true);
        try {
            await activityLogApi.tracking.setEnabled(enabled);
            toast.success(enabled ? 'Activity tracking enabled.' : 'Activity tracking disabled.');
            setShowDisableConfirm(false);
            await refetchStats();
        } catch (error) {
            toast.error(extractErrorMessage(error, 'Failed to update activity tracking.'));
        } finally {
            setTogglingTracking(false);
        }
    };

    const handleTrackingToggleClick = () => {
        if (stats?.is_enabled === false) {
            applyTrackingToggle(true);
        } else {
            setShowDisableConfirm(true);
        }
    };

    const hasActiveFilters = Object.keys(filters).length > 0 || !!searchTerm || highRisk;

    const filterConfig = [
        {
            name: 'user_id',
            label: 'User',
            type: 'select',
            options: [
                { value: '', label: 'All Users' },
                ...users.map((u) => ({
                    value: String(u.id ?? u.email),
                    label: u.first_name || u.last_name ? `${u.first_name || ''} ${u.last_name || ''}`.trim() : u.email,
                })),
            ],
        },
        { name: 'action', label: 'Action', type: 'select', options: ACTION_OPTIONS },
        { name: 'app_label', label: 'App', type: 'text' },
        { name: 'model_name', label: 'Model', type: 'text' },
        { name: 'date_from', label: 'Date From', type: 'date' },
        { name: 'date_to', label: 'Date To', type: 'date' },
    ];

    const columns = [
        {
            key: 'created_at',
            label: 'Timestamp',
            width: '180px',
            render: (value) => (
                <span className="text-sm text-neutral-600 whitespace-nowrap">{formatTimestamp(value)}</span>
            ),
        },
        {
            key: 'user_email',
            label: 'User',
            width: '200px',
            render: (value, row) => (
                value || row.user_name ? (
                    <div className="min-w-0">
                        <p className="text-sm font-medium text-neutral-900 truncate">{row.user_name || value}</p>
                        {row.user_name && value && (
                            <p className="text-xs text-neutral-400 truncate">{value}</p>
                        )}
                    </div>
                ) : (
                    <span className="text-sm text-neutral-400 italic">System</span>
                )
            ),
        },
        {
            key: 'action',
            label: 'Action',
            width: '140px',
            render: (value, row) => <ActionBadge action={value} actionDisplay={row.action_display} />,
        },
        {
            key: 'description',
            label: 'Description',
            render: (value, row) => (
                <div className="min-w-0 max-w-md">
                    <p className="text-sm text-neutral-700 break-words">{value || row.object_repr || '—'}</p>
                    <p className="text-xs text-neutral-400 mt-0.5">
                        {row.app_label} &middot; {row.model_name}
                    </p>
                </div>
            ),
        },
    ];

    if (initialLoading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex items-start justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-3">
                    <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-primary-600 to-accent-600 flex items-center justify-center shadow-lg shadow-primary-900/20 flex-shrink-0">
                        <History className="w-5 h-5 text-white" />
                    </div>
                    <div>
                        <h1 className="text-3xl font-bold text-neutral-900">Activity Log</h1>
                        <p className="text-neutral-500 mt-0.5">
                            System-wide audit trail of every create, update, delete, and status change.
                        </p>
                    </div>
                </div>

                {!statsLoading && !statsError && (
                    <div className="flex items-center gap-2.5">
                        <span className={`text-sm font-medium ${stats?.is_enabled === false ? 'text-neutral-500' : 'text-success-600'}`}>
                            Tracking: {stats?.is_enabled === false ? 'Off' : 'On'}
                        </span>
                        <Switch
                            checked={stats?.is_enabled !== false}
                            onChange={handleTrackingToggleClick}
                            loading={togglingTracking}
                        />
                    </div>
                )}
            </div>

            {/* Lifetime stats */}
            {statsError ? (
                <InlineAlert variant="error" message={statsError} onRetry={refetchStats} />
            ) : statsLoading ? (
                <div className="flex items-center justify-center py-8">
                    <LoadingSpinner size="lg" />
                </div>
            ) : (
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
                    <StatBox label="Total Events" value={stats?.total_events} />
                    <StatBox label="Creates" value={stats?.total_creates} tone="success" />
                    <StatBox label="Updates" value={stats?.total_updates} tone="info" />
                    <StatBox label="Deletes" value={stats?.total_deletes} tone="error" />
                    <StatBox label="State Changes" value={stats?.total_state_changes} tone="warning" />
                </div>
            )}
            {!statsLoading && !statsError && stats?.last_event_at && (
                <p className="text-xs text-neutral-400 -mt-3">
                    Last event recorded {formatTimestamp(stats.last_event_at)}
                </p>
            )}

            {/* High-risk quick filter */}
            <Card className={`p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-2 ${highRisk ? 'border-error-400 bg-error-50/50' : 'border-transparent'}`} hover={false}>
                <div className="flex items-center gap-3">
                    <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${highRisk ? 'bg-error-100 text-error-600' : 'bg-neutral-100 text-neutral-500'}`}>
                        <AlertOctagon className="w-5 h-5" />
                    </div>
                    <div>
                        <p className="font-semibold text-neutral-900">High-Risk Actions</p>
                        <p className="text-sm text-neutral-500">
                            Every delete, plus every change to pricing and money-moving records.
                        </p>
                    </div>
                </div>
                <Button
                    variant={highRisk ? 'danger' : 'secondary'}
                    onClick={toggleHighRisk}
                    icon={AlertOctagon}
                >
                    {highRisk ? 'Showing High-Risk Only' : 'Show High-Risk Only'}
                </Button>
            </Card>

            {/* Filters */}
            <div className="space-y-4">
                <div className="flex flex-col sm:flex-row gap-3">
                    <div className="flex-1">
                        <SearchBar
                            onSearch={handleSearch}
                            value={searchTerm}
                            placeholder="Search description or object..."
                            className="w-full"
                        />
                    </div>
                    <div className="flex gap-3">
                        <Button
                            variant="secondary"
                            onClick={() => setShowFilters(!showFilters)}
                            icon={SlidersHorizontal}
                        >
                            {showFilters ? 'Hide Filters' : 'Show Filters'}
                        </Button>
                        {hasActiveFilters && (
                            <Button variant="secondary" icon={X} onClick={handleResetFilters}>
                                Clear
                            </Button>
                        )}
                    </div>
                </div>

                {showFilters && (
                    <FilterBar
                        filters={filterConfig}
                        onApply={handleApplyFilters}
                        onReset={handleResetFilters}
                    />
                )}
            </div>

            {listError && (
                <InlineAlert variant="error" message={listError} onRetry={refetch} />
            )}

            <div className={`relative transition-opacity ${loading ? 'opacity-60' : 'opacity-100'}`}>
                {loading && (
                    <div className="absolute right-2 top-2 z-10">
                        <LoadingSpinner size="sm" />
                    </div>
                )}
                {events.length === 0 && !loading ? (
                    <EmptyState
                        icon={<ShieldAlert className="w-8 h-8 text-neutral-400" />}
                        title="No activity found"
                        description="Try adjusting your search or filters."
                    />
                ) : (
                    <Card className="p-0 overflow-hidden" hover={false}>
                        <Table columns={columns} data={events} />
                    </Card>
                )}
            </div>

            {meta.totalPages > 1 && (
                <Pagination
                    currentPage={meta.currentPage}
                    totalPages={meta.totalPages}
                    onPageChange={setPage}
                />
            )}

            <ConfirmDialog
                isOpen={showDisableConfirm}
                onClose={() => { if (!togglingTracking) setShowDisableConfirm(false); }}
                onConfirm={() => applyTrackingToggle(false)}
                loading={togglingTracking}
                title="Disable Activity Tracking"
                message="While tracking is off, nothing gets recorded — no creates, updates, deletes, or status changes will appear here until you turn it back on. Turning it off and back on is itself always recorded, so this action stays visible."
                confirmText="Disable Tracking"
                variant="danger"
            />
        </div>
    );
};

export default ActivityLogPage;
