import PropTypes from 'prop-types';
import { Link } from 'react-router-dom';
import { ArrowLeft, PanelLeft, SquarePen } from 'lucide-react';
import { AssistantAvatar } from './MessageBubble';

const AgentHeader = ({ assistantName, sidebarOpen, onToggleSidebar, onNewChat }) => (
    <header className="flex-shrink-0 h-14 flex items-center gap-1 sm:gap-2 px-2 sm:px-4 border-b border-neutral-200 bg-white/90 backdrop-blur">
        <button
            type="button"
            onClick={onToggleSidebar}
            aria-label={sidebarOpen ? 'Hide chat history' : 'Show chat history'}
            aria-expanded={sidebarOpen}
            className="w-11 h-11 flex items-center justify-center rounded-lg text-neutral-600 hover:bg-neutral-100 active:bg-neutral-200 cursor-pointer transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500"
        >
            <PanelLeft className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-2.5 min-w-0">
            <AssistantAvatar />
            <div className="min-w-0 leading-tight">
                <h1 className="text-sm font-semibold text-neutral-900 truncate">{assistantName}</h1>
                <p className="hidden sm:block text-xs text-neutral-500">Business assistant</p>
            </div>
        </div>

        <div className="flex-1" />

        <button
            type="button"
            onClick={onNewChat}
            aria-label="New chat"
            className="md:hidden w-11 h-11 flex items-center justify-center rounded-lg text-neutral-600 hover:bg-neutral-100 active:bg-neutral-200 cursor-pointer"
        >
            <SquarePen className="w-5 h-5" />
        </button>

        <Link
            to="/dashboard"
            className="inline-flex items-center gap-1.5 rounded-lg border border-primary-200 bg-primary-50 px-3 min-h-[44px] text-sm font-medium text-primary-700 hover:bg-primary-100 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500"
        >
            <ArrowLeft className="w-4 h-4" aria-hidden="true" />
            <span className="sm:hidden">Back</span>
            <span className="hidden sm:inline">Back to software</span>
        </Link>
    </header>
);

AgentHeader.propTypes = {
    assistantName: PropTypes.string.isRequired,
    sidebarOpen: PropTypes.bool.isRequired,
    onToggleSidebar: PropTypes.func.isRequired,
    onNewChat: PropTypes.func.isRequired,
};

export default AgentHeader;
