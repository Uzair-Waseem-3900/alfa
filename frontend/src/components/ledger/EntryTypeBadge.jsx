import PropTypes from 'prop-types';
import Badge from '../ui/Badge';

const EntryTypeBadge = ({ type }) => {
    // Supplier ledger uses 'purchase'; customer ledger uses 'sale' and adds
    // 'opening_balance' — kept in one map since the keys don't collide.
    const variants = {
        purchase: 'error',
        sale: 'error',
        payment: 'success',
        return: 'info',
        advance: 'warning',
        opening_balance: 'default',
    };

    const labels = {
        purchase: 'Purchase',
        sale: 'Sale',
        payment: 'Payment',
        return: 'Return',
        advance: 'Advance',
        opening_balance: 'Opening Balance',
    };

    return <Badge variant={variants[type] || 'default'}>{labels[type] || type}</Badge>;
};

EntryTypeBadge.propTypes = {
    type: PropTypes.oneOf([
        'purchase', 'sale', 'payment', 'return', 'advance', 'opening_balance',
    ]).isRequired,
};

export default EntryTypeBadge;