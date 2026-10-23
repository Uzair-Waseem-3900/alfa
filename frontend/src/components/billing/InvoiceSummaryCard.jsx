import PropTypes from 'prop-types';
import Card from '../ui/Card';
import InlineAlert from '../ui/InlineAlert';

const formatAmount = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : value;
    return isNaN(num) ? '0.00' : num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

// Filtered-invoices summary (count + total outstanding). Self-contained on
// purpose: it owns its own skeleton/error so a slow summary request never
// blocks or blanks the invoice table around it.
const InvoiceSummaryCard = ({ summary, loading, error, onRetry }) => (
    <Card hover={false} className="!p-4 sm:!p-5">
        {error ? (
            <InlineAlert variant="error" message={error} onRetry={onRetry} />
        ) : loading || !summary ? (
            <div className="animate-pulse flex flex-col sm:flex-row gap-4 sm:gap-10" aria-busy="true" aria-label="Loading invoice totals">
                <div className="space-y-2">
                    <div className="h-3 w-28 rounded bg-neutral-200" />
                    <div className="h-7 w-16 rounded bg-neutral-200" />
                </div>
                <div className="space-y-2">
                    <div className="h-3 w-32 rounded bg-neutral-200" />
                    <div className="h-7 w-48 rounded bg-neutral-200" />
                </div>
            </div>
        ) : (
            <div className="flex flex-col sm:flex-row gap-4 sm:gap-10">
                <div>
                    <p className="text-sm text-neutral-500">Matching Invoices</p>
                    <p className="text-2xl font-bold text-neutral-900">{summary.count.toLocaleString()}</p>
                </div>
                <div>
                    <p className="text-sm text-neutral-500">Total Outstanding</p>
                    <p className="text-2xl font-bold text-neutral-900">Rs. {formatAmount(summary.total_outstanding)}</p>
                </div>
            </div>
        )}
    </Card>
);

InvoiceSummaryCard.propTypes = {
    summary: PropTypes.shape({
        count: PropTypes.number,
        total_outstanding: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
    }),
    loading: PropTypes.bool,
    error: PropTypes.string,
    onRetry: PropTypes.func,
};

export default InvoiceSummaryCard;
