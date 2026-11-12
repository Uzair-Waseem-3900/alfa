import PropTypes from 'prop-types';
import { AnimatePresence, motion } from 'framer-motion';
import { Check, Loader2 } from 'lucide-react';

// ─── Variants ──────────────────────────────────────────────────────────────

const chipVariants = {
    hidden: { opacity: 0, scale: 0.75, y: 6 },
    show: {
        opacity: 1, scale: 1, y: 0,
        transition: { type: 'spring', stiffness: 480, damping: 26 },
    },
    exit: {
        opacity: 0, scale: 0.85, y: -4,
        transition: { duration: 0.18, ease: 'easeIn' },
    },
};

const iconVariants = {
    hidden: { opacity: 0, scale: 0.4, rotate: -30 },
    show: {
        opacity: 1, scale: 1, rotate: 0,
        transition: { type: 'spring', stiffness: 600, damping: 22 },
    },
};

// ─── ToolSteps ─────────────────────────────────────────────────────────────

const ToolSteps = ({ steps }) => {
    if (!steps?.length) return null;

    return (
        <ul className="flex flex-wrap gap-2 mb-3" aria-label="Assistant activity">
            <AnimatePresence initial={false}>
                {steps.map((step) => (
                    <motion.li
                        key={step.id}
                        variants={chipVariants}
                        initial="hidden"
                        animate="show"
                        exit="exit"
                        layout
                        className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium ${
                            step.done
                                ? 'border-neutral-200 bg-neutral-50 text-neutral-500'
                                : 'border-accent-200 bg-accent-50 text-accent-700'
                        }`}
                    >
                        {/* Icon swaps smoothly between spinner and check */}
                        <AnimatePresence mode="wait" initial={false}>
                            {step.done ? (
                                <motion.span
                                    key="done"
                                    variants={iconVariants}
                                    initial="hidden"
                                    animate="show"
                                >
                                    <Check className="w-3.5 h-3.5 text-success-600" aria-hidden="true" />
                                </motion.span>
                            ) : (
                                <motion.span
                                    key="spinning"
                                    initial={{ opacity: 0 }}
                                    animate={{ opacity: 1 }}
                                    exit={{ opacity: 0 }}
                                    transition={{ duration: 0.15 }}
                                >
                                    <Loader2 className="w-3.5 h-3.5 animate-spin motion-reduce:animate-none" aria-hidden="true" />
                                </motion.span>
                            )}
                        </AnimatePresence>

                        {step.label}
                    </motion.li>
                ))}
            </AnimatePresence>
        </ul>
    );
};

ToolSteps.propTypes = {
    steps: PropTypes.arrayOf(PropTypes.shape({
        id:    PropTypes.string.isRequired,
        label: PropTypes.string.isRequired,
        done:  PropTypes.bool,
    })),
};

export default ToolSteps;
