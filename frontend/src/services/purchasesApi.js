import { api } from '../utils/api';

// Base API functions for purchases app
export const purchasesApi = {
    // Categories
    categories: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/categories/${query ? `?${query}` : ''}`);
        },
        create: (data) => api.post('/categories/', data),
        update: (id, data) => api.patch(`/categories/${id}/`, data),
        delete: (id) => api.delete(`/categories/${id}/`),
    },

    // Shelves
    shelves: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/shelves/${query ? `?${query}` : ''}`);
        },
        getById: (id) => api.get(`/shelves/${id}/`),
        create: (data) => api.post('/shelves/', data),
        update: (id, data) => api.patch(`/shelves/${id}/`, data),
        delete: (id) => api.delete(`/shelves/${id}/`),
        // Products + quantities currently physically on one shelf.
        getStock: (shelfId, params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/shelves/${shelfId}/stock/${query ? `?${query}` : ''}`);
        },
        // Shelves that currently hold stock (qty > 0) of a given product —
        // the backend search source for consumption allocations (sale,
        // purchase return, lost inventory). search narrows by shelf name.
        getCandidates: (productId, search = '') => {
            const query = new URLSearchParams({ product_id: productId });
            if (search) query.set('search', search);
            return api.get(`/shelves/candidates/?${query.toString()}`);
        },
        moveStock: (data) => api.post('/shelves/move/', data),
        // Auto-allocate `quantity` units of a product across shelves that
        // currently hold stock, skipping `excludeShelfIds` (shelves the
        // caller already has manual rows for). Returns whatever it could
        // allocate plus a `shortfall` if total remaining stock fell short —
        // caller applies the allocations as-is either way.
        autoAllocate: (productId, quantity, excludeShelfIds = []) =>
            api.post('/shelves/auto-allocate/', {
                product_id: productId,
                quantity,
                exclude_shelf_ids: excludeShelfIds,
            }),
    },

    // Suppliers
    suppliers: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/suppliers/${query ? `?${query}` : ''}`);
        },
        getById: (id) => api.get(`/suppliers/${id}/`),
        create: (data) => api.post('/suppliers/', data),
        update: (id, data) => api.patch(`/suppliers/${id}/`, data),
        delete: (id) => api.delete(`/suppliers/${id}/`),
        getOutstanding: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/suppliers/outstanding/${query ? `?${query}` : ''}`);
        },
        getPayableSummary: (id) => api.get(`/suppliers/${id}/payable-summary/`),
        getOutstandingOrders: (id) => api.get(`/suppliers/${id}/outstanding-orders/`),
    },

    // Products
    products: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/products/${query ? `?${query}` : ''}`);
        },
        create: (data) => api.post('/products/', data),
        update: (id, data) => api.patch(`/products/${id}/`, data),
        delete: (id) => api.delete(`/products/${id}/`),
    },

    // Purchase Orders
    orders: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/orders/${query ? `?${query}` : ''}`);
        },
        getDrafts: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/orders/drafts/${query ? `?${query}` : ''}`);
        },
        getConfirmed: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/orders/confirmed/${query ? `?${query}` : ''}`);
        },
        getOutstanding: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/orders/outstanding/${query ? `?${query}` : ''}`);
        },
        getById: (id) => api.get(`/orders/${id}/`),
        create: (data) => api.post('/orders/', data),
        update: (id, data) => api.patch(`/orders/${id}/`, data),
        delete: (id) => api.delete(`/orders/${id}/`),
        confirm: (id) => api.post(`/orders/${id}/confirm/`),
        getPaymentSummary: (id) => api.get(`/orders/${id}/payment-summary/`),
        print: (id, isDraft = false) =>
            api.get(`/orders/${id}/print/?is_draft=${isDraft}`, { responseType: 'blob' }),
        savePDF: (id, data) => api.post(`/orders/${id}/pdf/save/`, data),
        getPDFs: (id) => api.get(`/orders/${id}/pdf/`),
        deletePDF: (pdfId) => api.delete(`/pdf/${pdfId}/`),
    },

    // Purchase Item shelf allocations (put-away plan while order is draft)
    purchaseItems: {
        setShelfAllocations: (purchaseItemId, allocations) =>
            api.post(`/purchase-items/${purchaseItemId}/shelf-allocations/`, { allocations }),
    },

    // Purchase Return Item shelf allocations (consumption plan while pending)
    purchaseReturnItems: {
        setShelfAllocations: (returnItemId, allocations) =>
            api.post(`/return-items/${returnItemId}/shelf-allocations/`, { allocations }),
    },

    // Payments
    payments: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/payments/${query ? `?${query}` : ''}`);
        },
        getByOrder: (orderId, params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/orders/${orderId}/payments/${query ? `?${query}` : ''}`);
        },
        create: (orderId, data) => {
            // The backend expects 'order' field
            const payload = {
                order: parseInt(orderId),  // Use 'order' field name
                amount: data.amount,
                method_allocations: data.method_allocations,
                payment_date: data.payment_date,
                note: data.note || '',
            };
            return api.post(`/orders/${orderId}/payments/`, payload);
        },
        delete: (paymentId) => api.delete(`/payments/${paymentId}/`),
    },

    // Returns
    // Returns
    returns: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/returns/${query ? `?${query}` : ''}`);
        },
        getByOrder: (orderId, params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/orders/${orderId}/returns/${query ? `?${query}` : ''}`);
        },
        create: (orderId, data) => {
            // The backend expects 'order_id' and items with 'purchase_item_id'
            const payload = {
                order_id: parseInt(orderId),  // Changed from invoice_id to order_id
                items: data.items.map(item => ({
                    purchase_item_id: parseInt(item.purchase_item_id),  // Changed from invoice_item_id
                    quantity: parseInt(item.quantity) || 0,
                })),
                note: data.note || '',
            };
            console.log('Sending return payload:', payload); // Debug log
            return api.post(`/orders/${orderId}/returns/`, payload);
        },
        accept: (returnId) => api.post(`/returns/${returnId}/accept/`),
        update: (returnId, data) => {
            const payload = {
                items: data.items.map(item => ({
                    purchase_item_id: parseInt(item.purchase_item_id),
                    quantity: parseInt(item.quantity) || 0,
                    gst: item.gst || 0,
                    wht: item.wht || 0,
                })),
                ...(data.note !== undefined ? { note: data.note } : {}),
            };
            return api.patch(`/returns/${returnId}/`, payload);
        },
        cancel: (returnId) => api.delete(`/returns/${returnId}/`),
    },

    // Inventory
    inventory: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/inventory/${query ? `?${query}` : ''}`);
        },
        // O(1) whole-inventory stats for the summary cards — served off a
        // stored counter, not a live count, so it's always global (not
        // affected by search/category/shelf filters).
        getStats: () => api.get('/inventory/stats/'),
        // Breakdown lists behind the Low Stock / Out of Stock cards.
        // Same search/category/shelf params as getAll, paginated.
        getLowStock: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/inventory/low-stock/${query ? `?${query}` : ''}`);
        },
        getOutOfStock: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/inventory/out-of-stock/${query ? `?${query}` : ''}`);
        },
        getByProduct: (productId) => api.get(`/inventory/${productId}/`),
    },

    // Lost Inventory
    lostInventory: {
        getAll: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return api.get(`/lost-inventory/${query ? `?${query}` : ''}`);
        },
        getById: (id) => api.get(`/lost-inventory/${id}/`),
        create: (data) => api.post('/lost-inventory/', data),
        fifoPreview: (productId, quantity) => {
            const query = new URLSearchParams({ product_id: productId, quantity }).toString();
            return api.get(`/lost-inventory/fifo-preview/?${query}`);
        },
        markFound: (itemId, quantity, shelfAllocations = []) =>
            api.post(`/lost-inventory/items/${itemId}/found/`, {
                quantity,
                shelf_allocations: shelfAllocations,
            }),
    },
};