import { motion } from 'framer-motion';
import PropTypes from 'prop-types';

/**
 * Wraps a page with an enter/exit animation.
 *
 * variant="agent"  — used when entering or leaving the AI agent view.
 *                    Slides in from the right with a slight scale-up so it
 *                    feels like a full-screen panel opening over the app.
 *                    Exits the same way (slides right, fades out).
 *
 * variant="app"    — used for the main software. Slides in from the left
 *                    (the natural "going back" direction) so returning from
 *                    the agent feels like stepping back into the app.
 *
 * Both variants share the same duration so the outgoing and incoming pages
 * stay in sync via AnimatePresence mode="wait".
 */

const DURATION = 0.3;
const EASE = [0.4, 0, 0.2, 1]; // material easing

const variants = {
    agent: {
        initial: { opacity: 0, x: 48, scale: 0.98 },
        animate: { opacity: 1, x: 0, scale: 1 },
        exit:    { opacity: 0, x: 48, scale: 0.98 },
    },
    app: {
        initial: { opacity: 0, x: -48, scale: 0.98 },
        animate: { opacity: 1, x: 0, scale: 1 },
        exit:    { opacity: 0, x: -48, scale: 0.98 },
    },
};

const PageTransition = ({ children, variant = 'app' }) => {
    const v = variants[variant] ?? variants.app;

    return (
        <motion.div
            initial={v.initial}
            animate={v.animate}
            exit={v.exit}
            transition={{ duration: DURATION, ease: EASE }}
            // Prevent the exiting layer from creating a horizontal scrollbar
            style={{ willChange: 'opacity, transform', overflow: 'hidden' }}
        >
            {children}
        </motion.div>
    );
};

PageTransition.propTypes = {
    children: PropTypes.node.isRequired,
    variant:  PropTypes.oneOf(['agent', 'app']),
};

export default PageTransition;
