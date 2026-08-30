import { useState } from 'react';
import { Navigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { DatabaseZap } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import Tabs from '../../components/ui/Tabs';
import InlineAlert from '../../components/ui/InlineAlert';
import SupplierOpeningBalancePanel from '../../components/dataentry/SupplierOpeningBalancePanel';
import CustomerOpeningBalancePanel from '../../components/dataentry/CustomerOpeningBalancePanel';
import OpeningCashPanel from '../../components/dataentry/OpeningCashPanel';
import OpeningStockPanel from '../../components/dataentry/OpeningStockPanel';
import OpeningInvestorInvestmentPanel from '../../components/dataentry/OpeningInvestorInvestmentPanel';

const TABS = [
    { value: 'supplier', label: 'Supplier Balance' },
    { value: 'customer', label: 'Customer Balance' },
    { value: 'cash', label: 'Opening Cash' },
    { value: 'stock', label: 'Opening Stock' },
    { value: 'investor', label: 'Investor Investment' },
];

const DataEntryPage = () => {
    const { user } = useAuth();
    const [activeTab, setActiveTab] = useState('supplier');

    // Superuser-only page. Non-superusers are redirected (backend also enforces).
    if (user?.role !== 'superuser') {
        return <Navigate to="/dashboard" replace />;
    }

    return (
        <div className="space-y-6">
            <motion.div
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
                className="flex items-start gap-4"
            >
                <div className="hidden sm:flex w-12 h-12 rounded-2xl bg-gradient-to-br from-primary-700 to-accent-600 items-center justify-center shadow-lg shadow-primary-900/20 flex-shrink-0">
                    <DatabaseZap className="w-6 h-6 text-white" />
                </div>
                <div>
                    <h1 className="text-2xl sm:text-3xl font-bold text-neutral-900">Data Entry</h1>
                    <p className="text-neutral-500 mt-1">
                        One-time bootstrap of opening balances, cash and stock before go-live.
                        Opening balances are <span className="font-medium text-neutral-700">permanently locked</span> after creation.
                    </p>
                </div>
            </motion.div>

            <InlineAlert
                variant="warning"
                title="Superuser tool"
                message="Entries here cannot be edited or deleted. Opening balances appear only as outstanding amounts to be settled — they don't count as operating-period purchases or sales."
            />

            <div className="overflow-x-auto -mx-1 px-1">
                <Tabs tabs={TABS} activeTab={activeTab} onChange={setActiveTab} className="min-w-max" />
            </div>

            <motion.div
                key={activeTab}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.25 }}
            >
                {activeTab === 'supplier' && <SupplierOpeningBalancePanel />}
                {activeTab === 'customer' && <CustomerOpeningBalancePanel />}
                {activeTab === 'cash' && <OpeningCashPanel />}
                {activeTab === 'stock' && <OpeningStockPanel />}
                {activeTab === 'investor' && <OpeningInvestorInvestmentPanel />}
            </motion.div>
        </div>
    );
};

export default DataEntryPage;
