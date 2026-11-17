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
// Short on purpose: the premium part of a page switch is each screen assembling itself (header drops, history
// slides, body rises, mode switch glides); this only gets the old screen out of the way.
const ENTER = 0.22;
const EXIT = 0.12;

const PageFade = ({ children }) => {
    const reduce = useReducedMotion();
    return (
        <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, transition: { duration: reduce ? 0 : EXIT, ease: 'easeIn' } }}
            transition={{ duration: reduce ? 0 : ENTER, ease: 'easeOut' }}
        >
            {children}
        </motion.div>
    );
};

PageFade.propTypes = {
    children: PropTypes.node.isRequired,
};

export default PageFade;
