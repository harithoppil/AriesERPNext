import { useState, useMemo } from 'react';
import { motion } from 'framer-motion';
import {
  FileText, Plus, Download, Eye, X,
} from 'lucide-react';
import type { Invoice } from '@/types';
import { getInvoices } from '@/lib/api';

const aed = new Intl.NumberFormat('en-AE', { style: 'currency', currency: 'AED' });

const statusConfig = {
  paid:    { label: 'Paid',    className: 'bg-green-100 text-green-700' },
  pending: { label: 'Pending', className: 'bg-amber-100 text-amber-700' },
  overdue: { label: 'Overdue', className: 'bg-red-100 text-red-700' },
  draft:   { label: 'Draft',   className: 'bg-gray-100 text-gray-600' },
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

/* ─── Stat Card ─── */
function StatCard({ label, amount, accent }: { label: string; amount: number; accent: string }) {
  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
      <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">{label}</p>
      <p className="text-xl font-bold mt-1" style={{ color: accent }}>
        {aed.format(amount)}
      </p>
    </div>
  );
}

/* ─── Invoice Card ─── */
function InvoiceCard({ invoice, onView, onDownload }: {
  invoice: Invoice;
  onView: (inv: Invoice) => void;
  onDownload: (inv: Invoice) => void;
}) {
  const cfg = statusConfig[invoice.status];
  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 hover:shadow-md transition-shadow duration-200 p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <FileText size={18} className="text-[#1e3a5f]" />
          <span className="font-semibold text-sm text-[#0f172a]">{invoice.number}</span>
        </div>
        <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${cfg.className}`}>
          {cfg.label}
        </span>
      </div>

      {/* Client */}
      <p className="text-sm text-gray-600 mb-3">{invoice.client}</p>

      {/* Divider */}
      <div className="border-t border-gray-100 my-3" />

      {/* Dates */}
      <div className="space-y-1.5 text-sm mb-3">
        <div className="flex justify-between">
          <span className="text-gray-500">Issue:</span>
          <span className="text-gray-700">{new Date(invoice.issueDate).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Due:</span>
          <span className="text-gray-700">{new Date(invoice.dueDate).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}</span>
        </div>
      </div>

      {/* Divider */}
      <div className="border-t border-gray-100 my-3" />

      {/* Amounts */}
      <div className="space-y-1.5 text-sm mb-4">
        <div className="flex justify-between">
          <span className="text-gray-500">Subtotal:</span>
          <span className="text-gray-700">{aed.format(invoice.subtotal)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">VAT (5%):</span>
          <span className="text-gray-700">{aed.format(invoice.vat)}</span>
        </div>
        <div className="border-t border-dashed border-gray-200 my-1.5" />
        <div className="flex justify-between">
          <span className="font-semibold text-gray-900">Total:</span>
          <span className="font-bold text-[#0f172a]">{aed.format(invoice.total)}</span>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 mt-4">
        <button
          onClick={() => onView(invoice)}
          className="flex-1 flex items-center justify-center gap-1.5 py-2 text-xs font-medium text-[#1e3a5f] bg-[#1e3a5f]/5 hover:bg-[#1e3a5f]/10 rounded-lg transition-colors"
        >
          <Eye size={14} />
          View Details
        </button>
        <button
          onClick={() => onDownload(invoice)}
          className="flex-1 flex items-center justify-center gap-1.5 py-2 text-xs font-medium text-[#0ea5e9] bg-[#0ea5e9]/5 hover:bg-[#0ea5e9]/10 rounded-lg transition-colors"
        >
          <Download size={14} />
          Download PDF
        </button>
      </div>
    </div>
  );
}

/* ─── Main Page ─── */
export default function Invoices() {
  const invoices = useMemo(() => getInvoices(), []);
  const [showCreate, setShowCreate] = useState(false);
  const { toast, show } = useToast();

  const stats = useMemo(() => {
    const paid = invoices.filter(i => i.status === 'paid').reduce((s, i) => s + i.total, 0);
    const pending = invoices.filter(i => i.status === 'pending').reduce((s, i) => s + i.total, 0);
    const overdue = invoices.filter(i => i.status === 'overdue').reduce((s, i) => s + i.total, 0);
    return { total: invoices.length, paid, pending, overdue };
  }, [invoices]);

  const handleView = (inv: Invoice) => show(`Opening ${inv.number} for ${inv.client}`, 'info');
  const handleDownload = (inv: Invoice) => show(`Downloading PDF for ${inv.number}`, 'success');

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#0f172a]">Invoices</h1>
          <p className="text-sm text-gray-500 mt-1">Sales invoice builder with UAE 5% VAT</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2.5 bg-[#1e3a5f] text-white rounded-lg hover:bg-[#2d5a87] transition-colors text-sm font-medium"
        >
          <Plus size={18} />
          Create Invoice
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Invoices" amount={stats.total} accent="#0f172a" />
        <StatCard label="Paid AED" amount={stats.paid} accent="#10b981" />
        <StatCard label="Pending AED" amount={stats.pending} accent="#f59e0b" />
        <StatCard label="Overdue AED" amount={stats.overdue} accent="#ef4444" />
      </div>

      {/* Invoice Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
        {invoices.map((inv) => (
          <InvoiceCard key={inv.id} invoice={inv} onView={handleView} onDownload={handleDownload} />
        ))}
      </div>

      {/* Create Invoice Dialog */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/40" onClick={() => setShowCreate(false)} />
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.15 }}
            className="relative bg-white rounded-2xl shadow-xl border border-gray-100 w-full max-w-lg mx-4 p-6 z-10"
          >
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-semibold text-[#0f172a]">Create Invoice</h2>
              <button onClick={() => setShowCreate(false)} className="p-1.5 hover:bg-gray-100 rounded-lg transition-colors">
                <X size={18} className="text-gray-500" />
              </button>
            </div>
            <p className="text-sm text-gray-500 mb-4">Fill in the invoice details below.</p>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Client</label>
                <input
                  type="text"
                  placeholder="Client name"
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Issue Date</label>
                  <input
                    type="date"
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Due Date</label>
                  <input
                    type="date"
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Subtotal (AED)</label>
                <input
                  type="number"
                  placeholder="0.00"
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none"
                />
              </div>
              <div className="flex items-center justify-between text-sm text-gray-500 pt-2">
                <span>VAT (5%): Auto-calculated</span>
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 mt-6">
              <button
                onClick={() => setShowCreate(false)}
                className="px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => { setShowCreate(false); show('Invoice created', 'success'); }}
                className="px-4 py-2 text-sm font-medium text-white bg-[#1e3a5f] hover:bg-[#2d5a87] rounded-lg transition-colors"
              >
                Create Invoice
              </button>
            </div>
          </motion.div>
        </div>
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
