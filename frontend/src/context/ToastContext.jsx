import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';
import ToastViewport from '../components/ui/ToastViewport';

const ToastContext = createContext();

export const useToast = () => {
    const context = useContext(ToastContext);
    if (!context) {
        throw new Error('useToast must be used within ToastProvider');
    }
    return context;
};

const DEFAULT_DURATION = { success: 5000, info: 5000, warning: 6000, error: 8000 };

export const ToastProvider = ({ children }) => {
    const [toasts, setToasts] = useState([]);
    const idRef = useRef(0);

    const removeToast = useCallback((id) => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
    }, []);

    const addToast = useCallback(({ variant = 'info', message, duration }) => {
        idRef.current += 1;
        const id = idRef.current;
        const toast = {
            id,
            variant,
            message,
            duration: duration ?? DEFAULT_DURATION[variant] ?? DEFAULT_DURATION.info,
        };
        setToasts((prev) => [...prev, toast]);
        return id;
    }, []);

    const toast = useMemo(() => ({
        show: addToast,
        success: (message, opts) => addToast({ ...opts, variant: 'success', message }),
        error: (message, opts) => addToast({ ...opts, variant: 'error', message }),
        warning: (message, opts) => addToast({ ...opts, variant: 'warning', message }),
        info: (message, opts) => addToast({ ...opts, variant: 'info', message }),
    }), [addToast]);

    const value = useMemo(() => ({ toast, dismiss: removeToast }), [toast, removeToast]);

    return (
        <ToastContext.Provider value={value}>
            {children}
            <ToastViewport toasts={toasts} onDismiss={removeToast} />
        </ToastContext.Provider>
    );
};
