import { useRef, useState } from 'react';
import PropTypes from 'prop-types';
import { ArrowUp, Loader2 } from 'lucide-react';

const MAX_CHARS = 2000;      // mirrors AGENT_MAX_INPUT_CHARS on the backend
const MAX_HEIGHT_PX = 160;

const Composer = ({ onSend, disabled, busy, assistantName }) => {
    const [value, setValue] = useState('');
    const textareaRef = useRef(null);
    const canSend = !disabled && !busy && value.trim().length > 0;

    const resize = () => {
        const el = textareaRef.current;
        if (!el) return;
        el.style.height = 'auto';
        el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT_PX)}px`;
    };

    const submit = () => {
        if (!canSend) return;
        onSend(value.trim());
        setValue('');
        requestAnimationFrame(resize);
    };

    const handleKeyDown = (e) => {
        // Enter sends, Shift+Enter = new line; never send mid-IME composition.
        if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            submit();
        }
    };

    return (
        <div className="px-3 sm:px-4 pt-2 pb-3 bg-gradient-to-t from-white via-white to-white/0">
            <form
                onSubmit={(e) => { e.preventDefault(); submit(); }}
                className="max-w-3xl mx-auto flex items-end gap-2 rounded-2xl border border-neutral-300 bg-white p-2 shadow-sm transition-shadow focus-within:border-accent-500 focus-within:ring-2 focus-within:ring-accent-500/25"
            >
                <label htmlFor="agent-composer" className="sr-only">Message {assistantName}</label>
                <textarea
                    id="agent-composer"
                    ref={textareaRef}
                    rows={1}
                    value={value}
                    maxLength={MAX_CHARS}
                    disabled={disabled}
                    onChange={(e) => { setValue(e.target.value); resize(); }}
                    onKeyDown={handleKeyDown}
                    placeholder={`Ask ${assistantName} about your business…`}
                    // 16px: anything smaller makes iOS Safari zoom the page on focus.
                    className="flex-1 resize-none bg-transparent px-2 py-2.5 text-base leading-6 text-neutral-900 placeholder:text-neutral-400 focus:outline-none disabled:opacity-60"
                    style={{ maxHeight: MAX_HEIGHT_PX }}
                />
                <button
                    type="submit"
                    disabled={!canSend}
                    aria-label={busy ? `${assistantName} is answering` : 'Send message'}
                    className="w-11 h-11 flex-shrink-0 rounded-xl flex items-center justify-center text-white bg-gradient-to-r from-primary-700 to-accent-600 hover:from-primary-800 hover:to-accent-700 transition-all duration-200 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 focus-visible:ring-offset-2 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                    {busy ? <Loader2 className="w-5 h-5 animate-spin motion-reduce:animate-none" /> : <ArrowUp className="w-5 h-5" />}
                </button>
            </form>
            <p className="max-w-3xl mx-auto mt-2 text-center text-xs text-neutral-500">
                {value.length > MAX_CHARS * 0.8 && (
                    <span className="mr-2 font-medium text-warning-700">{value.length}/{MAX_CHARS}</span>
                )}
                Answers come from your live data and are internal estimates, not certified figures. Check anything important.
            </p>
        </div>
    );
};

Composer.propTypes = {
    onSend: PropTypes.func.isRequired,
    disabled: PropTypes.bool,
    busy: PropTypes.bool,
    assistantName: PropTypes.string.isRequired,
};

export default Composer;
