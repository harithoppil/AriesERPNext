import { useState, useMemo } from 'react';
import { motion } from 'framer-motion';
import {
  Landmark, Banknote, FileText, Plus, X,
} from 'lucide-react';
import { getPayments } from '@/lib/api';

const aed = new Intl.NumberFormat('en-AE', { style: 'currency', currency: 'AED' });

const statusConfig = {
  cleared: { label: 'Cleared', className: 'bg-green-100 text-green-700' },
  pending: { label: 'Pending', className: 'bg-amber-100 text-amber-700' },
};

const methodConfig = {
  bank:   { label: 'Bank Transfer', icon: Landmark },
  cash:   { label: 'Cash',          icon: Banknote },
  cheque: { label: 'Cheque',        icon: FileText },
};

/* ─── Toast ─── */
function useToast() {
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'info' } | null>(null);
  const show = (message: string, type: 'success' | 'info' = 'info') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 2500);
  };
  return { toast, show };
}

/* ─── Record Payment Dialog ─── */
function RecordPaymentDialog({ onClose, onRecord }: { onClose: () => void; onRecord: () => void }) {
  const [client, setClient] = useState('');
  const [amount, setAmount] = useState('');
  const [method, setMethod] = useState<'bank' | 'cash' | 'cheque'>('bank');
  const [reference, setReference] = useState('');
  const [date, setDate] = useState('');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.15 }}
        className="relative bg-white rounded-2xl shadow-xl border border-gray-100 w-full max-w-md mx-4 p-6 z-10"
      >
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-semibold text-[#0f172a]">Record Payment</h2>
          <button onClick={onClose} className="p-1.5 hover:bg-gray-100 rounded-lg transition-colors">
            <X size={18} className="text-gray-500" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Client</label>
            <input
              type="text"
              value={client}
              onChange={(e) => setClient(e.target.value)}
              placeholder="Client name"
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Amount (AED)</label>
            <input
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="0.00"
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Method</label>
            <select
              value={method}
              onChange={(e) => setMethod(e.target.value as 'bank' | 'cash' | 'cheque')}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none bg-white"
            >
              <option value="bank">Bank Transfer</option>
              <option value="cash">Cash</option>
              <option value="cheque">Cheque</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Reference</label>
            <input
              type="text"
              value={reference}
              onChange={(e) => setReference(e.target.value)}
              placeholder="Bank ref / Cheque #"
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Date</label>
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none"
            />
          </div>
        </div>

        <div className="flex items-center justify-end gap-3 mt-6">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => { onRecord(); onClose(); }}
            className="px-4 py-2 text-sm font-medium text-white bg-[#1e3a5f] hover:bg-[#2d5a87] rounded-lg transition-colors"
          >
            Record Payment
          </button>
        </div>
      </motion.div>
    </div>
  );
}

/* ─── Main Page ─── */
export default function Payments() {
  const payments = useMemo(() => getPayments(), []);
  const [showRecord, setShowRecord] = useState(false);
  const { toast, show } = useToast();

  const totalCleared = useMemo(
    () => payments.filter(p => p.status === 'cleared').reduce((s, p) => s + p.amount, 0),
    [payments],
  );
  const totalPending = useMemo(
    () => payments.filter(p => p.status === 'pending').reduce((s, p) => s + p.amount, 0),
    [payments],
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#0f172a]">Payments</h1>
          <p className="text-sm text-gray-500 mt-1">Payment entries with method tracking</p>
        </div>
        <button
          onClick={() => setShowRecord(true)}
          className="flex items-center gap-2 px-4 py-2.5 bg-[#1e3a5f] text-white rounded-lg hover:bg-[#2d5a87] transition-colors text-sm font-medium"
        >
          <Plus size={18} />
          Record Payment
        </button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
          <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">Total Payments</p>
          <p className="text-xl font-bold text-[#0f172a] mt-1">{payments.length}</p>
        </div>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
          <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">Cleared</p>
          <p className="text-xl font-bold text-[#10b981] mt-1">{aed.format(totalCleared)}</p>
        </div>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
          <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">Pending</p>
          <p className="text-xl font-bold text-[#f59e0b] mt-1">{aed.format(totalPending)}</p>
        </div>
      </div>

      {/* Payments Table */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="bg-gray-50 text-gray-700 font-semibold text-sm">
                <th className="text-left px-5 py-3.5">Payment #</th>
                <th className="text-left px-5 py-3.5">Date</th>
                <th className="text-left px-5 py-3.5">Client</th>
                <th className="text-right px-5 py-3.5">Amount</th>
                <th className="text-left px-5 py-3.5">Method</th>
                <th className="text-left px-5 py-3.5">Reference</th>
                <th className="text-left px-5 py-3.5">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {payments.map((p) => {
                const mCfg = methodConfig[p.method];
                const MIcon = mCfg.icon;
                const sCfg = statusConfig[p.status];
                return (
                  <tr key={p.id} className="hover:bg-gray-50 transition-colors text-sm">
                    <td className="px-5 py-4 font-medium text-[#0f172a]">{p.number}</td>
                    <td className="px-5 py-4 text-gray-600">
                      {new Date(p.date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}
                    </td>
                    <td className="px-5 py-4 text-gray-700">{p.client}</td>
                    <td className="px-5 py-4 text-right font-medium text-gray-900">{aed.format(p.amount)}</td>
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-2 text-gray-600">
                        <MIcon size={16} className="text-[#0ea5e9]" />
                        <span>{mCfg.label}</span>
                      </div>
                    </td>
                    <td className="px-5 py-4 text-gray-500 font-mono text-xs">{p.reference}</td>
                    <td className="px-5 py-4">
                      <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${sCfg.className}`}>
                        {sCfg.label}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Record Payment Dialog */}
      {showRecord && (
        <RecordPaymentDialog
          onClose={() => setShowRecord(false)}
          onRecord={() => show('Payment recorded successfully', 'success')}
        />
      )}

      {/* Toast */}
      {toast && (
        <motion.div
          initial={{ opacity: 0, y: -20, x: 20 }}
          animate={{ opacity: 1, y: 0, x: 0 }}
          exit={{ opacity: 0 }}
          className={`fixed top-20 right-6 z-50 px-4 py-3 rounded-xl shadow-lg border text-sm font-medium ${
            toast.type === 'success' ? 'bg-green-50 text-green-700 border-green-200' : 'bg-blue-50 text-blue-700 border-blue-200'
          }`}
        >
          {toast.message}
        </motion.div>
      )}
    </div>
  );
}
