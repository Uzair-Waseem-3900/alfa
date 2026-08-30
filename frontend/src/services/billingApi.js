import { api } from '../utils/api';

export const billingApi = {
    // Customers
    customers: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/billing/customers/${query ? `?${query}` : ''}`);
        },
        getOutstanding: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/billing/customers/outstanding/${query ? `?${query}` : ''}`);
        },
        getOutstandingSummary: (id) => api.get(`/billing/customers/${id}/outstanding/`),
        getById: (id) => api.get(`/billing/customers/${id}/`),
        create: (data) => api.post('/billing/customers/', data),
        update: (id, data) => api.patch(`/billing/customers/${id}/`, data),
        delete: (id) => api.delete(`/billing/customers/${id}/`),
    },

    // Invoices
    invoices: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/billing/invoices/${query ? `?${query}` : ''}`);
        },
        getDrafts: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/billing/invoices/drafts/${query ? `?${query}` : ''}`);
        },
        getConfirmed: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/billing/invoices/confirmed/${query ? `?${query}` : ''}`);
        },
        getOutstanding: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/billing/invoices/outstanding/${query ? `?${query}` : ''}`);
        },
        getDue: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/billing/invoices/due/${query ? `?${query}` : ''}`);
        },
        updateDueDate: (id, payment_due_date) =>
            api.patch(`/billing/invoices/${id}/due-date/`, { payment_due_date }),
        getSearch: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/billing/invoices/search/${query ? `?${query}` : ''}`);
        },
        getById: (id) => api.get(`/billing/invoices/${id}/`),
        create: (data) => api.post('/billing/invoices/', data),
        update: (id, data) => api.patch(`/billing/invoices/${id}/`, data),
        delete: (id) => api.delete(`/billing/invoices/${id}/`),
        confirm: (id) => api.post(`/billing/invoices/${id}/confirm/`),
        getPaymentSummary: (id) => api.get(`/billing/invoices/${id}/payment-summary/`),
        print: (id, isDraft = false) =>
            api.get(`/billing/invoices/${id}/print/?is_draft=${isDraft}`, { responseType: 'blob' }),
        savePDF: (id, data) => api.post(`/billing/invoices/${id}/pdf/save/`, data),
        getPDFs: (id) => api.get(`/billing/invoices/${id}/pdf/`),
        deletePDF: (pdfId) => api.delete(`/billing/pdf/${pdfId}/`),
    },

    // Shelves (for invoice-line/return shelf allocation)
    shelves: {
        // Shelves that currently hold stock (qty > 0) of a given product —
        // the backend search source for a sale line's consumption
        // allocation. search narrows by shelf name.
        getCandidates: (productId, search = '') => {
            const query = new URLSearchParams({ product_id: productId });
            if (search) query.set('search', search);
            return api.get(`/billing/shelves/candidates/?${query.toString()}`);
        },
        // Auto-allocate `quantity` units of a product across shelves that
        // currently hold stock, skipping `excludeShelfIds` (shelves the
        // caller already has manual rows for). Returns whatever it could
        // allocate plus a `shortfall` if total remaining stock fell short —
        // caller applies the allocations as-is either way.
        autoAllocate: (productId, quantity, excludeShelfIds = []) =>
            api.post('/billing/shelves/auto-allocate/', {
                product_id: productId,
                quantity,
                exclude_shelf_ids: excludeShelfIds,
            }),
    },

    // Invoice Item shelf allocations (consumption plan while draft)
    invoiceItems: {
        setShelfAllocations: (invoiceItemId, allocations) =>
            api.post(`/billing/invoice-items/${invoiceItemId}/shelf-allocations/`, { allocations }),
    },

    // Return Item shelf allocations (put-away plan while pending)
    returnItems: {
        setShelfAllocations: (returnItemId, allocations) =>
            api.post(`/billing/return-items/${returnItemId}/shelf-allocations/`, { allocations }),
    },

    // Payments
    payments: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/billing/payments/${query ? `?${query}` : ''}`);
        },
        getById: (paymentId) => api.get(`/billing/payments/${paymentId}/`),
        getByInvoice: (invoiceId, params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/billing/invoices/${invoiceId}/payments/${query ? `?${query}` : ''}`);
        },
        create: (invoiceId, data) => {
            const payload = {
                invoice: parseInt(invoiceId),
                amount: data.amount,
                method_allocations: data.method_allocations,
                payment_date: data.payment_date,
                note: data.note || '',
            };
            return api.post(`/billing/invoices/${invoiceId}/payments/`, payload);
        },
        delete: (paymentId) => api.delete(`/billing/payments/${paymentId}/`),
    },

    // Returns
    returns: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/billing/returns/${query ? `?${query}` : ''}`);
        },
        getByInvoice: (invoiceId, params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/billing/invoices/${invoiceId}/returns/${query ? `?${query}` : ''}`);
        },
        create: (invoiceId, data) => {
            const payload = {
                invoice_id: parseInt(invoiceId),
                items: data.items || [],
                note: data.note || '',
            };
            return api.post(`/billing/invoices/${invoiceId}/returns/`, payload);
        },
        accept: (returnId) => api.post(`/billing/returns/${returnId}/accept/`),
        update: (returnId, data) => {
            const payload = {
                items: data.items || [],
                ...(data.note !== undefined ? { note: data.note } : {}),
            };
            return api.patch(`/billing/returns/${returnId}/`, payload);
        },
        cancel: (returnId) => api.delete(`/billing/returns/${returnId}/`),
    },
};