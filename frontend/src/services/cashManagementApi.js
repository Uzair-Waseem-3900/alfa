import { api } from '../utils/api';

export const cashManagementApi = {
    stats: {
        get: () => api.get('/cash-management/stats/'),
    },
    adjustments: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/cash-management/adjustments/${query ? `?${query}` : ''}`);
        },
        getById: (id) => api.get(`/cash-management/adjustments/${id}/`),
        create: (data) => api.post('/cash-management/adjustments/', data),
        delete: (id) => api.delete(`/cash-management/adjustments/${id}/`),
    },
    investors: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/cash-management/investors/${query ? `?${query}` : ''}`);
        },
        getById: (id) => api.get(`/cash-management/investors/${id}/`),
        create: (data) => api.post('/cash-management/investors/', data),
        update: (id, data) => api.patch(`/cash-management/investors/${id}/`, data),
        delete: (id) => api.delete(`/cash-management/investors/${id}/`),
    },
    investorValuationEntries: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/cash-management/investors/valuation-entries/${query ? `?${query}` : ''}`);
        },
    },
    investorTransactions: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/cash-management/investor-transactions/${query ? `?${query}` : ''}`);
        },
        getById: (id) => api.get(`/cash-management/investor-transactions/${id}/`),
        create: (data) => api.post('/cash-management/investor-transactions/', data),
        delete: (id) => api.delete(`/cash-management/investor-transactions/${id}/`),
    },
    ownerTransactions: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/cash-management/owner-transactions/${query ? `?${query}` : ''}`);
        },
        getById: (id) => api.get(`/cash-management/owner-transactions/${id}/`),
        create: (data) => api.post('/cash-management/owner-transactions/', data),
        delete: (id) => api.delete(`/cash-management/owner-transactions/${id}/`),
    },
};
