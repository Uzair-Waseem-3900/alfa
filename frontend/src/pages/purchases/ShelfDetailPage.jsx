import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { ArrowRightLeft, LayoutGrid, PackageSearch } from 'lucide-react';
import { purchasesApi } from '../../services/purchasesApi';
import { usePaginatedList } from '../../hooks/usePaginatedList';
import Table from '../../components/ui/Table';
import Button from '../../components/ui/Button';
import BackLink from '../../components/ui/BackLink';
import Card from '../../components/ui/Card';
import SearchBar from '../../components/ui/SearchBar';
import Pagination from '../../components/ui/Pagination';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import InlineAlert from '../../components/ui/InlineAlert';
import EmptyState from '../../components/ui/EmptyState';
import MoveStockModal from '../../components/purchases/MoveStockModal';
import { extractErrorMessage } from '../../utils/errorMessage';

const ShelfDetailPage = () => {
    const { id } = useParams();

    const [shelf, setShelf] = useState(null);
    const [shelfLoading, setShelfLoading] = useState(true);
    const [shelfError, setShelfError] = useState('');
    const [searchTerm, setSearchTerm] = useState('');
    const [showMoveModal, setShowMoveModal] = useState(false);

    const fetchShelf = async () => {
        setShelfLoading(true);
        setShelfError('');
        try {
            const data = await purchasesApi.shelves.getById(id);
            setShelf(data);
        } catch (err) {
            setShelf(null);
            setShelfError(extractErrorMessage(err, 'Failed to load shelf.'));
        } finally {
            setShelfLoading(false);
        }
    };

    useEffect(() => {
        fetchShelf();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [id]);

    const fetchStockPage = (params) => {
        const p = { ...params };
        if (searchTerm) p.search = searchTerm;
        return purchasesApi.shelves.getStock(id, p);
    };

    const {
        data: stock, meta, page, setPage, loading, error: stockError, refetch,
    } = usePaginatedList(fetchStockPage, {}, 25, [id, searchTerm]);

    const handleSearch = (value) => {
        setSearchTerm(value);
        setPage(1);
    };

    const handleMoveSuccess = () => {
        setShowMoveModal(false);
        refetch();
    };

    const columns = [
        {
            key: 'product_name',
            label: 'Product Name',
            render: (_value, row) => row.product?.name || 'N/A',
        },
        {
            key: 'product_code',
            label: 'Product Code',
            render: (_value, row) => row.product?.code || 'N/A',
        },
        {
            key: 'quantity',
            label: 'Quantity',
            render: (value) => <span className="font-semibold text-neutral-900">{value}</span>,
        },
        {
            key: 'last_updated_at',
            label: 'Last Updated',
            render: (value) => value ? new Date(value).toLocaleString() : 'N/A',
        },
    ];

    if (shelfLoading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    if (!shelf) {
        return (
            <div className="space-y-4">
                <BackLink to="/purchases/shelves">Back to Shelves</BackLink>
                {shelfError ? (
                    <InlineAlert variant="error" message={shelfError} onRetry={fetchShelf} />
                ) : (
                    <div className="text-center py-12">
                        <h2 className="text-2xl font-semibold text-neutral-900">Shelf Not Found</h2>
                        <p className="text-neutral-500 mt-1">The shelf you&apos;re looking for doesn&apos;t exist.</p>
                    </div>
                )}
            </div>
        );
    }

    return (
        <>
            <MoveStockModal
                isOpen={showMoveModal}
                onClose={() => setShowMoveModal(false)}
                fromShelfId={id}
                onSuccess={handleMoveSuccess}
            />

            <div className="space-y-6">
                <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
                    <div>
                        <BackLink to="/purchases/shelves">Back to Shelves</BackLink>
                        <div className="flex items-center gap-3 mt-3">
                            <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-primary-600 to-accent-600 flex items-center justify-center shadow-lg shadow-primary-900/20 flex-shrink-0">
                                <LayoutGrid className="w-5 h-5 text-white" />
                            </div>
                            <div>
                                <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900">{shelf.name}</h1>
                                {shelf.description && (
                                    <p className="text-neutral-500 mt-0.5 text-sm sm:text-base">{shelf.description}</p>
                                )}
                            </div>
                        </div>
                    </div>
                    <Button
                        onClick={() => setShowMoveModal(true)}
                        icon={ArrowRightLeft}
                        className="sm:flex-shrink-0"
                    >
                        Move Stock
                    </Button>
                </div>

                <Card className="p-4 sm:p-6" hover={false}>
                    <div className="flex items-center justify-between mb-4">
                        <h3 className="font-semibold text-neutral-900">Products on this Shelf</h3>
                    </div>

                    <div className="mb-4">
                        <SearchBar
                            onSearch={handleSearch}
                            placeholder="Search by product name or code..."
                            className="w-full"
                        />
                    </div>

                    {stockError && (
                        <div className="mb-4">
                            <InlineAlert variant="error" message={stockError} onRetry={refetch} />
                        </div>
                    )}

                    {loading ? (
                        <div className="flex items-center justify-center py-12">
                            <LoadingSpinner size="lg" />
                        </div>
                    ) : stock.length === 0 ? (
                        <EmptyState
                            icon={<PackageSearch className="w-8 h-8 text-neutral-400" />}
                            title="No products on this shelf"
                            description={searchTerm ? 'Try adjusting your search.' : 'Move stock here to see it listed.'}
                        />
                    ) : (
                        <>
                            <Table columns={columns} data={stock} />

                            {meta.totalPages > 1 && (
                                <div className="mt-4">
                                    <Pagination
                                        currentPage={meta.currentPage}
                                        totalPages={meta.totalPages}
                                        onPageChange={setPage}
                                    />
                                </div>
                            )}
                        </>
                    )}
                </Card>
            </div>
        </>
    );
};

export default ShelfDetailPage;
