import PropTypes from 'prop-types';
import { AnimatePresence, motion } from 'framer-motion';

// Same behaviour and motion as the assistant's chat-history sidebar (ChatSidebar): a drawer that slides over the
// content on mobile, and an in-flow panel that collapses on desktop. Children are rendered in both.
const mobileVariants = {
    open:   { x: 0,       transition: { type: 'spring', stiffness: 320, damping: 30 } },
    closed: { x: '-100%', transition: { type: 'spring', stiffness: 320, damping: 32 } },
};

const SidebarShell = ({ open, onClose, label, children }) => (
    <>
        <AnimatePresence>
            {open && (
                <motion.div
                    key="scrim"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="fixed inset-0 z-30 bg-black/50 md:hidden"
                    onClick={onClose}
                    aria-hidden="true"
                />
            )}
        </AnimatePresence>

        <motion.aside
            aria-label={label}
            variants={mobileVariants}
            initial={false}
            animate={open ? 'open' : 'closed'}
            className="md:hidden fixed inset-y-0 left-0 z-40 w-[85vw] max-w-xs flex flex-col bg-neutral-50 border-r border-neutral-200"
        >
            {children}
        </motion.aside>

        <motion.aside
            aria-label={label}
            aria-hidden={!open}
            initial={false}
            animate={{ width: open ? 288 : 0, opacity: open ? 1 : 0 }}   // 288px = w-72
            transition={{ type: 'spring', stiffness: 300, damping: 32 }}
            className="hidden md:flex flex-col bg-neutral-50 border-r border-neutral-200 overflow-hidden flex-shrink-0"
        >
            {/* full width inside, so text does not reflow while the panel collapses */}
            <div className="w-72 flex flex-col h-full">{children}</div>
        </motion.aside>
    </>
);

SidebarShell.propTypes = {
    open: PropTypes.bool.isRequired,
    onClose: PropTypes.func.isRequired,
    label: PropTypes.string.isRequired,
    children: PropTypes.node,
};

export default SidebarShell;
