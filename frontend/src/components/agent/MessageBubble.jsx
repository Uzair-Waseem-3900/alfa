import { memo } from 'react';
import PropTypes from 'prop-types';
import { motion } from 'framer-motion';
import { Sparkles } from 'lucide-react';
import MarkdownContent from './MarkdownContent';
import ToolSteps from './ToolSteps';
import InlineAlert from '../ui/InlineAlert';

// ─── Avatar ────────────────────────────────────────────────────────────────

export const AssistantAvatar = ({ className = '' }) => (
    <div
        className={`w-8 h-8 rounded-full bg-gradient-to-br from-primary-600 to-accent-600 flex items-center justify-center flex-shrink-0 ${className}`}
        aria-hidden="true"
    >
        <Sparkles className="w-4 h-4 text-white" />
    </div>
);

AssistantAvatar.propTypes = { className: PropTypes.string };

// ─── Thinking dots ─────────────────────────────────────────────────────────

const ThinkingDots = () => (
    <div className="flex items-center gap-1.5 py-2" role="status" aria-label="Assistant is thinking">
        {[0, 1, 2].map((i) => (
            <motion.span
                key={i}
                className="w-2 h-2 rounded-full bg-neutral-300 motion-reduce:animate-none"
                animate={{ y: [0, -5, 0] }}
                transition={{ duration: 0.7, repeat: Infinity, delay: i * 0.15, ease: 'easeInOut' }}
            />
        ))}
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

const MessageBubble = ({ message, assistantName, onRetry }) => {
    if (message.role === 'user') {
        return (
            <motion.div className="flex justify-end" variants={userVariants} initial="hidden" animate="show">
                <div className="max-w-[85%] sm:max-w-[75%] rounded-2xl rounded-br-md bg-primary-50 border border-primary-100 px-4 py-2.5 text-[15px] leading-7 text-neutral-900 whitespace-pre-wrap break-words">
                    {message.text}
                </div>
            </motion.div>
        );
    }

    const streaming = message.status === 'streaming';
    const waiting   = streaming && !message.text && !message.steps?.length;

    return (
        <motion.div className="flex gap-3" aria-busy={streaming} variants={assistantVariants} initial="hidden" animate="show">
            <motion.div variants={avatarVariants}>
                <AssistantAvatar className="mt-0.5" />
            </motion.div>

            <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold text-neutral-500 mb-1">{assistantName}</p>

                <ToolSteps steps={message.steps} />

                {waiting && <ThinkingDots />}

                {message.text && <MarkdownContent text={message.text} />}

                {streaming && message.text && (
                    <motion.span
                        className="inline-block w-2 h-4 ml-0.5 align-middle bg-primary-400 rounded-sm motion-reduce:animate-none"
                        animate={{ opacity: [1, 0, 1] }}
                        transition={{ duration: 0.9, repeat: Infinity, ease: 'easeInOut' }}
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
};

export default memo(MessageBubble);
