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
    },
};
