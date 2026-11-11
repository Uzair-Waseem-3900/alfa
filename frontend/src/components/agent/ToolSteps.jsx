import PropTypes from 'prop-types';
import { Check, Loader2 } from 'lucide-react';

// What the assistant is doing right now ("Searching invoices…"). Running steps
// spin; finished ones get a check. State is never colour-only (icon + text).
const ToolSteps = ({ steps }) => {
    if (!steps?.length) return null;

    return (
        <ul className="flex flex-wrap gap-2 mb-3" aria-label="Assistant activity">
            {steps.map((step) => (
                <li
                    key={step.id}
                    className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors duration-200 ${
                        step.done
                            ? 'border-neutral-200 bg-neutral-50 text-neutral-500'
                            : 'border-accent-200 bg-accent-50 text-accent-700'
                    }`}
                >
                    {step.done ? (
                        <Check className="w-3.5 h-3.5 text-success-600" aria-hidden="true" />
                    ) : (
                        <Loader2 className="w-3.5 h-3.5 animate-spin motion-reduce:animate-none" aria-hidden="true" />
                    )}
                    {step.label}
                </li>
            ))}
        </ul>
    );
};

ToolSteps.propTypes = {
    steps: PropTypes.arrayOf(PropTypes.shape({
        id: PropTypes.string.isRequired,
        label: PropTypes.string.isRequired,
        done: PropTypes.bool,
    })),
};

export default ToolSteps;
