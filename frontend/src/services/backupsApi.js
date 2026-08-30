import { api } from '../utils/api';

// Local backups return a zip file directly — fetched manually (not via the
// shared `api` client, which expects JSON) so the blob can be saved as a
// real download, same pattern as utils/print.js's PDF handling.
const downloadBackupFile = async (endpoint) => {
    const baseUrl = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';
    const token = localStorage.getItem('access_token');
    if (!token) {
        throw new Error('Please login again to run a backup');
    }

    const response = await fetch(`${baseUrl}/api${endpoint}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
    });

    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Backup failed');
    }

    const disposition = response.headers.get('Content-Disposition') || '';
    const match = disposition.match(/filename="?([^"]+)"?/);
    const filename = match ? match[1] : 'backup.zip';

    const blob = await response.blob();
    const blobUrl = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = blobUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(blobUrl);
};

export const backupsApi = {
    stats: {
        get: () => api.get('/backups/stats/'),
    },
    history: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/backups/history/${query ? `?${query}` : ''}`);
        },
    },
    fullLocal: () => downloadBackupFile('/backups/full/local/'),
    incrementalLocal: () => downloadBackupFile('/backups/incremental/local/'),
    fullRemote: () => api.post('/backups/full/remote/'),
    incrementalRemote: () => api.post('/backups/incremental/remote/'),
};
