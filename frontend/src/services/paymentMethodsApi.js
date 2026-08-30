import { api } from '../utils/api';

export const paymentMethodsApi = {
    methods: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/payment-methods/${query ? `?${query}` : ''}`);
        },
        getById: (id) => api.get(`/payment-methods/${id}/`),
        create: (data) => api.post('/payment-methods/', data),
        update: (id, data) => api.patch(`/payment-methods/${id}/`, data),
        delete: (id) => api.delete(`/payment-methods/${id}/`),
    },
    allocations: {
        getForMethod: (methodId, params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/payment-methods/${methodId}/allocations/${query ? `?${query}` : ''}`);
        },
    },
    transfers: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/payment-methods/transfers/${query ? `?${query}` : ''}`);
        },
        getById: (id) => api.get(`/payment-methods/transfers/${id}/`),
        create: (data) => api.post('/payment-methods/transfers/', data),
        delete: (id) => api.delete(`/payment-methods/transfers/${id}/`),
    },
};
