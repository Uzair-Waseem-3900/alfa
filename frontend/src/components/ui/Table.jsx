import { motion } from 'framer-motion';
import PropTypes from 'prop-types';

const Table = ({ columns, data, onRowClick, className = '', ...props }) => {
    return (
        <div className={`overflow-x-auto ${className}`}>
            <table className="w-full" {...props}>
                <thead>
                    <tr className="border-b border-neutral-200">
                        {columns.map((col) => (
                            <th
                                key={col.key}
                                className="px-4 py-3 text-left text-xs font-medium text-neutral-500 uppercase tracking-wider"
                                style={{ width: col.width }}
                            >
                                {col.label}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody className="divide-y divide-neutral-100">
                    {data.length === 0 ? (
                        <tr>
                            <td colSpan={columns.length} className="px-4 py-8 text-center text-neutral-500">
                                No data available
                            </td>
                        </tr>
                    ) : (
                        data.map((row, index) => (
                            <motion.tr
                                key={row.id || index}
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                transition={{ delay: index * 0.05 }}
                                className={`
                  hover:bg-neutral-50 transition-colors
                  ${onRowClick ? 'cursor-pointer' : ''}
                `}
                                onClick={() => onRowClick?.(row)}
                            >
                                {columns.map((col) => (
                                    <td
                                        key={col.key}
                                        className="px-4 py-3 text-sm text-neutral-700"
                                    >
                                        {col.render ? col.render(row[col.key], row) : row[col.key]}
                                    </td>
                                ))}
                            </motion.tr>
                        ))
                    )}
                </tbody>
            </table>
        </div>
    );
};

Table.propTypes = {
    columns: PropTypes.arrayOf(
        PropTypes.shape({
            key: PropTypes.string.isRequired,
            label: PropTypes.string.isRequired,
            width: PropTypes.string,
            render: PropTypes.func,
        })
    ).isRequired,
    data: PropTypes.array.isRequired,
    onRowClick: PropTypes.func,
    className: PropTypes.string,
};

export default Table;