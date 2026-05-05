import { useState, useMemo, useCallback } from 'react';
import { motion } from 'framer-motion';
import {
  ShoppingCart, Plus, X, Trash2,
} from 'lucide-react';
import type { PurchaseOrder } from '@/types';
import { getPurchaseOrders, getSuppliers } from '@/lib/api';

const aed = new Intl.NumberFormat('en-AE', { style: 'currency', currency: 'AED' });

const statusConfig = {
  pending:  { label: 'Pending',  className: 'bg-amber-100 text-amber-700' },
  approved: { label: 'Approved', className: 'bg-green-100 text-green-700' },
  received: { label: 'Received', className: 'bg-blue-100 text-blue-700' },
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
function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
      <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">{label}</p>
      <p className="text-xl font-bold mt-1" style={{ color }}>
        {typeof value === 'number' && value > 999 ? aed.format(value) : value}
      </p>
    </div>
  );
}

/* ─── PO Card ─── */
function POCard({ po }: { po: PurchaseOrder }) {
  const cfg = statusConfig[po.status];
  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 hover:shadow-md transition-shadow duration-200 p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <ShoppingCart size={18} className="text-[#1e3a5f]" />
          <span className="font-semibold text-sm text-[#0f172a]">{po.number}</span>
        </div>
        <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${cfg.className}`}>
          {cfg.label}
        </span>
      </div>

      {/* Supplier */}
      <p className="text-sm text-gray-600 mb-3">{po.supplier}</p>

      {/* Divider */}
      <div className="border-t border-gray-100 my-3" />

      {/* Details */}
      <div className="space-y-1.5 text-sm">
        <div className="flex justify-between">
          <span className="text-gray-500">Date:</span>
          <span className="text-gray-700">{new Date(po.date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Delivery:</span>
          <span className="text-gray-700">{new Date(po.deliveryDate).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Items:</span>
          <span className="text-gray-700">{po.items}</span>
        </div>
        <div className="border-t border-dashed border-gray-200 my-1.5" />
        <div className="flex justify-between">
          <span className="font-semibold text-gray-900">Total:</span>
          <span className="font-bold text-[#0f172a]">{aed.format(po.total)}</span>
        </div>
      </div>
    </div>
  );
}

/* ─── Line Item ─── */
interface LineItem {
  id: string;
  name: string;
  qty: number;
  unitPrice: number;
}

let lineItemIdCounter = 0;

/* ─── Create PO Dialog ─── */
function CreatePODialog({ onClose, onCreate }: { onClose: () => void; onCreate: () => void }) {
  const suppliers = useMemo(() => getSuppliers(), []);
  const [supplier, setSupplier] = useState('');
  const [deliveryDate, setDeliveryDate] = useState('');
  const [notes, setNotes] = useState('');
  const [lineItems, setLineItems] = useState<LineItem[]>([
    { id: `li-${++lineItemIdCounter}`, name: '', qty: 1, unitPrice: 0 },
  ]);

  const addLineItem = useCallback(() => {
    setLineItems((prev) => [...prev, { id: `li-${++lineItemIdCounter}`, name: '', qty: 1, unitPrice: 0 }]);
  }, []);

  const removeLineItem = useCallback((id: string) => {
    setLineItems((prev) => prev.filter((li) => li.id !== id));
  }, []);

  const updateLineItem = useCallback((id: string, updates: Partial<LineItem>) => {
    setLineItems((prev) => prev.map((li) => (li.id === id ? { ...li, ...updates } : li)));
  }, []);

  const grandTotal = useMemo(
    () => lineItems.reduce((sum, li) => sum + li.qty * li.unitPrice, 0),
    [lineItems],
  );

  const canSubmit = supplier && deliveryDate && lineItems.some((li) => li.name && li.qty > 0 && li.unitPrice > 0);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.15 }}
        className="relative bg-white rounded-2xl shadow-xl border border-gray-100 w-full max-w-2xl max-h-[85vh] overflow-y-auto z-10"
      >
        <div className="sticky top-0 bg-white rounded-t-2xl border-b border-gray-100 px-6 py-4 flex items-center justify-between z-10">
          <h2 className="text-lg font-semibold text-[#0f172a]">Create Purchase Order</h2>
          <button onClick={onClose} className="p-1.5 hover:bg-gray-100 rounded-lg transition-colors">
            <X size={18} className="text-gray-500" />
          </button>
        </div>

        <div className="px-6 py-5 space-y-5">
          {/* Supplier */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Supplier</label>
            <select
              value={supplier}
              onChange={(e) => setSupplier(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none bg-white"
            >
              <option value="">Select supplier</option>
              {suppliers.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>

          {/* Delivery Date */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Delivery Date</label>
            <input
              type="date"
              value={deliveryDate}
              onChange={(e) => setDeliveryDate(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none"
            />
          </div>

          {/* Line Items */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="block text-sm font-medium text-gray-700">Line Items</label>
              <button
                onClick={addLineItem}
                className="flex items-center gap-1 text-xs font-medium text-[#0ea5e9] hover:text-[#0284c7] transition-colors"
              >
                <Plus size={14} />
                Add Item
              </button>
            </div>

            <div className="border border-gray-200 rounded-xl overflow-hidden">
              {/* Table Header */}
              <div className="grid grid-cols-12 gap-2 bg-gray-50 px-3 py-2 text-xs font-semibold text-gray-500">
                <div className="col-span-5">Item</div>
                <div className="col-span-2 text-center">Qty</div>
                <div className="col-span-3 text-right">Unit Price (AED)</div>
                <div className="col-span-1 text-right">Total</div>
                <div className="col-span-1" />
              </div>

              {/* Line Items */}
              <div className="divide-y divide-gray-100">
                {lineItems.map((li) => {
                  const lineTotal = li.qty * li.unitPrice;
                  return (
                    <div key={li.id} className="grid grid-cols-12 gap-2 px-3 py-2.5 items-center text-sm">
                      <div className="col-span-5">
                        <input
                          type="text"
                          value={li.name}
                          onChange={(e) => updateLineItem(li.id, { name: e.target.value })}
                          placeholder="Item description"
                          className="w-full border border-gray-200 rounded-md px-2 py-1.5 text-xs focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none"
                        />
                      </div>
                      <div className="col-span-2">
                        <input
                          type="number"
                          value={li.qty || ''}
                          onChange={(e) => updateLineItem(li.id, { qty: Math.max(1, parseInt(e.target.value, 10) || 0) })}
                          min={1}
                          className="w-full border border-gray-200 rounded-md px-2 py-1.5 text-xs text-center focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none"
                        />
                      </div>
                      <div className="col-span-3">
                        <input
                          type="number"
                          value={li.unitPrice || ''}
                          onChange={(e) => updateLineItem(li.id, { unitPrice: Math.max(0, parseFloat(e.target.value) || 0) })}
                          min={0}
                          step={0.01}
                          placeholder="0.00"
                          className="w-full border border-gray-200 rounded-md px-2 py-1.5 text-xs text-right focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none"
                        />
                      </div>
                      <div className="col-span-1 text-right text-xs font-medium text-gray-700">
                        {aed.format(lineTotal)}
                      </div>
                      <div className="col-span-1 flex justify-end">
                        {lineItems.length > 1 && (
                          <button
                            onClick={() => removeLineItem(li.id)}
                            className="p-1 hover:bg-red-50 rounded transition-colors text-gray-400 hover:text-red-500"
                          >
                            <Trash2 size={13} />
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Grand Total */}
              <div className="border-t border-gray-200 bg-gray-50/50 px-3 py-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-gray-700">Grand Total:</span>
                  <span className="text-lg font-bold text-[#0f172a]">{aed.format(grandTotal)}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Notes */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Notes</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Additional notes..."
              rows={3}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none resize-none"
            />
          </div>
        </div>

        {/* Footer Actions */}
        <div className="sticky bottom-0 bg-white rounded-b-2xl border-t border-gray-100 px-6 py-4 flex items-center justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => { if (canSubmit) { onCreate(); onClose(); } }}
            disabled={!canSubmit}
            className={`px-4 py-2 text-sm font-medium text-white rounded-lg transition-colors ${
              canSubmit
                ? 'bg-[#1e3a5f] hover:bg-[#2d5a87]'
                : 'bg-gray-300 cursor-not-allowed'
            }`}
          >
            Create PO
          </button>
        </div>
      </motion.div>
    </div>
  );
}

/* ─── Main Page ─── */
export default function PurchaseOrders() {
  const pos = useMemo(() => getPurchaseOrders(), []);
  const [showCreate, setShowCreate] = useState(false);
  const { toast, show } = useToast();

  const stats = useMemo(() => {
    const total = pos.length;
    const pending = pos.filter((p) => p.status === 'pending').length;
    const approved = pos.filter((p) => p.status === 'approved').length;
    const received = pos.filter((p) => p.status === 'received').length;
    return { total, pending, approved, received };
  }, [pos]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#0f172a]">Purchase Orders</h1>
          <p className="text-sm text-gray-500 mt-1">PO builder and tracker</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2.5 bg-[#1e3a5f] text-white rounded-lg hover:bg-[#2d5a87] transition-colors text-sm font-medium"
        >
          <Plus size={18} />
          Create PO
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total POs" value={stats.total} color="#0f172a" />
        <StatCard label="Pending" value={stats.pending} color="#f59e0b" />
        <StatCard label="Approved" value={stats.approved} color="#10b981" />
        <StatCard label="Received" value={stats.received} color="#0ea5e9" />
      </div>

      {/* PO Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
        {pos.map((po) => (
          <POCard key={po.id} po={po} />
        ))}
      </div>

      {/* Create PO Dialog */}
      {showCreate && (
        <CreatePODialog
          onClose={() => setShowCreate(false)}
          onCreate={() => show('Purchase order created successfully', 'success')}
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
