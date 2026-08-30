import { motion } from 'framer-motion';
import PropTypes from 'prop-types';
import Badge from '../ui/Badge';

const DirectionBadge = ({ direction }) => {
    const isInflow = direction === 'inflow';

    return (
        <Badge variant={isInflow ? 'success' : 'error'}>
            <span className="flex items-center gap-1">
                {isInflow ? '↑' : '↓'} {isInflow ? 'Inflow' : 'Outflow'}
            </span>
        </Badge>
    );
};

DirectionBadge.propTypes = {
    direction: PropTypes.oneOf(['inflow', 'outflow']).isRequired,
};

export default DirectionBadge;