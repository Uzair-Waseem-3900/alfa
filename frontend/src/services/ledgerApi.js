import { api } from '../utils/api';

// Shared factory — supplier and customer ledgers are the exact same REST
// shape aside from the base path, so build both API clients off one
// implementation instead of duplicating every method.
const buildLedgerApi = (basePath) => ({
    // List all ledgers
    getAll: (params = {}) => {
        const query = new URLSearchParams(params).toString();
        return api.get(`${basePath}/${query ? `?${query}` : ''}`);
    },

    // Get ledger detail by ledger ID
    getById: (id, params = {}) => {
        const query = new URLSearchParams(params).toString();
        return api.get(`${basePath}/${id}/${query ? `?${query}` : ''}`);
    },

    // Print ledger PDF
    print: (id, params = {}) => {
        const query = new URLSearchParams(params).toString();
        return api.get(`${basePath}/${id}/print/${query ? `?${query}` : ''}`, { responseType: 'blob' });
    },

    // Save ledger PDF
    savePDF: (id, data) => api.post(`${basePath}/${id}/pdf/save/`, data),

    // Get saved PDFs
    getSavedPDFs: (id, params) => api.get(`${basePath}/${id}/pdf/`, { params }),

    // Delete saved PDF
    deleteSavedPDF: (pdfId) => api.delete(`${basePath}/pdf/${pdfId}/`),

    // Delete ledger (soft delete) — only allowed once the owner is deleted
    delete: (id) => api.delete(`${basePath}/${id}/`),
});

export const ledgerApi = {
    ...buildLedgerApi('/ledger'),

    // Get ledger by supplier ID
    getBySupplierId: (supplierId, params = {}) => {
        const query = new URLSearchParams(params).toString();
        return api.get(`/ledger/supplier/${supplierId}/${query ? `?${query}` : ''}`);
    },
};

export const customerLedgerApi = {
    ...buildLedgerApi('/ledger/customers'),

    // Get ledger by customer ID
    getByCustomerId: (customerId, params = {}) => {
        const query = new URLSearchParams(params).toString();
        return api.get(`/ledger/customers/by-customer/${customerId}/${query ? `?${query}` : ''}`);
    },
};