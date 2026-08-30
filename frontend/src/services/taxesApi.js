import { api } from '../utils/api';

export const taxesApi = {
    stats: {
        get: () => api.get('/taxes/stats/'),
    },
    payments: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/taxes/payments/${query ? `?${query}` : ''}`);
        },
        getById: (id) => api.get(`/taxes/payments/${id}/`),
        create: (data) => api.post('/taxes/payments/', data),
        delete: (id) => api.delete(`/taxes/payments/${id}/`),
    },
    whtPayments: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/taxes/wht-payments/${query ? `?${query}` : ''}`);
        },
        getById: (id) => api.get(`/taxes/wht-payments/${id}/`),
        create: (data) => api.post('/taxes/wht-payments/', data),
        delete: (id) => api.delete(`/taxes/wht-payments/${id}/`),
    },
};
