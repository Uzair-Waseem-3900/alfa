import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useRateHistory } from '../../hooks/useRates';
import { useToast } from '../../context/ToastContext';
import { extractErrorMessage } from '../../utils/errorMessage';
import { purchasesApi } from '../../services/purchasesApi';
import PriceHistoryTable from '../../components/rates/PriceHistoryTable';
import Button from '../../components/ui/Button';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Card from '../../components/ui/Card';
import Badge from '../../components/ui/Badge';
import InlineAlert from '../../components/ui/InlineAlert';

const PriceHistoryPage = () => {
    const { productId } = useParams();
    const navigate = useNavigate();
    const { toast } = useToast();
    const { data, loading, error, refetch } = useRateHistory(productId);
    const [product, setProduct] = useState(null);
    const [productLoading, setProductLoading] = useState(true);

    useEffect(() => {
        fetchProduct();
    }, [productId]);

    const fetchProduct = async () => {
        setProductLoading(true);
        try {
            // Get product details from products API
            const productsRes = await purchasesApi.products.getAll({ page_size: 500 });
            const products = productsRes?.results ?? productsRes ?? [];
            const found = products.find(p => p.id === parseInt(productId));
            setProduct(found);
        } catch (error) {
            console.error('Failed to fetch product:', error);
            toast.error(extractErrorMessage(error, 'Failed to load product details'));
        } finally {
            setProductLoading(false);
        }
    };

    const currentPrice = data.length > 0 ? parseFloat(data[0].selling_price) : null;

    if (productLoading || loading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold text-neutral-900">Price History</h1>
                    <p className="text-neutral-500 mt-1">
                        Complete price change log for this product
                    </p>
                </div>
                <Link to="/rates">
                    <Button variant="secondary">
                        ← Back to Rates
                    </Button>
                </Link>
            </div>

            {error && <InlineAlert variant="error" message={error} onRetry={refetch} />}

            {/* Product Info */}
            {product && (
                <Card className="p-6">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div>
                            <p className="text-sm text-neutral-500">Product Name</p>
                            <p className="font-medium text-neutral-900">{product.name}</p>
                        </div>
                        <div>
                            <p className="text-sm text-neutral-500">Product Code</p>
                            <p className="font-medium text-neutral-900">{product.code}</p>
                        </div>
                        <div>
                            <p className="text-sm text-neutral-500">Category</p>
                            <p className="font-medium text-neutral-900">
                                {product.category?.name || 'N/A'}
                            </p>
                        </div>
                        <div>
                            <p className="text-sm text-neutral-500">Current Price</p>
                            <p className="font-medium text-primary-600 text-lg">
                                {currentPrice !== null ? `Rs. ${currentPrice.toFixed(2)}` : 'No price set'}
                            </p>
                        </div>
                    </div>
                </Card>
            )}

            {/* Price History Table */}
            <PriceHistoryTable
                history={data}
                loading={loading}
                currentPrice={currentPrice}
            />

            {/* Back Button at Bottom */}
            <div className="flex justify-center">
                <Link to="/rates">
                    <Button variant="secondary">
                        ← Back to Rates
                    </Button>
                </Link>
            </div>
        </div>
    );
};

export default PriceHistoryPage;