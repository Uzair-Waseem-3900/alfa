import PropTypes from 'prop-types';

// The two product marks (public/agent_icon.png, public/bulk_invoices_icon.png), drawn like an icon: pass the same
// className you would give a lucide icon (e.g. "w-4 h-4"). Used wherever the assistant / bulk invoices are represented.
import { ICON_SRC } from '../../utils/agentIcons';

const AgentIcon = ({ className = 'w-4 h-4', name = 'agent' }) => (
    <img src={ICON_SRC[name]} alt="" aria-hidden="true" draggable={false}
        className={`${className} rounded-md object-cover select-none`} />
);

AgentIcon.propTypes = { className: PropTypes.string, name: PropTypes.oneOf(['agent', 'bulk']) };

export const BulkIcon = ({ className }) => <AgentIcon name="bulk" className={className} />;
BulkIcon.propTypes = { className: PropTypes.string };

export default AgentIcon;
