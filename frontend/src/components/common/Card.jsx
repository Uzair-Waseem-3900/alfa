import { motion } from 'framer-motion';
import PropTypes from 'prop-types';

const Card = ({
    children,
    className = '',
    hover = true,
    glass = false,
    onClick,
    ...props
}) => {
    return (
        <motion.div
            whileHover={hover ? { y: -4, transition: { duration: 0.3 } } : {}}
            className={`
        card
        ${glass ? 'glass-effect' : ''}
        ${onClick ? 'cursor-pointer' : ''}
        ${className}
      `}
            onClick={onClick}
            {...props}
        >
            {children}
        </motion.div>
    );
};

Card.propTypes = {
    children: PropTypes.node,
    className: PropTypes.string,
    hover: PropTypes.bool,
    glass: PropTypes.bool,
    onClick: PropTypes.func,
};

export default Card;