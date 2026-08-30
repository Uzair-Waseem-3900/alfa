import { api } from '../utils/api';

// Extracts a human-readable message from a DRF error response.
export const extractApiError = (err, fallback = 'Something went wrong') => {
    const d = err?.response?.data;
    if (!d) return err?.message || fallback;
    if (typeof d === 'string') return d;
    if (d.detail) return d.detail;
    const first = Object.values(d)[0];
    if (Array.isArray(first)) return first[0];
    return typeof first === 'string' ? first : fallback;
};

const buildQuery = (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return query ? `?${query}` : '';
};

export const dataEntryApi = {
    supplierOpeningBalance: {
        getAll: (params = {}) => api.get(`/data-entry/supplier-opening-balance/${buildQuery(params)}`),
        create: (data) => api.post('/data-entry/supplier-opening-balance/', data),
    },
    customerOpeningBalance: {
        getAll: (params = {}) => api.get(`/data-entry/customer-opening-balance/${buildQuery(params)}`),
        create: (data) => api.post('/data-entry/customer-opening-balance/', data),
    },
    openingCash: {
        getAll: (params = {}) => api.get(`/data-entry/opening-cash/${buildQuery(params)}`),
        create: (data) => api.post('/data-entry/opening-cash/', data),
    },
    openingStock: {
        getAll: (params = {}) => api.get(`/data-entry/opening-stock/${buildQuery(params)}`),
        create: (data) => api.post('/data-entry/opening-stock/', data),
    },
    openingInvestorInvestment: {
        getAll: (params = {}) => api.get(`/data-entry/opening-investor-investment/${buildQuery(params)}`),
        create: (data) => api.post('/data-entry/opening-investor-investment/', data),
    },
};
