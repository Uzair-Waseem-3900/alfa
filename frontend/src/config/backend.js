class BackendConfig {
    constructor() {
        this.baseURL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';
        this.timeout = 30000; // 30 seconds
        this.retryAttempts = 3;
        this.retryDelay = 1000;
    }

    getBaseURL() {
        return this.baseURL;
    }

    // Remove /api/v1 - just use /api
    getAPIURL() {
        return `${this.baseURL}/api`;
    }

    getEndpoint(endpoint) {
        return `${this.getAPIURL()}${endpoint}`;
    }

    getHeaders() {
        const token = localStorage.getItem('access_token');
        return {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            ...(token && { 'Authorization': `Bearer ${token}` }),
        };
    }

    getTimeout() {
        return this.timeout;
    }

    getRetryConfig() {
        return {
            attempts: this.retryAttempts,
            delay: this.retryDelay,
        };
    }

    isDevelopment() {
        return import.meta.env.MODE === 'development';
    }

    isProduction() {
        return import.meta.env.MODE === 'production';
    }

    getWebSocketURL() {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = new URL(this.baseURL);
        return `${wsProtocol}//${url.host}`;
    }
}

export const backendConfig = new BackendConfig();
export const getBaseURL = () => backendConfig.getBaseURL();
export const getAPIURL = () => backendConfig.getAPIURL();
export const getEndpoint = (endpoint) => backendConfig.getEndpoint(endpoint);
export const getHeaders = () => backendConfig.getHeaders();
export const getTimeout = () => backendConfig.getTimeout();