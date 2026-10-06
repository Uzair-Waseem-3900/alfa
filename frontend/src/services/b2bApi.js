import { api } from '../utils/api';

const buildQuery = (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return query ? `?${query}` : '';
};

export const b2bApi = {
    providers: {
        getAll: (params = {}) => api.get(`/b2b/providers/${buildQuery(params)}`),
        // Live proxy to the partner software — always its latest rate list.
        rateList: (provider, params = {}) =>
            api.get(`/b2b/providers/${encodeURIComponent(provider)}/rate-list/${buildQuery(params)}`),
        request: (provider) => api.post(`/b2b/providers/${encodeURIComponent(provider)}/request/`),
        // One readiness check of the partner's backend (no data changes). Only called when the user presses "Wake up".
        wake: (provider) => api.post(`/b2b/providers/${encodeURIComponent(provider)}/wake/`),
        // Live search in the partner's priced catalog (never any stock figure).
        searchProducts: (provider, params = {}) =>
            api.get(`/b2b/providers/${encodeURIComponent(provider)}/products/${buildQuery(params)}`),
    },
    purchaseRequests: {
        getAll: (params = {}) => api.get(`/b2b/purchase-requests/${buildQuery(params)}`),
        getById: (id) => api.get(`/b2b/purchase-requests/${id}/`),
        create: (data) => api.post('/b2b/purchase-requests/', data),
        cancel: (id) => api.post(`/b2b/purchase-requests/${id}/cancel/`),
        // "Check for updates now" — asks the partner about every undecided request.
        sync: () => api.post('/b2b/purchase-requests/sync/'),
    },
};
