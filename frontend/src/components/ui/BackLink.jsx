import { Link } from 'react-router-dom';
import PropTypes from 'prop-types';
import { ArrowLeft, ArrowRight } from 'lucide-react';

// Standard navigational "pill" link — replaces plain colored text (which
// reads as inert text, not something clickable) with a clear button-like
// affordance. `direction="left"` (default) puts the arrow before the label
// for "back to X" links; `direction="right"` puts it after, for "forward
// to X" links.
const BackLink = ({ to, children, direction = 'left', className = '' }) => {
    const Icon = direction === 'left' ? ArrowLeft : ArrowRight;

    return (
        <Link
            to={to}
            className={`inline-flex items-center gap-1.5 text-sm font-medium text-primary-700 bg-primary-50 hover:bg-primary-100 border border-primary-200 rounded-lg px-3 py-1.5 transition-colors ${className}`}
        >
            {direction === 'left' && <Icon className="w-4 h-4" />}
            {children}
            {direction === 'right' && <Icon className="w-4 h-4" />}
        </Link>
    );
};

BackLink.propTypes = {
    to: PropTypes.string.isRequired,
    children: PropTypes.node.isRequired,
    direction: PropTypes.oneOf(['left', 'right']),
    className: PropTypes.string,
};

export default BackLink;
