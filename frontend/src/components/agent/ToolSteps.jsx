import PropTypes from 'prop-types';
import { AnimatePresence, motion } from 'framer-motion';
import { SPRING_POP } from '../../utils/motion';

// A tool call, shown as a pill:
//   running — a light travels around a gradient border, the label shimmers, a
//             soft ring "breathes" and a live dot ripples
//   done    — the tick draws itself in once, a single ripple confirms it, and the
//             pill settles into a quiet neutral chip
// All loops are CSS (index.css) so they cost nothing while tokens stream in.

const chipVariants = {
    hidden: { opacity: 0, scale: 0.8, x: -10 },
    show:   { opacity: 1, scale: 1,   x: 0, transition: SPRING_POP },
    exit:   { opacity: 0, scale: 0.9, transition: { duration: 0.15, ease: 'easeIn' } },
};

const RunningDot = () => (
    <span className="relative flex h-2.5 w-2.5 flex-shrink-0" aria-hidden="true">
        <span className="agent-ripple absolute inset-0 rounded-full bg-accent-500" />
        <span className="relative h-2.5 w-2.5 rounded-full bg-accent-600" />
    </span>
);

const DoneTick = () => (
    <span className="relative flex h-4 w-4 flex-shrink-0 items-center justify-center" aria-hidden="true">
        {/* one-shot confirmation ripple */}
        <motion.span
            className="absolute inset-0 rounded-full bg-success-500"
            initial={{ scale: 0.6, opacity: 0.5 }}
            animate={{ scale: 2.2, opacity: 0 }}
            transition={{ duration: 0.7, ease: 'easeOut' }}
        />
        <motion.span
            className="absolute inset-0 rounded-full bg-success-50"
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={SPRING_POP}
        />
        <svg viewBox="0 0 16 16" className="relative h-3 w-3 text-success-600" fill="none">
            <motion.path
                d="M3.5 8.5l3 3 6-7"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                initial={{ pathLength: 0 }}
                animate={{ pathLength: 1 }}
                transition={{ duration: 0.32, ease: 'easeOut', delay: 0.08 }}
            />
        </svg>
    </span>
);

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
                        className={`rounded-full ${
                            step.done
                                ? 'p-px bg-neutral-200'
                                : 'p-px bg-gradient-to-r from-accent-200 via-accent-500 to-accent-200 agent-sheen-border agent-breathe'
                        }`}
                    >
                        <span className={`flex items-center gap-2 rounded-full bg-white py-1 pl-2.5 pr-3 text-xs font-medium ${
                            step.done ? 'text-neutral-500' : ''
                        }`}>
                            {step.done ? <DoneTick /> : <RunningDot />}
                            <span className={step.done ? '' : 'agent-sheen-text bg-gradient-to-r from-neutral-500 via-accent-600 to-neutral-500'}>
                                {step.label}
                            </span>
                        </span>
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
