import { memo } from 'react';
import PropTypes from 'prop-types';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// Right-align numeric cells (amounts) so columns of figures line up.
const NUMERIC = /^[\s\-+(]*(?:Rs\.?|PKR)?\s*[\d,]+(?:\.\d+)?\)?\s*%?\s*$/i;
const cellText = (children) => (Array.isArray(children) ? children.join('') : String(children ?? ''));

// Element styling lives here (semantic tokens only) instead of a typography
// plugin, so assistant answers match the rest of the app. react-markdown does
// not render raw HTML, so model/data text can never inject markup.
const components = {
    p: (props) => <p className="leading-7 [&:not(:first-child)]:mt-3" {...props} />,
    strong: (props) => <strong className="font-semibold text-neutral-900" {...props} />,
    em: (props) => <em className="italic" {...props} />,
    h1: (props) => <h3 className="text-lg font-semibold text-neutral-900 mt-5 mb-2" {...props} />,
    h2: (props) => <h3 className="text-lg font-semibold text-neutral-900 mt-5 mb-2" {...props} />,
    h3: (props) => <h4 className="text-base font-semibold text-neutral-900 mt-4 mb-1.5" {...props} />,
    h4: (props) => <h4 className="text-base font-semibold text-neutral-900 mt-4 mb-1.5" {...props} />,
    ul: (props) => <ul className="list-disc pl-6 mt-3 space-y-1.5 marker:text-neutral-400" {...props} />,
    ol: (props) => <ol className="list-decimal pl-6 mt-3 space-y-1.5 marker:text-neutral-500" {...props} />,
    li: (props) => <li className="leading-7 pl-0.5" {...props} />,
    hr: () => <hr className="my-4 border-neutral-200" />,
    blockquote: (props) => (
        <blockquote className="mt-3 border-l-4 border-primary-200 bg-primary-50/60 rounded-r-lg pl-4 pr-3 py-2 text-neutral-700" {...props} />
    ),
    a: ({ href, children }) => (
        <a href={href} target="_blank" rel="noopener noreferrer" className="text-accent-600 underline underline-offset-2 hover:text-accent-700">
            {children}
        </a>
    ),
    code: ({ inline, className, children, ...props }) =>
        inline || !/\n/.test(String(children)) ? (
            <code className="rounded bg-neutral-100 px-1.5 py-0.5 text-[0.9em] font-mono text-primary-800" {...props}>{children}</code>
        ) : (
            <code className={`font-mono text-sm ${className || ''}`} {...props}>{children}</code>
        ),
    pre: (props) => (
        <pre className="mt-3 overflow-x-auto rounded-xl bg-primary-900 text-primary-50 p-4 text-sm leading-6" {...props} />
    ),
    // Wide tables scroll sideways inside the message instead of breaking the page on phones.
    table: (props) => (
        <div className="mt-3 overflow-x-auto rounded-xl border border-neutral-200 bg-white">
            <table className="min-w-full border-collapse text-sm" {...props} />
        </div>
    ),
    thead: (props) => <thead className="bg-neutral-50" {...props} />,
    th: ({ children, ...props }) => (
        <th
            className={`px-3 py-2 text-left font-semibold text-neutral-700 whitespace-nowrap border-b border-neutral-200 ${NUMERIC.test(cellText(children)) ? 'text-right' : ''}`}
            {...props}
        >
            {children}
        </th>
    ),
    td: ({ children, ...props }) => (
        <td
            className={`px-3 py-2 text-neutral-800 border-b border-neutral-100 align-top ${NUMERIC.test(cellText(children)) ? 'text-right tabular-nums whitespace-nowrap' : ''}`}
            {...props}
        >
            {children}
        </td>
    ),
};

const MarkdownContent = ({ text }) => (
    <div className="text-[15px] text-neutral-800 break-words">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
            {text}
        </ReactMarkdown>
    </div>
);

MarkdownContent.propTypes = {
    text: PropTypes.string.isRequired,
};

export default memo(MarkdownContent);
