import PropTypes from 'prop-types';

// The assistant's own mark (public/agent_icon.png), drawn like an icon: pass the same className you would give a
// lucide icon (e.g. "w-4 h-4"). Used wherever the assistant is represented, instead of a generic sparkle.
const AgentIcon = ({ className = 'w-4 h-4' }) => (
    <img src="/agent_icon.png" alt="" aria-hidden="true" draggable={false}
        className={`${className} rounded-md object-cover select-none`} />
);

AgentIcon.propTypes = { className: PropTypes.string };

export default AgentIcon;
