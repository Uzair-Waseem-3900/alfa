import { api } from '../utils/api';

export const assetsApi = {
    stats: {
        get: () => api.get('/assets/stats/'),
    },
    categories: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/assets/categories/${query ? `?${query}` : ''}`);
        },
        getById: (id) => api.get(`/assets/categories/${id}/`),
        create: (data) => api.post('/assets/categories/', data),
        update: (id, data) => api.patch(`/assets/categories/${id}/`, data),
    },
    items: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/assets/items/${query ? `?${query}` : ''}`);
        },
        getById: (id) => api.get(`/assets/items/${id}/`),
        create: (data) => api.post('/assets/items/', data),
        revalue: (id, data) => api.post(`/assets/items/${id}/revalue/`, data),
        dispose: (id, data) => api.post(`/assets/items/${id}/dispose/`, data),
    },
    valuationEntries: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/assets/items/valuation-entries/${query ? `?${query}` : ''}`);
        },
    },
    disposals: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/assets/disposals/${query ? `?${query}` : ''}`);
        },
    },
    payments: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/assets/payments/${query ? `?${query}` : ''}`);
        },
        getById: (id) => api.get(`/assets/payments/${id}/`),
    },
};
