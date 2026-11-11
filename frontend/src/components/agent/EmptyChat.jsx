import PropTypes from 'prop-types';
import { Wallet, Users, PackageSearch, TrendingUp } from 'lucide-react';
import { AssistantAvatar } from './MessageBubble';

const SUGGESTIONS = [
    { icon: Wallet, title: 'Cash position', prompt: 'How much cash do we have right now?' },
    { icon: Users, title: 'Who owes us', prompt: 'Which customers owe us the most money?' },
    { icon: PackageSearch, title: 'Stock alerts', prompt: 'Which products are low or out of stock?' },
    { icon: TrendingUp, title: 'This month', prompt: 'Summarise this month’s sales and profit.' },
];

const EmptyChat = ({ assistantName, companyName, onPick, disabled }) => (
    <div className="flex flex-col items-center justify-center text-center px-4 py-10 min-h-full">
        <AssistantAvatar className="!w-12 !h-12 mb-4" />
        <h2 className="text-2xl font-bold text-neutral-900">How can I help today?</h2>
        <p className="mt-2 max-w-md text-sm text-neutral-500">
            I’m {assistantName}. Ask me anything about {companyName}’s sales, stock, customers, payables, expenses or profit —
            I read your live data.
        </p>

        <div className="mt-8 grid w-full max-w-2xl grid-cols-1 sm:grid-cols-2 gap-3">
            {SUGGESTIONS.map(({ icon: Icon, title, prompt }) => (
                <button
                    key={title}
                    type="button"
                    disabled={disabled}
                    onClick={() => onPick(prompt)}
                    className="group flex items-start gap-3 rounded-xl border border-neutral-200 bg-white p-4 text-left transition-all duration-200 hover:border-accent-300 hover:bg-accent-50/40 hover:shadow-sm cursor-pointer min-h-[64px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    <span className="mt-0.5 flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-primary-50 text-primary-700 group-hover:bg-accent-100 group-hover:text-accent-700 transition-colors">
                        <Icon className="h-5 w-5" aria-hidden="true" />
                    </span>
                    <span className="min-w-0">
                        <span className="block text-sm font-semibold text-neutral-900">{title}</span>
                        <span className="block text-sm text-neutral-500">{prompt}</span>
                    </span>
                </button>
            ))}
        </div>
    </div>
);

EmptyChat.propTypes = {
    assistantName: PropTypes.string.isRequired,
    companyName: PropTypes.string.isRequired,
    onPick: PropTypes.func.isRequired,
    disabled: PropTypes.bool,
};

export default EmptyChat;
