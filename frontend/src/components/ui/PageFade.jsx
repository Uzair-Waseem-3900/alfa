import { motion, useReducedMotion } from 'framer-motion';
import PropTypes from 'prop-types';

/**
 * Route-group fade. OPACITY ONLY — on purpose.
 *
 * The old PageTransition animated x/scale and set `will-change: transform` +
 * `overflow: hidden`. Any of those makes this wrapper the containing block for
 * `position: fixed` descendants, which broke the sidebar (scrolled with the
 * page, sized to content, clipped). Never add transform, filter, will-change,
 * perspective, contain or overflow here.
 */
const DURATION = 0.18;

const PageFade = ({ children }) => {
    const reduce = useReducedMotion();
    return (
        <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: reduce ? 0 : DURATION, ease: 'easeOut' }}
        >
            {children}
        </motion.div>
    );
};

PageFade.propTypes = {
    children: PropTypes.node.isRequired,
};

export default PageFade;
