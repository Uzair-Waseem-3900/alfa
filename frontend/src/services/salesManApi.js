import { api } from '../utils/api';

export const salesManApi = {
    salesMen: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/sales-man/sales-men/${query ? `?${query}` : ''}`);
        },
        getById: (id) => api.get(`/sales-man/sales-men/${id}/`),
        create: (data) => api.post('/sales-man/sales-men/', data),
        update: (id, data) => api.patch(`/sales-man/sales-men/${id}/`, data),
        delete: (id) => api.delete(`/sales-man/sales-men/${id}/`),
    },
    linkNames: {
        getAll: (salesManId) => api.get(`/sales-man/sales-men/${salesManId}/link-names/`),
        create: (salesManId, data) => api.post(`/sales-man/sales-men/${salesManId}/link-names/`, data),
        delete: (id) => api.delete(`/sales-man/link-names/${id}/`),
        // Flat, unpaginated list across all sales men — dropdown source for
        // the customer create/edit form. Any authenticated user can call
        // this (customer create/update isn't admin-only).
        getAllOptions: () => api.get('/sales-man/link-names/'),
    },
    customers: {
        getAll: (salesManId, params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/sales-man/sales-men/${salesManId}/customers/${query ? `?${query}` : ''}`);
        },
    },
    invoices: {
        getAll: (salesManId, params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/sales-man/sales-men/${salesManId}/invoices/${query ? `?${query}` : ''}`);
        },
    },
};
