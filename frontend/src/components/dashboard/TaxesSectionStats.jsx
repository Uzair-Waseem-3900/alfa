import PropTypes from 'prop-types';
import { useNavigate } from 'react-router-dom';
import { Calculator, Hourglass, Receipt, DollarSign, ArrowUpFromLine, ArrowDownToLine } from 'lucide-react';
import StatCard from './StatCard';
import StatCardSkeleton from './StatCardSkeleton';

const TaxesSectionStats = ({ stats, loading }) => {
    const navigate = useNavigate();
    const goToTaxes = () => navigate('/taxes');

    if (loading) {
        return (
            <div className="space-y-4">
                <h2 className="text-lg font-semibold text-neutral-900">Taxes</h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                    <StatCardSkeleton color="amber" />
                    <StatCardSkeleton color="red" />
                    <StatCardSkeleton color="blue" />
                    <StatCardSkeleton color="purple" />
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            <h2 className="text-lg font-semibold text-neutral-900">Taxes</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <StatCard
                    label="Net Sales Tax Payable"
                    value={stats?.net_sales_tax_payable}
                    icon={Calculator}
                    color="amber"
                    subtitle="Output minus Input tax"
                    onClick={goToTaxes}
                />
                <StatCard
                    label="Sales Tax Outstanding"
                    value={stats?.sales_tax_outstanding}
                    icon={Hourglass}
                    color="red"
                    subtitle="Still to pay FBR"
                    onClick={goToTaxes}
                />
                <StatCard
                    label="Input Tax Paid"
                    value={stats?.total_input_tax_paid}
                    icon={Receipt}
                    color="blue"
                    subtitle="GST paid to suppliers"
                    onClick={goToTaxes}
                />
                <StatCard
                    label="Output Tax Collected"
                    value={stats?.total_output_tax_collected}
                    icon={DollarSign}
                    color="purple"
                    subtitle="GST charged to customers"
                    onClick={goToTaxes}
                />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <StatCard
                    label="WHT Withheld from Suppliers"
                    value={stats?.total_wht_withheld_from_suppliers}
                    icon={ArrowUpFromLine}
                    color="orange"
                    subtitle="Info only — owed to FBR"
                    onClick={goToTaxes}
                />
                <StatCard
                    label="WHT Withheld by Customers"
                    value={stats?.total_wht_withheld_by_customers}
                    icon={ArrowDownToLine}
                    color="green"
                    subtitle="Info only — your tax credit"
                    onClick={goToTaxes}
                />
            </div>
        </div>
    );
};

TaxesSectionStats.propTypes = {
    stats: PropTypes.object,
    loading: PropTypes.bool,
};

export default TaxesSectionStats;
