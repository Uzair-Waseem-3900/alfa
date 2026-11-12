import PropTypes from 'prop-types';
import { motion } from 'framer-motion';
import { Wallet, Users, PackageSearch, TrendingUp } from 'lucide-react';
import { AssistantAvatar } from './MessageBubble';

const SUGGESTIONS = [
    { icon: Wallet,        title: 'Cash position', prompt: 'How much cash do we have right now?' },
    { icon: Users,         title: 'Who owes us',   prompt: 'Which customers owe us the most money?' },
    { icon: PackageSearch, title: 'Stock alerts',  prompt: 'Which products are low or out of stock?' },
    { icon: TrendingUp,    title: 'This month',    prompt: 'Summarise this month\u2019s sales and profit.' },
];

// ─── variants ──────────────────────────────────────────────────────────────

const container = {
    hidden: {},
    show: {
        transition: { staggerChildren: 0.08, delayChildren: 0.18 },
    },
};

const fadeUp = {
    hidden: { opacity: 0, y: 20, scale: 0.97 },
    show:   { opacity: 1, y: 0,  scale: 1,
        transition: { type: 'spring', stiffness: 340, damping: 26 } },
};

const headerFade = {
    hidden: { opacity: 0, y: 14 },
    show:   { opacity: 1, y: 0,
        transition: { type: 'spring', stiffness: 300, damping: 24, delay: 0.06 } },
};

// Subtle continuous float for the avatar
const floatTransition = {
    duration: 3.2,
    repeat: Infinity,
    repeatType: 'mirror',
    ease: 'easeInOut',
};

// ─── Component ─────────────────────────────────────────────────────────────

const EmptyChat = ({ assistantName, companyName, onPick, disabled }) => (
    <motion.div
        className="flex flex-col items-center justify-center text-center px-4 py-10 min-h-full"
        initial="hidden"
        animate="show"
        variants={container}
    >
        {/* Avatar — floats gently */}
        <motion.div
            animate={{ y: [0, -6, 0] }}
            transition={floatTransition}
            className="mb-4"
        >
            <AssistantAvatar className="!w-12 !h-12" />
        </motion.div>

        {/* Heading + subtext */}
        <motion.div variants={headerFade}>
            <h2 className="text-2xl font-bold text-neutral-900">How can I help today?</h2>
            <p className="mt-2 max-w-md text-sm text-neutral-500">
                I&apos;m {assistantName}. Ask me anything about {companyName}&apos;s sales, stock, customers,
                payables, expenses or profit — I read your live data.
            </p>
        </motion.div>

        {/* Suggestion cards — staggered */}
        <motion.div
            className="mt-8 grid w-full max-w-2xl grid-cols-1 sm:grid-cols-2 gap-3"
            variants={container}
        >
            {SUGGESTIONS.map(({ icon: Icon, title, prompt }) => (
                <motion.button
                    key={title}
                    variants={fadeUp}
                    whileHover={{
                        scale: 1.025,
                        boxShadow: '0 6px 24px 0 rgba(0,0,0,0.08)',
                        transition: { type: 'spring', stiffness: 500, damping: 22 },
                    }}
                    whileTap={{ scale: 0.96 }}
                    type="button"
                    disabled={disabled}
                    onClick={() => onPick(prompt)}
                    className="group flex items-start gap-3 rounded-xl border border-neutral-200 bg-white p-4 text-left transition-colors duration-200 hover:border-accent-300 hover:bg-accent-50/40 cursor-pointer min-h-[64px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    <motion.span
                        whileHover={{ rotate: [0, -12, 10, 0] }}
                        transition={{ duration: 0.4 }}
                        className="mt-0.5 flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-primary-50 text-primary-700 group-hover:bg-accent-100 group-hover:text-accent-700 transition-colors"
                    >
                        <Icon className="h-5 w-5" aria-hidden="true" />
                    </motion.span>
                    <span className="min-w-0">
                        <span className="block text-sm font-semibold text-neutral-900">{title}</span>
                        <span className="block text-sm text-neutral-500">{prompt}</span>
                    </span>
                </motion.button>
            ))}
        </motion.div>
    </motion.div>
);

EmptyChat.propTypes = {
    assistantName: PropTypes.string.isRequired,
    companyName:   PropTypes.string.isRequired,
    onPick:        PropTypes.func.isRequired,
    disabled:      PropTypes.bool,
};

export default EmptyChat;
