import { AnimatePresence } from 'framer-motion';
import PropTypes from 'prop-types';
import Toast from './Toast';

const ToastViewport = ({ toasts, onDismiss }) => {
    const errors = toasts.filter((t) => t.variant === 'error');
    const rest = toasts.filter((t) => t.variant !== 'error');

    return (
        <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2 w-full max-w-sm pointer-events-none">
            {/* Errors get an assertive live region so screen readers interrupt for them */}
            <div aria-live="assertive" className="contents">
                <AnimatePresence>
                    {errors.map((t) => (
                        <div key={t.id} className="pointer-events-auto">
                            <Toast {...t} onDismiss={() => onDismiss(t.id)} />
                        </div>
                    ))}
                </AnimatePresence>
            </div>
            <div role="status" aria-live="polite" className="contents">
                <AnimatePresence>
                    {rest.map((t) => (
                        <div key={t.id} className="pointer-events-auto">
                            <Toast {...t} onDismiss={() => onDismiss(t.id)} />
                        </div>
                    ))}
                </AnimatePresence>
            </div>
        </div>
    );
};

ToastViewport.propTypes = {
    toasts: PropTypes.array.isRequired,
    onDismiss: PropTypes.func.isRequired,
};

export default ToastViewport;
