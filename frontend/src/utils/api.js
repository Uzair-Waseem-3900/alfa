import axios from 'axios';
import { backendConfig } from '../config';

// Create axios instance
const apiClient = axios.create({
    baseURL: backendConfig.getAPIURL(),
    timeout: backendConfig.getTimeout(),
    headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    },
});

// Request interceptor
apiClient.interceptors.request.use(
    (config) => {
        const token = localStorage.getItem('access_token');
        if (token) {
            config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
    },
    (error) => Promise.reject(error)
);

// Refresh is rotated server-side (ROTATE_REFRESH_TOKENS + BLACKLIST_AFTER_ROTATION) —
// the old refresh token is blacklisted the moment one refresh call succeeds. If several
// requests 401 at once, each firing its own refresh call would race: only the first
// lands before rotation, every other one reuses the now-blacklisted token and fails.
// Sharing a single in-flight promise means concurrent 401s all wait on the SAME refresh
// call instead of each spending the refresh token themselves.
let refreshPromise = null;

const performTokenRefresh = () => {
    const refreshToken = localStorage.getItem('refresh_token');
    if (!refreshToken) {
        return Promise.reject(new Error('No refresh token available'));
    }
    return axios
        .post(`${backendConfig.getAPIURL()}/auth/token/refresh/`, { refresh: refreshToken })
        .then((response) => {
            const { access, refresh } = response.data;
            localStorage.setItem('access_token', access);
            // Must persist the rotated refresh token too — the old one is blacklisted
            // server-side as soon as this call succeeds, so leaving the stale value in
            // localStorage guarantees the NEXT refresh attempt fails.
            if (refresh) {
                localStorage.setItem('refresh_token', refresh);
            }
            return access;
        })
        .catch((refreshError) => {
            localStorage.removeItem('access_token');
            localStorage.removeItem('refresh_token');
            localStorage.removeItem('user');
            window.location.href = '/login';
            throw refreshError;
        })
        .finally(() => {
            refreshPromise = null;
        });
};

// Response interceptor
apiClient.interceptors.response.use(
    (response) => response.data,
    async (error) => {
        const originalRequest = error.config;

        if (error.response?.status === 401 && !originalRequest._retry) {
            originalRequest._retry = true;
            try {
                if (!refreshPromise) {
                    refreshPromise = performTokenRefresh();
                }
                const access = await refreshPromise;
                originalRequest.headers.Authorization = `Bearer ${access}`;
                return apiClient(originalRequest);
            } catch (refreshError) {
                return Promise.reject(refreshError);
            }
        }
        return Promise.reject(error);
    }
);

// Base API methods
export const api = {
    get: (url, config = {}) => apiClient.get(url, config),
    post: (url, data = {}, config = {}) => apiClient.post(url, data, config),
    put: (url, data = {}, config = {}) => apiClient.put(url, data, config),
    patch: (url, data = {}, config = {}) => apiClient.patch(url, data, config),
    delete: (url, config = {}) => apiClient.delete(url, config),
};

// ==================== AUTH API ====================
export const authApi = {
    login: (email, password) => api.post('/auth/login/', { email, password }),
    logout: (refreshToken) => api.post('/auth/logout/', { refresh: refreshToken }),
    refreshToken: (refresh) => api.post('/auth/token/refresh/', { refresh }),
};

// ==================== USERS API ====================
export const usersApi = {
    getAll: (params = {}) => api.get('/users/', { params }),
    create: (userData) => api.post('/users/', userData),
    delete: (email) => api.delete(`/users/${email}/delete/`),
    getProfile: () => api.get('/users/me/'),
    updateProfile: (data) => api.patch('/users/me/', data), // PATCH for profile
    changeOwnPassword: (data) => api.patch('/users/me/change-password/', data),
    changeUserPassword: (data) => api.patch('/users/change-password/', data),
};

// ==================== PURCHASES API ====================

// Categories
export const categoriesApi = {
    getAll: () => api.get('/categories/'),
    create: (data) => api.post('/categories/', data),
    update: (id, data) => api.put(`/categories/${id}/`, data), // PUT is allowed for categories
    delete: (id) => api.delete(`/categories/${id}/`),
};

// Shelves
export const shelvesApi = {
    getAll: () => api.get('/shelves/'),
    create: (data) => api.post('/shelves/', data),
    update: (id, data) => api.put(`/shelves/${id}/`, data), // PUT is allowed for shelves
    delete: (id) => api.delete(`/shelves/${id}/`),
};

// Suppliers - Uses PATCH for updates (http_method_names = ["get", "patch", "delete"])
export const suppliersApi = {
    getAll: (params = {}) => api.get('/suppliers/', { params }),
    getOutstanding: (params = {}) => api.get('/suppliers/outstanding/', { params }),
    getById: (id) => api.get(`/suppliers/${id}/`),
    create: (data) => api.post('/suppliers/', data),
    update: (id, data) => api.patch(`/suppliers/${id}/`, data), // PATCH not PUT
    delete: (id) => api.delete(`/suppliers/${id}/`),
    getPayableSummary: (id) => api.get(`/suppliers/${id}/payable-summary/`),
    getOutstandingOrders: (id) => api.get(`/suppliers/${id}/outstanding-orders/`),
};

// Products
export const productsApi = {
    getAll: (params = {}) => api.get('/products/', { params }),
    getById: (id) => api.get(`/products/${id}/`),
    create: (data) => api.post('/products/', data),
    update: (id, data) => api.put(`/products/${id}/`, data), // PUT is allowed for products
    delete: (id) => api.delete(`/products/${id}/`),
};

// Purchase Orders
export const purchaseOrdersApi = {
    getAll: (params = {}) => api.get('/orders/', { params }),
    getDrafts: () => api.get('/orders/drafts/'),
    getConfirmed: () => api.get('/orders/confirmed/'),
    getOutstanding: () => api.get('/orders/outstanding/'),
    getById: (id) => api.get(`/orders/${id}/`),
    create: (data) => api.post('/orders/', data),
    update: (id, data) => api.put(`/orders/${id}/`, data), // PUT for draft updates
    delete: (id) => api.delete(`/orders/${id}/`),
    confirm: (id) => api.post(`/orders/${id}/confirm/`),
    getPaymentSummary: (id) => api.get(`/orders/${id}/payment-summary/`),
    print: (id, isDraft = false) => api.get(`/orders/${id}/print/?is_draft=${isDraft}`, { responseType: 'blob' }),
    savePDF: (id, data) => api.post(`/orders/${id}/pdf/save/`, data),
    getSavedPDFs: (id) => api.get(`/orders/${id}/pdf/`),
    deletePDF: (id) => api.delete(`/pdf/${id}/`),
};

// Payments
export const paymentsApi = {
    getAll: (params = {}) => api.get('/payments/', { params }),
    getByOrder: (orderId) => api.get(`/orders/${orderId}/payments/`),
    create: (orderId, data) => api.post(`/orders/${orderId}/payments/`, data),
    delete: (id) => api.delete(`/payments/${id}/`),
};

// Returns
export const returnsApi = {
    getAll: (params = {}) => api.get('/returns/', { params }),
    getByOrder: (orderId) => api.get(`/orders/${orderId}/returns/`),
    create: (orderId, data) => api.post(`/orders/${orderId}/returns/`, data),
    accept: (id) => api.post(`/returns/${id}/accept/`),
};

// Inventory
export const inventoryApi = {
    getAll: (params = {}) => api.get('/inventory/', { params }),
    getByProduct: (productId) => api.get(`/inventory/${productId}/`),
};

export default apiClient;