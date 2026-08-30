import { api } from '../utils/api';

// System-wide Activity Log — superuser-only. See instructions/frontend.md:
// never touch backend routes/contracts, this only consumes them.
export const activityLogApi = {
    events: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/activity-log/events/${query ? `?${query}` : ''}`);
        },
    },
    stats: {
        get: () => api.get('/activity-log/stats/'),
    },
    tracking: {
        setEnabled: (enabled) => api.patch('/activity-log/toggle/', { enabled }),
    },
};
