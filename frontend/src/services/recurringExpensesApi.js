import { api } from '../utils/api';

export const recurringExpensesApi = {
    flowStats: {
        get: () => api.get('/recurring-expenses/stats/flow/'),
    },
    monthlyStats: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/recurring-expenses/stats/monthly/${query ? `?${query}` : ''}`);
        },
        getByPeriod: (period) => api.get(`/recurring-expenses/stats/monthly/${period}/`),
    },
    categories: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/recurring-expenses/categories/${query ? `?${query}` : ''}`);
        },
        create: (data) => api.post('/recurring-expenses/categories/', data),
        update: (id, data) => api.patch(`/recurring-expenses/categories/${id}/`, data),
        delete: (id) => api.delete(`/recurring-expenses/categories/${id}/`),
    },
    templates: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/recurring-expenses/templates/${query ? `?${query}` : ''}`);
        },
        getById: (id) => api.get(`/recurring-expenses/templates/${id}/`),
        create: (data) => api.post('/recurring-expenses/templates/', data),
        update: (id, data) => api.patch(`/recurring-expenses/templates/${id}/`, data),
        delete: (id) => api.delete(`/recurring-expenses/templates/${id}/`),
    },
    pendingDues: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/recurring-expenses/templates/pending-dues/${query ? `?${query}` : ''}`);
        },
    },
    assignments: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/recurring-expenses/assignments/${query ? `?${query}` : ''}`);
        },
        getById: (id) => api.get(`/recurring-expenses/assignments/${id}/`),
        create: (data) => api.post('/recurring-expenses/assignments/', data),
        bulkCreate: (data) => api.post('/recurring-expenses/assignments/bulk/', data),
        delete: (id) => api.delete(`/recurring-expenses/assignments/${id}/`),
    },
    payments: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/recurring-expenses/payments/${query ? `?${query}` : ''}`);
        },
        getById: (id) => api.get(`/recurring-expenses/payments/${id}/`),
        create: (data) => api.post('/recurring-expenses/payments/', data),
        delete: (id) => api.delete(`/recurring-expenses/payments/${id}/`),
    },
};
