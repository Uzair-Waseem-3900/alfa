import PropTypes from 'prop-types';
import Card from '../ui/Card';

const StatCardSkeleton = ({ color = 'primary' }) => {
    const colors = {
        primary: 'border-l-4 border-primary-500',
        green: 'border-l-4 border-success-500',
        amber: 'border-l-4 border-warning-500',
        red: 'border-l-4 border-error-500',
        blue: 'border-l-4 border-info-500',
        orange: 'border-l-4 border-orange-500',
        purple: 'border-l-4 border-purple-500',
    };

    return (
        <Card className={`p-5 ${colors[color] || colors.primary}`}>
            <div className="flex items-start justify-between">
                <div className="flex-1">
                    <div className="h-4 bg-neutral-200 rounded w-24 animate-pulse"></div>
                    <div className="h-8 bg-neutral-200 rounded w-32 mt-2 animate-pulse"></div>
                </div>
                <div className="w-10 h-10 bg-neutral-200 rounded-xl animate-pulse"></div>
            </div>
        </Card>
    );
};

StatCardSkeleton.propTypes = {
    color: PropTypes.oneOf(['primary', 'green', 'amber', 'red', 'blue', 'orange', 'purple']),
};

export default StatCardSkeleton;