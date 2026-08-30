import { api } from '../utils/api';

export const creditScoreApi = {
    customers: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/credit-score/customers/${query ? `?${query}` : ''}`);
        },
        getById: (customerId) => api.get(`/credit-score/customers/${customerId}/`),
        getHistory: (customerId, params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/credit-score/customers/${customerId}/history/${query ? `?${query}` : ''}`);
        },
    },
};
