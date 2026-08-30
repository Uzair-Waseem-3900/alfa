import { api } from '../utils/api';

export const ratesApi = {
    // Get all rates with filters
    getAll: (params = {}) => {
        const query = new URLSearchParams(params).toString();
        return api.get(`/rates/${query ? `?${query}` : ''}`);
    },

    // Get single rate
    getById: (id) => api.get(`/rates/${id}/`),

    // Get products that don't have a rate set yet (paginated + searchable)
    getUnpriced: (params = {}) => {
        const query = new URLSearchParams(params).toString();
        return api.get(`/rates/unpriced/${query ? `?${query}` : ''}`);
    },

    // Create rate for a product (admin/superuser)
    create: (data) => api.post('/rates/', data),

    // Update rate (admin/superuser)
    update: (id, data) => api.patch(`/rates/${id}/`, data),

    // Get price history for a product
    getHistory: (productId, params) => api.get(`/rates/history/${productId}/`, { params }),
};