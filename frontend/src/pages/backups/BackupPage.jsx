import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
    DatabaseBackup, HardDrive, Download, Cloud, RefreshCw,
    History, Clock, CloudUpload,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { useBackupStats } from '../../hooks/useBackups';
import { backupsApi } from '../../services/backupsApi';
import { extractErrorMessage } from '../../utils/errorMessage';
import Card from '../../components/ui/Card';
import Button from '../../components/ui/Button';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import InlineAlert from '../../components/ui/InlineAlert';
import ConfirmDialog from '../../components/ui/ConfirmDialog';

const fmtDate = (value) => value ? new Date(value).toLocaleString() : 'Never';

const RESULT_INITIAL = { key: null, error: '', info: null };

// Local backups just stream a zip download — nothing on the server changes,
// so they run immediately. Remote backups write directly into the
// configured remote database (a FULL remote backup even prunes rows that no
// longer exist locally), so those are genuinely consequential and get a
// confirmation step first.
const CARDS = [
    {
        key: 'fullLocal',
        title: 'Full Backup — Local',
        description: 'Every row in the system, from day one to now. Downloads as a zip file — nothing is kept on the server.',
        icon: HardDrive,
        fn: () => backupsApi.fullLocal(),
        isDownload: true,
        destructive: false,
    },
    {
        key: 'incrementalLocal',
        title: 'Incremental Backup — Local',
        description: 'Only rows changed since the last local backup. Downloads as a zip file.',
        icon: Download,
        fn: () => backupsApi.incrementalLocal(),
        isDownload: true,
        destructive: false,
    },
    {
        key: 'fullRemote',
        title: 'Full Backup — Remote',
        description: 'Every row, migrated and loaded directly into the configured remote database. Also removes remote rows no longer present locally, so the remote becomes an exact mirror.',
        icon: Cloud,
        fn: () => backupsApi.fullRemote(),
        isDownload: false,
        destructive: true,
        confirmMessage: 'This writes directly into the configured remote database and deletes any remote rows that no longer exist locally, so the remote becomes an exact mirror. This cannot be undone. Continue?',
    },
    {
        key: 'incrementalRemote',
        title: 'Incremental Backup — Remote',
        description: 'Only rows changed since the last remote backup, loaded into the remote database.',
        icon: RefreshCw,
        fn: () => backupsApi.incrementalRemote(),
        isDownload: false,
        destructive: true,
        confirmMessage: 'This writes changed rows directly into the configured remote database. Continue?',
    },
];

const BackupPage = () => {
    const { user } = useAuth();
    const { toast } = useToast();
    const navigate = useNavigate();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const { data: stats, loading: statsLoading, refetch: refetchStats } = useBackupStats();
    const [runningKey, setRunningKey] = useState(null);
    const [result, setResult] = useState(RESULT_INITIAL);
    const [confirmCard, setConfirmCard] = useState(null);

    if (!isAdmin) {
        navigate('/dashboard');
        return null;
    }

    const executeBackup = async (card) => {
        setRunningKey(card.key);
        setResult(RESULT_INITIAL);
        try {
            const res = await card.fn();
            const info = card.isDownload
                ? { message: 'Backup downloaded successfully.' }
                : {
                    message: res.schema_migrated
                        ? 'Remote schema was behind — migrated, and ran as a FULL backup instead.'
                        : 'Remote backup completed successfully.',
                    rowCount: res.row_count,
                    backupType: res.backup_type,
                };
            setResult({ key: card.key, error: '', info });
            toast.success(card.isDownload ? 'Backup downloaded' : 'Remote backup completed');
            setConfirmCard(null);
        } catch (err) {
            const message = extractErrorMessage(err, 'Backup failed');
            setResult({ key: card.key, error: message, info: null });
            toast.error(message);
            // Leave the confirmation dialog open on failure so the user can
            // see what happened without losing their place / re-triggering
            // the confirm step from scratch.
        } finally {
            setRunningKey(null);
            refetchStats();
        }
    };

    const handleCardAction = (card) => {
        if (card.destructive) {
            setConfirmCard(card);
            return;
        }
        executeBackup(card);
    };

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="flex items-start gap-4">
                    <div className="hidden sm:flex w-12 h-12 rounded-2xl bg-gradient-to-br from-primary-700 to-accent-600 items-center justify-center shadow-lg shadow-primary-900/20 flex-shrink-0">
                        <DatabaseBackup className="w-6 h-6 text-white" />
                    </div>
                    <div>
                        <h1 className="text-3xl font-bold text-neutral-900">Backups</h1>
                        <p className="text-neutral-500 mt-1">
                            Create a full or incremental backup, locally or to a remote database.
                        </p>
                    </div>
                </div>
                <Link to="/backups/history">
                    <Button variant="secondary" icon={History}>View History</Button>
                </Link>
            </div>

            {statsLoading ? (
                <div className="flex items-center justify-center py-8">
                    <LoadingSpinner size="md" />
                </div>
            ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <Card className="p-5 flex items-center gap-4">
                        <div className="w-10 h-10 rounded-xl bg-primary-50 flex items-center justify-center flex-shrink-0">
                            <Clock className="w-5 h-5 text-primary-600" />
                        </div>
                        <div>
                            <p className="text-sm text-neutral-500">Last Local Backup</p>
                            <p className="text-lg font-semibold text-neutral-900">{fmtDate(stats?.local_last_backup_at)}</p>
                        </div>
                    </Card>
                    <Card className="p-5 flex items-center gap-4">
                        <div className="w-10 h-10 rounded-xl bg-accent-50 flex items-center justify-center flex-shrink-0">
                            <CloudUpload className="w-5 h-5 text-accent-600" />
                        </div>
                        <div>
                            <p className="text-sm text-neutral-500">Last Remote Backup</p>
                            <p className="text-lg font-semibold text-neutral-900">{fmtDate(stats?.remote_last_backup_at)}</p>
                        </div>
                    </Card>
                </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {CARDS.map((card) => {
                    const Icon = card.icon;
                    const isRunning = runningKey === card.key;
                    return (
                        <Card key={card.key} className="p-6" hover={false}>
                            <div className="flex items-start gap-4">
                                <div className={`w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0 ${
                                    card.destructive ? 'bg-warning-50 text-warning-600' : 'bg-primary-50 text-primary-600'
                                }`}>
                                    <Icon className="w-5 h-5" />
                                </div>
                                <div className="flex-1 min-w-0">
                                    <h2 className="text-lg font-semibold text-neutral-900">{card.title}</h2>
                                    <p className="text-sm text-neutral-500 mt-1">{card.description}</p>
                                </div>
                            </div>

                            <Button
                                className="mt-5 w-full sm:w-auto"
                                variant={card.destructive ? 'danger' : 'primary'}
                                loading={isRunning}
                                disabled={runningKey !== null && !isRunning}
                                onClick={() => handleCardAction(card)}
                            >
                                {isRunning ? 'Running…' : 'Run Backup'}
                            </Button>

                            {result.key === card.key && result.error && (
                                <InlineAlert
                                    className="mt-4"
                                    variant="error"
                                    message={result.error}
                                />
                            )}
                            {result.key === card.key && result.info && (
                                <motion.div
                                    initial={{ opacity: 0, y: -6 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    className="mt-4 p-3 bg-success-50 border border-success-200 rounded-lg"
                                >
                                    <p className="text-sm text-success-700">{result.info.message}</p>
                                    {result.info.rowCount != null && (
                                        <p className="text-xs text-success-600 mt-1">
                                            {result.info.rowCount} rows &middot; type: {result.info.backupType}
                                        </p>
                                    )}
                                </motion.div>
                            )}
                        </Card>
                    );
                })}
            </div>

            <ConfirmDialog
                isOpen={confirmCard !== null}
                onClose={() => setConfirmCard(null)}
                onConfirm={() => executeBackup(confirmCard)}
                title={confirmCard?.title}
                message={confirmCard?.confirmMessage}
                confirmText="Run Backup"
                variant="danger"
                loading={runningKey === confirmCard?.key}
            />
        </div>
    );
};

export default BackupPage;
