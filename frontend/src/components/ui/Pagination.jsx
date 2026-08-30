import { useState } from 'react';
import { motion } from 'framer-motion';
import PropTypes from 'prop-types';
import Button from './Button';

const Pagination = ({
    currentPage,
    totalPages,
    onPageChange,
    className = '',
}) => {
    const [pageInput, setPageInput] = useState('');

    const handleGoToPage = (e) => {
        e.preventDefault();
        const page = parseInt(pageInput, 10);
        if (!isNaN(page)) {
            onPageChange(Math.min(Math.max(page, 1), totalPages));
        }
        setPageInput('');
    };

    const getPageNumbers = () => {
        const pages = [];
        const maxVisible = 5;

        if (totalPages <= maxVisible) {
            for (let i = 1; i <= totalPages; i++) {
                pages.push(i);
            }
        } else {
            if (currentPage <= 3) {
                for (let i = 1; i <= 4; i++) pages.push(i);
                pages.push('...');
                pages.push(totalPages);
            } else if (currentPage >= totalPages - 2) {
                pages.push(1);
                pages.push('...');
                for (let i = totalPages - 3; i <= totalPages; i++) pages.push(i);
            } else {
                pages.push(1);
                pages.push('...');
                for (let i = currentPage - 1; i <= currentPage + 1; i++) pages.push(i);
                pages.push('...');
                pages.push(totalPages);
            }
        }

        return pages;
    };

    return (
        <div className={`flex items-center justify-between ${className}`}>
            <p className="text-sm text-neutral-500">
                Page {currentPage} of {totalPages}
            </p>

            <div className="flex gap-1">
                <Button
                    variant="secondary"
                    size="sm"
                    disabled={currentPage === 1}
                    onClick={() => onPageChange(currentPage - 1)}
                >
                    Previous
                </Button>

                {getPageNumbers().map((page, index) => (
                    <motion.button
                        key={index}
                        whileHover={{ scale: 1.05 }}
                        whileTap={{ scale: 0.95 }}
                        onClick={() => typeof page === 'number' && onPageChange(page)}
                        className={`
              px-3 py-1 rounded-lg text-sm transition-colors
              ${page === currentPage
                                ? 'bg-primary-600 text-white'
                                : page === '...'
                                    ? 'cursor-default text-neutral-400'
                                    : 'hover:bg-neutral-100 text-neutral-600'
                            }
            `}
                        disabled={page === '...'}
                    >
                        {page}
                    </motion.button>
                ))}

                <Button
                    variant="secondary"
                    size="sm"
                    disabled={currentPage === totalPages}
                    onClick={() => onPageChange(currentPage + 1)}
                >
                    Next
                </Button>

                <form onSubmit={handleGoToPage} className="flex gap-1 ml-2">
                    <input
                        type="number"
                        min={1}
                        max={totalPages}
                        value={pageInput}
                        onChange={(e) => setPageInput(e.target.value)}
                        placeholder="Go to..."
                        className="w-20 px-2 py-1 text-sm border border-neutral-200 rounded-lg outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500"
                    />
                    <Button type="submit" variant="secondary" size="sm">
                        Go
                    </Button>
                </form>
            </div>
        </div>
    );
};

Pagination.propTypes = {
    currentPage: PropTypes.number.isRequired,
    totalPages: PropTypes.number.isRequired,
    onPageChange: PropTypes.func.isRequired,
    className: PropTypes.string,
};

export default Pagination;