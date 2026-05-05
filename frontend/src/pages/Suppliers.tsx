import { useState, useMemo } from 'react';
import { motion } from 'framer-motion';
import {
  Building2, Mail, Phone, MapPin, Star, Plus, X, Eye, Pencil,
} from 'lucide-react';
import type { Supplier } from '@/types';
import { getSuppliers } from '@/lib/api';

/* ─── Star Rating ─── */
function StarRating({ rating }: { rating: number }) {
  const fullStars = Math.floor(rating);
  const hasHalf = rating - fullStars >= 0.5;
  const emptyStars = 5 - fullStars - (hasHalf ? 1 : 0);

  return (
    <div className="flex items-center gap-1">
      <div className="flex items-center">
        {Array.from({ length: fullStars }).map((_, i) => (
          <Star key={`f-${i}`} size={15} className="text-amber-400 fill-amber-400" />
        ))}
        {hasHalf && (
          <div className="relative">
            <Star size={15} className="text-gray-200 fill-gray-200" />
            <div className="absolute inset-0 overflow-hidden w-1/2">
              <Star size={15} className="text-amber-400 fill-amber-400" />
            </div>
          </div>
        )}
        {Array.from({ length: emptyStars }).map((_, i) => (
          <Star key={`e-${i}`} size={15} className="text-gray-200 fill-gray-200" />
        ))}
      </div>
      <span className="text-xs font-medium text-gray-500 ml-1">{rating.toFixed(1)}</span>
    </div>
  );
}

/* ─── Toast ─── */
function useToast() {
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'info' } | null>(null);
  const show = (message: string, type: 'success' | 'info' = 'info') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 2500);
  };
  return { toast, show };
}

/* ─── Supplier Card ─── */
function SupplierCard({ supplier, onView, onEdit }: {
  supplier: Supplier;
  onView: (s: Supplier) => void;
  onEdit: (s: Supplier) => void;
}) {
  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 hover:shadow-md transition-shadow duration-200 p-5">
      {/* Icon + Name */}
      <div className="flex items-start gap-3 mb-3">
        <div className="w-11 h-11 rounded-xl bg-[#1e3a5f]/10 flex items-center justify-center flex-shrink-0">
          <Building2 size={22} className="text-[#1e3a5f]" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold text-sm text-[#0f172a] truncate">{supplier.name}</h3>
          <StarRating rating={supplier.rating} />
        </div>
      </div>

      {/* Divider */}
      <div className="border-t border-gray-100 my-3" />

      {/* Contact Info */}
      <div className="space-y-2 text-sm mb-3">
        <div className="flex items-center gap-2 text-gray-600">
          <Mail size={14} className="text-gray-400 flex-shrink-0" />
          <span className="truncate">{supplier.email}</span>
        </div>
        <div className="flex items-center gap-2 text-gray-600">
          <Phone size={14} className="text-gray-400 flex-shrink-0" />
          <span>{supplier.phone}</span>
        </div>
        <div className="flex items-start gap-2 text-gray-600">
          <MapPin size={14} className="text-gray-400 flex-shrink-0 mt-0.5" />
          <span>{supplier.address}</span>
        </div>
      </div>

      {/* Divider */}
      <div className="border-t border-gray-100 my-3" />

      {/* Meta */}
      <div className="flex items-center justify-between text-sm mb-4">
        <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-[#0ea5e9]/10 text-[#0ea5e9]">
          {supplier.category}
        </span>
        <span className="text-xs text-gray-500">
          Terms: <span className="font-medium text-gray-700">{supplier.paymentTerms}</span>
        </span>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => onView(supplier)}
          className="flex-1 flex items-center justify-center gap-1.5 py-2 text-xs font-medium text-[#1e3a5f] bg-[#1e3a5f]/5 hover:bg-[#1e3a5f]/10 rounded-lg transition-colors"
        >
          <Eye size={14} />
          View
        </button>
        <button
          onClick={() => onEdit(supplier)}
          className="flex-1 flex items-center justify-center gap-1.5 py-2 text-xs font-medium text-gray-600 bg-gray-50 hover:bg-gray-100 rounded-lg transition-colors"
        >
          <Pencil size={14} />
          Edit
        </button>
      </div>
    </div>
  );
}

/* ─── Add Supplier Dialog ─── */
function AddSupplierDialog({ onClose, onAdd }: { onClose: () => void; onAdd: () => void }) {
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
          <h2 className="text-lg font-semibold text-[#0f172a]">Add Supplier</h2>
          <button onClick={onClose} className="p-1.5 hover:bg-gray-100 rounded-lg transition-colors">
            <X size={18} className="text-gray-500" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Company Name</label>
            <input
              type="text"
              placeholder="Enter company name"
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Category</label>
            <select className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none bg-white">
              <option value="">Select category</option>
              <option value="ROV Equipment">ROV Equipment</option>
              <option value="NDT Equipment">NDT Equipment</option>
              <option value="Crane Equipment">Crane Equipment</option>
              <option value="Diving Equipment">Diving Equipment</option>
              <option value="Survey Equipment">Survey Equipment</option>
              <option value="Communication">Communication</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
            <input
              type="email"
              placeholder="contact@supplier.com"
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Phone</label>
            <input
              type="tel"
              placeholder="+971 4 XXX XXXX"
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Address</label>
            <input
              type="text"
              placeholder="Location"
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Payment Terms</label>
            <select className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none bg-white">
              <option value="">Select terms</option>
              <option value="Net 30">Net 30</option>
              <option value="Net 45">Net 45</option>
              <option value="Net 60">Net 60</option>
              <option value="Cash on Delivery">Cash on Delivery</option>
            </select>
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
            onClick={() => { onAdd(); onClose(); }}
            className="px-4 py-2 text-sm font-medium text-white bg-[#1e3a5f] hover:bg-[#2d5a87] rounded-lg transition-colors"
          >
            Add Supplier
          </button>
        </div>
      </motion.div>
    </div>
  );
}

/* ─── Main Page ─── */
export default function Suppliers() {
  const suppliers = useMemo(() => getSuppliers(), []);
  const [showAdd, setShowAdd] = useState(false);
  const { toast, show } = useToast();

  const handleView = (s: Supplier) => show(`Viewing ${s.name}`, 'info');
  const handleEdit = (s: Supplier) => show(`Editing ${s.name}`, 'info');

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#0f172a]">Suppliers</h1>
          <p className="text-sm text-gray-500 mt-1">Supplier and vendor directory</p>
        </div>
        <button
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-2 px-4 py-2.5 bg-[#1e3a5f] text-white rounded-lg hover:bg-[#2d5a87] transition-colors text-sm font-medium"
        >
          <Plus size={18} />
          Add Supplier
        </button>
      </div>

      {/* Suppliers Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
        {suppliers.map((s) => (
          <SupplierCard key={s.id} supplier={s} onView={handleView} onEdit={handleEdit} />
        ))}
      </div>

      {/* Add Supplier Dialog */}
      {showAdd && (
        <AddSupplierDialog
          onClose={() => setShowAdd(false)}
          onAdd={() => show('Supplier added successfully', 'success')}
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
