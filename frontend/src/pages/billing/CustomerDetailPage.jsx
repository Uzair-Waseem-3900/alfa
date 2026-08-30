import { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { TrendingUp, FileText, ArrowRight } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { billingApi } from '../../services/billingApi';
import { extractErrorMessage } from '../../utils/errorMessage';
import BackLink from '../../components/ui/BackLink';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import Table from '../../components/ui/Table';
import Badge from '../../components/ui/Badge';
import InlineAlert from '../../components/ui/InlineAlert';
import EmptyState from '../../components/ui/EmptyState';
import PaymentStatusBadge from '../../components/billing/PaymentStatusBadge';

const money = (value) => {
    const num = typeof value === 'string' ? parseFloat(value) : value;
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

const CustomerDetailPage = () => {
    const { id } = useParams();
    const { user } = useAuth();
    const isAdmin = user?.role === 'admin' || user?.role === 'superuser';

    const [customer, setCustomer] = useState(null);
    const [outstandingSummary, setOutstandingSummary] = useState(null);
    const [invoices, setInvoices] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchData = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const [customerData, summaryData, invoicesData] = await Promise.all([
                billingApi.customers.getById(id),
                billingApi.customers.getOutstandingSummary(id),
                billingApi.invoices.getAll({ customer_id: id, page_size: 500 }),
            ]);

            setCustomer(customerData);
            setOutstandingSummary(summaryData);
            setInvoices(invoicesData?.results ?? invoicesData ?? []);
        } catch (err) {
            setError(extractErrorMessage(err, 'Failed to load customer details.'));
        } finally {
            setLoading(false);
        }
    }, [id]);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    const columns = [
        { key: 'bill_number', label: 'Bill #', width: '120px' },
        {
            key: 'grand_total',
            label: 'Grand Total (PKR)',
            render: (value) => money(value),
        },
        {
            key: 'credit_outstanding',
            label: 'Outstanding (PKR)',
            render: (value) => money(value),
        },
        {
            key: 'payment_status',
            label: 'Payment Status',
            render: (value) => <PaymentStatusBadge status={value} />
        },
        {
            key: 'status',
            label: 'Invoice Status',
            render: (value) => {
                const variants = {
                    draft: 'draft',
                    confirmed: 'confirmed',
                    partial: 'warning',
                    returned: 'info',
                };
                const labels = {
                    draft: 'Draft',
                    confirmed: 'Confirmed',
                    partial: 'Partial Return',
                    returned: 'Returned',
                };
                return <Badge variant={variants[value] || 'default'}>{labels[value] || value}</Badge>;
            }
        },
        {
            key: 'confirmed_at',
            label: 'Confirmed',
            render: (value) => value ? new Date(value).toLocaleDateString() : 'N/A'
        },
        {
            key: 'id',
            label: 'Actions',
            width: '90px',
            render: (_, row) => (
                <Link
                    to={`/billing/invoices/${row.id}`}
                    className="inline-flex items-center gap-1 text-primary-600 hover:text-primary-700 text-sm font-medium"
                >
                    View <ArrowRight className="w-3.5 h-3.5" />
                </Link>
            ),
        },
    ];

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <LoadingSpinner size="lg" />
            </div>
        );
    }

    if (error) {
        return (
            <div className="space-y-4">
                <BackLink to="/billing/customers">Back to Customers</BackLink>
                <InlineAlert variant="error" title="Failed to load customer" message={error} onRetry={fetchData} />
            </div>
        );
    }

    if (!customer) {
        return (
            <div className="text-center py-12">
                <h2 className="text-2xl font-semibold text-neutral-900">Customer Not Found</h2>
                <BackLink to="/billing/customers" className="mt-4">Back to Customers</BackLink>
            </div>
        );
    }

    const activeInvoices = invoices.filter(inv => inv.status !== 'draft');
    const draftInvoices = invoices.filter(inv => inv.status === 'draft');

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <BackLink to="/billing/customers">Back to Customers</BackLink>
                    <h1 className="text-3xl font-bold text-neutral-900 mt-2">{customer.name}</h1>
                    <p className="text-neutral-500">Code: {customer.code}</p>
                </div>
                <Link to={`/billing/customers/${id}/credit-score`}>
                    <Button variant="secondary" icon={TrendingUp}>
                        Credit Score
                    </Button>
                </Link>
            </div>

            {/* Customer Info */}
            <Card className="p-6" hover={false}>
                <h3 className="font-semibold text-neutral-900 mb-4">Customer Information</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-5">
                    <div>
                        <p className="text-sm text-neutral-500">Name</p>
                        <p className="font-medium text-neutral-900">{customer.name}</p>
                    </div>
                    <div>
                        <p className="text-sm text-neutral-500">Code</p>
                        <p className="font-medium text-neutral-900">{customer.code}</p>
                    </div>
                    <div>
                        <p className="text-sm text-neutral-500">Address</p>
                        <p className="font-medium text-neutral-900">{customer.address}</p>
                    </div>
                    <div>
                        <p className="text-sm text-neutral-500">Mobile</p>
                        <p className="font-medium text-neutral-900">{customer.mobile || 'N/A'}</p>
                    </div>
                    <div>
                        <p className="text-sm text-neutral-500">Created</p>
                        <p className="font-medium text-neutral-900">{new Date(customer.created_at).toLocaleDateString()}</p>
                    </div>
                    <div>
                        <p className="text-sm text-neutral-500">Status</p>
                        <Badge variant={customer.is_deleted ? 'error' : 'success'}>
                            {customer.is_deleted ? 'Deleted' : 'Active'}
                        </Badge>
                    </div>
                </div>
            </Card>

            {/* Outstanding Summary */}
            {outstandingSummary && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <Card className="p-4">
                        <p className="text-sm text-neutral-500">Total Billed</p>
                        <p className="text-xl font-bold text-neutral-900">
                            {money(outstandingSummary.total_billed)}
                        </p>
                    </Card>
                    <Card className="p-4">
                        <p className="text-sm text-neutral-500">Total Paid</p>
                        <p className="text-xl font-bold text-success-600">
                            {money(outstandingSummary.total_paid)}
                        </p>
                    </Card>
                    <Card className="p-4">
                        <p className="text-sm text-neutral-500">Credit Outstanding</p>
                        <p className="text-xl font-bold text-error-600">
                            {money(outstandingSummary.total_credit_outstanding)}
                        </p>
                    </Card>
                    <Card className="p-4">
                        <p className="text-sm text-neutral-500 mb-1">Payment Status</p>
                        {outstandingSummary.total_credit_outstanding && parseFloat(outstandingSummary.total_credit_outstanding) > 0 ? (
                            <Badge variant="unpaid">Outstanding</Badge>
                        ) : (
                            <Badge variant="paid">Settled</Badge>
                        )}
                    </Card>
                </div>
            )}

            {/* Invoice History */}
            <Card className="p-6" hover={false}>
                <h3 className="font-semibold text-neutral-900 mb-4">Invoice History</h3>
                {activeInvoices.length === 0 ? (
                    <EmptyState
                        icon={<FileText className="w-8 h-8 text-neutral-400" />}
                        title="No confirmed invoices"
                        description="This customer has no confirmed invoices yet."
                    />
                ) : (
                    <Table columns={columns} data={activeInvoices} />
                )}
            </Card>

            {/* All Invoices (including drafts) */}
            {invoices.length > activeInvoices.length && (
                <Card className="p-6" hover={false}>
                    <h3 className="font-semibold text-neutral-900 mb-4">Draft Invoices</h3>
                    {draftInvoices.length === 0 ? (
                        <p className="text-center text-neutral-500 py-4">No draft invoices</p>
                    ) : (
                        <Table columns={columns} data={draftInvoices} />
                    )}
                </Card>
            )}
        </div>
    );
};

export default CustomerDetailPage;
