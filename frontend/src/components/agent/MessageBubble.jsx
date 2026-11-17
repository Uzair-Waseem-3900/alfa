import { memo } from 'react';
import PropTypes from 'prop-types';
import { AnimatePresence, motion } from 'framer-motion';
import { Sparkles } from 'lucide-react';
import MarkdownContent from './MarkdownContent';
import ToolSteps from './ToolSteps';
import InlineAlert from '../ui/InlineAlert';

// ─── Avatar ────────────────────────────────────────────────────────────────

export const AssistantAvatar = ({ className = '', active = false }) => (
    <div className={`relative w-8 h-8 flex-shrink-0 ${className}`} aria-hidden="true">
        {/* Live ring: only while the assistant is working on an answer */}
        <AnimatePresence>
            {active && (
                <motion.span
                    key="ring"
                    className="agent-ripple absolute inset-0 rounded-full bg-accent-500"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                />
            )}
        </AnimatePresence>
        <div className={`relative w-full h-full rounded-full bg-gradient-to-br from-primary-600 to-accent-600 flex items-center justify-center ${active ? 'agent-glow' : ''}`}>
            <motion.span
                className="inline-flex"
                animate={active ? { rotate: [0, 14, -10, 0], scale: [1, 1.15, 1] } : { rotate: 0, scale: 1 }}
                transition={active ? { duration: 1.8, repeat: Infinity, ease: 'easeInOut' } : { duration: 0.2 }}
            >
                <Sparkles className="w-4 h-4 text-white" />
            </motion.span>
        </div>
    </div>
);

AssistantAvatar.propTypes = { className: PropTypes.string, active: PropTypes.bool };

// ─── Thinking dots ─────────────────────────────────────────────────────────

const ThinkingDots = () => (
    <div className="flex items-center gap-2.5 py-2" role="status" aria-label="Assistant is thinking">
        <div className="flex items-center gap-1" aria-hidden="true">
            {[0, 1, 2].map((i) => (
                <motion.span
                    key={i}
                    className="w-1.5 h-1.5 rounded-full bg-accent-500"
                    animate={{ y: [0, -4, 0], opacity: [0.35, 1, 0.35] }}
                    transition={{ duration: 0.9, repeat: Infinity, delay: i * 0.14, ease: 'easeInOut' }}
                />
            ))}
        </div>
        <span className="agent-sheen-text bg-gradient-to-r from-neutral-400 via-accent-600 to-neutral-400 text-sm font-medium">
            Thinking
        </span>
    </div>
);

// ─── Variants ──────────────────────────────────────────────────────────────

const userVariants = {
    hidden: { opacity: 0, x: 24, scale: 0.97 },
    show:   { opacity: 1, x: 0,  scale: 1,
        transition: { type: 'spring', stiffness: 380, damping: 28 } },
};

const assistantVariants = {
    hidden: { opacity: 0, x: -20, y: 8 },
    show:   { opacity: 1, x: 0,   y: 0,
        transition: { type: 'spring', stiffness: 340, damping: 26 } },
};

const avatarVariants = {
    hidden: { opacity: 0, scale: 0.5 },
    show:   { opacity: 1, scale: 1,
        transition: { type: 'spring', stiffness: 500, damping: 22, delay: 0.04 } },
};

// ─── MessageBubble ─────────────────────────────────────────────────────────

const MessageBubble = ({ message, assistantName, onRetry, instant = false }) => {
    // Messages that were already stored (history, or the optimistic turn being swapped for its stored copy)
    // appear in place: replaying the entrance would flash the whole conversation each time one answer finishes.
    const initial = instant ? false : 'hidden';
    if (message.role === 'user') {
        return (
            <motion.div className="flex justify-end" variants={userVariants} initial={initial} animate="show">
                <div className="max-w-[85%] sm:max-w-[75%] rounded-2xl rounded-br-md bg-primary-50 border border-primary-100 px-4 py-2.5 text-[15px] leading-7 text-neutral-900 whitespace-pre-wrap break-words">
                    {message.text}
                </div>
            </motion.div>
        );
    }

    const streaming = message.status === 'streaming';
    const waiting   = streaming && !message.text && !message.steps?.length;

    return (
        <motion.div className="flex gap-3" aria-busy={streaming} variants={assistantVariants} initial={initial} animate="show">
            <motion.div variants={avatarVariants}>
                <AssistantAvatar className="mt-0.5" active={streaming} />
            </motion.div>

            <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold text-neutral-500 mb-1">{assistantName}</p>

                <ToolSteps steps={message.steps} finished={!streaming} />

                {waiting && <ThinkingDots />}

                {message.text && <MarkdownContent text={message.text} />}

                {streaming && message.text && (
                    <motion.span
                        className="inline-block w-[3px] h-4 ml-0.5 align-middle rounded-full bg-gradient-to-b from-accent-400 to-primary-600 shadow-[0_0_8px_2px] shadow-accent-500/40"
                        animate={{ opacity: [1, 0.25, 1] }}
                        transition={{ duration: 1, repeat: Infinity, ease: 'easeInOut' }}
                        aria-hidden="true"
                    />
                )}

                {message.status === 'error' && (
                    <InlineAlert
                        className="mt-3"
                        message={message.error || 'Something went wrong while answering.'}
                        onRetry={onRetry}
                        retryLabel="Try again"
                    />
                )}
            </div>
        </motion.div>
    );
};

MessageBubble.propTypes = {
    message: PropTypes.shape({
        id:     PropTypes.oneOfType([PropTypes.number, PropTypes.string]).isRequired,
        role:   PropTypes.oneOf(['user', 'assistant']).isRequired,
        text:   PropTypes.string,
        steps:  PropTypes.array,
        status: PropTypes.string,
        error:  PropTypes.string,
    }).isRequired,
    assistantName: PropTypes.string.isRequired,
    onRetry:       PropTypes.func,
    instant:       PropTypes.bool,
};

export default memo(MessageBubble);
