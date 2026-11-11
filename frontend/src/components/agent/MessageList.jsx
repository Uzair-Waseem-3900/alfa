import { useLayoutEffect, useRef, useState, useCallback } from 'react';
import PropTypes from 'prop-types';
import { ArrowDown, Loader2 } from 'lucide-react';
import MessageBubble from './MessageBubble';
import InlineAlert from '../ui/InlineAlert';

const STICK_THRESHOLD_PX = 120;

// Scrolls like a chat app: follows the stream while you're at the bottom,
// stops following the moment you scroll up (and offers a jump-to-latest
// button), and keeps your place when older messages are prepended.
const MessageList = ({
    messages, assistantName, loadingHistory, historyError,
    hasEarlier, loadingEarlier, onLoadEarlier, onRetryLast, resetKey, children,
}) => {
    const scrollRef = useRef(null);
    const stickRef = useRef(true);
    const anchorRef = useRef(null);           // scrollHeight before prepending older messages
    const [showJump, setShowJump] = useState(false);

    const last = messages[messages.length - 1];
    const contentVersion = `${messages.length}:${last?.text?.length ?? 0}:${last?.steps?.length ?? 0}:${last?.status ?? ''}`;

    // New conversation: follow the bottom again.
    useLayoutEffect(() => {
        stickRef.current = true;
        setShowJump(false);
    }, [resetKey]);

    useLayoutEffect(() => {
        const el = scrollRef.current;
        if (!el) return;
        if (anchorRef.current != null) {                      // older messages were prepended
            el.scrollTop += el.scrollHeight - anchorRef.current;
            anchorRef.current = null;
            return;
        }
        if (stickRef.current) el.scrollTop = el.scrollHeight;
    }, [contentVersion, loadingHistory]);

    const handleScroll = useCallback(() => {
        const el = scrollRef.current;
        if (!el) return;
        const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < STICK_THRESHOLD_PX;
        stickRef.current = nearBottom;
        setShowJump(!nearBottom);
    }, []);

    const jumpToLatest = () => {
        const el = scrollRef.current;
        if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    };

    const loadEarlier = () => {
        anchorRef.current = scrollRef.current?.scrollHeight ?? null;
        onLoadEarlier();
    };

    const lastUserText = [...messages].reverse().find((m) => m.role === 'user')?.text;

    return (
        <div className="relative flex-1 min-h-0">
            <div ref={scrollRef} onScroll={handleScroll} className="h-full overflow-y-auto overscroll-contain">
                {loadingHistory && messages.length === 0 ? (
                    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6" aria-hidden="true">
                        {[60, 85, 45].map((w, i) => (
                            <div key={i} className="flex gap-3">
                                <div className="w-8 h-8 rounded-full bg-neutral-200 animate-pulse motion-reduce:animate-none" />
                                <div className="flex-1 space-y-2 pt-1">
                                    <div className="h-3 rounded bg-neutral-200 animate-pulse motion-reduce:animate-none" style={{ width: `${w}%` }} />
                                    <div className="h-3 rounded bg-neutral-100 animate-pulse motion-reduce:animate-none" style={{ width: `${w - 20}%` }} />
                                </div>
                            </div>
                        ))}
                    </div>
                ) : historyError ? (
                    <div className="max-w-3xl mx-auto px-4 py-8">
                        <InlineAlert message={historyError} />
                    </div>
                ) : messages.length === 0 ? (
                    children
                ) : (
                    <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
                        {hasEarlier && (
                            <div className="flex justify-center">
                                <button
                                    type="button"
                                    onClick={loadEarlier}
                                    disabled={loadingEarlier}
                                    className="inline-flex items-center gap-2 rounded-full border border-neutral-200 bg-white px-4 py-2 min-h-[44px] text-sm font-medium text-neutral-600 hover:bg-neutral-50 cursor-pointer disabled:opacity-60"
                                >
                                    {loadingEarlier && <Loader2 className="w-4 h-4 animate-spin motion-reduce:animate-none" />}
                                    Load earlier messages
                                </button>
                            </div>
                        )}
                        {messages.map((m) => (
                            <MessageBubble
                                key={m.id}
                                message={m}
                                assistantName={assistantName}
                                onRetry={m === last && m.status === 'error' && lastUserText ? () => onRetryLast(lastUserText) : undefined}
                            />
                        ))}
                    </div>
                )}
            </div>

            {showJump && (
                <button
                    type="button"
                    onClick={jumpToLatest}
                    aria-label="Jump to latest message"
                    className="absolute bottom-3 left-1/2 -translate-x-1/2 w-11 h-11 rounded-full border border-neutral-200 bg-white shadow-md flex items-center justify-center text-neutral-600 hover:bg-neutral-50 cursor-pointer transition-opacity"
                >
                    <ArrowDown className="w-5 h-5" />
                </button>
            )}
        </div>
    );
};

MessageList.propTypes = {
    messages: PropTypes.array.isRequired,
    assistantName: PropTypes.string.isRequired,
    loadingHistory: PropTypes.bool,
    historyError: PropTypes.string,
    hasEarlier: PropTypes.bool,
    loadingEarlier: PropTypes.bool,
    onLoadEarlier: PropTypes.func.isRequired,
    onRetryLast: PropTypes.func.isRequired,
    resetKey: PropTypes.string,
    children: PropTypes.node,
};

export default MessageList;
