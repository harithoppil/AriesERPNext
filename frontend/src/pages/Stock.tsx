import { useState, useMemo } from 'react';
import { getStock } from '@/lib/api';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Package,
  Plus,
  Search,
  CheckCircle,
  AlertTriangle,
  ShieldAlert,
  TrendingUp,
} from 'lucide-react';

const WAREHOUSES = ['All', 'Jebel Ali', 'Mussafah', 'Das Island'];

const CATEGORIES = [
  'All',
  'ROV Spares',
  'NDT Consumables',
  'Diving Equipment',
  'Crane Spares',
  'Communication',
  'Survey Equipment',
];

const WAREHOUSE_COLORS: Record<string, string> = {
  'Jebel Ali': 'bg-blue-100 text-blue-700',
  Mussafah: 'bg-green-100 text-green-700',
  'Das Island': 'bg-purple-100 text-purple-700',
};

const CATEGORY_COLORS: Record<string, string> = {
  'ROV Spares': 'bg-blue-100 text-blue-700',
  'NDT Consumables': 'bg-purple-100 text-purple-700',
  'Diving Equipment': 'bg-teal-100 text-teal-700',
  'Crane Spares': 'bg-orange-100 text-orange-700',
  Communication: 'bg-gray-100 text-gray-700',
  'Survey Equipment': 'bg-green-100 text-green-700',
};

const STATUS_CONFIG = {
  adequate: {
    label: 'Adequate',
    badge: 'bg-green-100 text-green-700',
    icon: CheckCircle,
    qtyClass: 'text-green-600',
    indicator: 'bg-green-500',
  },
  low: {
    label: 'Low',
    badge: 'bg-amber-100 text-amber-700',
    icon: AlertTriangle,
    qtyClass: 'text-amber-600',
    indicator: 'bg-amber-500',
  },
  critical: {
    label: 'Critical',
    badge: 'bg-red-100 text-red-700',
    icon: ShieldAlert,
    qtyClass: 'text-red-600',
    indicator: 'bg-red-500',
  },
};

function getStockPercentage(
  quantity: number,
  reorderLevel: number
): number {
  if (reorderLevel <= 0) return 100;
  return Math.min(100, Math.round((quantity / (reorderLevel * 2)) * 100));
}

export default function Stock() {
  const [warehouseFilter, setWarehouseFilter] = useState('All');
  const [categoryFilter, setCategoryFilter] = useState('All');
  const [searchQuery, setSearchQuery] = useState('');

  const stockItems = getStock();

  const filteredItems = useMemo(() => {
    return stockItems.filter((item) => {
      const matchesWarehouse =
        warehouseFilter === 'All' || item.warehouse === warehouseFilter;
      const matchesCategory =
        categoryFilter === 'All' || item.category === categoryFilter;
      const matchesSearch =
        !searchQuery ||
        item.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.sku.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.category.toLowerCase().includes(searchQuery.toLowerCase());
      return matchesWarehouse && matchesCategory && matchesSearch;
    });
  }, [stockItems, warehouseFilter, categoryFilter, searchQuery]);

  const stats = useMemo(() => {
    const base =
      warehouseFilter === 'All' && categoryFilter === 'All'
        ? stockItems
        : filteredItems;
    const totalValue = base.reduce(
      (sum, item) => sum + item.quantity * item.unitCost,
      0
    );
    return {
      totalItems: base.length,
      lowStock: base.filter((i) => i.status === 'low').length,
      reorderRequired: base.filter((i) => i.status === 'critical').length,
      totalValue,
    };
  }, [stockItems, filteredItems, warehouseFilter, categoryFilter]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-[#0f172a]">Stock Inventory</h2>
          <p className="text-sm text-[#64748b] mt-1">
            {filteredItems.length} items
          </p>
        </div>
        <button className="inline-flex items-center gap-2 bg-[#1e3a5f] text-white hover:bg-[#2d5a87] rounded-lg px-4 py-2.5 text-sm font-medium transition-colors w-fit">
          <Plus size={16} />
          Add Item
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
          <div className="flex items-center gap-2 mb-2">
            <Package size={16} className="text-[#0ea5e9]" />
            <span className="text-xs font-medium text-[#64748b] uppercase">
              Total Items
            </span>
          </div>
          <p className="text-2xl font-bold text-[#0f172a]">
            {stats.totalItems}
          </p>
        </div>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle size={16} className="text-amber-500" />
            <span className="text-xs font-medium text-[#64748b] uppercase">
              Low Stock
            </span>
          </div>
          <p className="text-2xl font-bold text-[#0f172a]">
            {stats.lowStock}
          </p>
        </div>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
          <div className="flex items-center gap-2 mb-2">
            <ShieldAlert size={16} className="text-red-500" />
            <span className="text-xs font-medium text-[#64748b] uppercase">
              Reorder Required
            </span>
          </div>
          <p className="text-2xl font-bold text-[#0f172a]">
            {stats.reorderRequired}
          </p>
        </div>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp size={16} className="text-green-500" />
            <span className="text-xs font-medium text-[#64748b] uppercase">
              Total Value
            </span>
          </div>
          <p className="text-2xl font-bold text-[#0f172a]">
            AED {stats.totalValue.toLocaleString()}
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1 max-w-md">
          <Search
            size={16}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-[#94a3b8]"
          />
          <Input
            placeholder="Search stock items..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9 border-[#e2e8f0] rounded-lg focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent"
          />
        </div>
        <Select value={warehouseFilter} onValueChange={setWarehouseFilter}>
          <SelectTrigger className="w-[180px] border-[#e2e8f0] rounded-lg focus:ring-2 focus:ring-[#0ea5e9]">
            <SelectValue placeholder="All Warehouses" />
          </SelectTrigger>
          <SelectContent>
            {WAREHOUSES.map((w) => (
              <SelectItem key={w} value={w}>
                {w}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={categoryFilter} onValueChange={setCategoryFilter}>
          <SelectTrigger className="w-[200px] border-[#e2e8f0] rounded-lg focus:ring-2 focus:ring-[#0ea5e9]">
            <SelectValue placeholder="All Categories" />
          </SelectTrigger>
          <SelectContent>
            {CATEGORIES.map((c) => (
              <SelectItem key={c} value={c}>
                {c}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-gray-50 hover:bg-gray-50">
                <TableHead className="text-gray-700 font-semibold text-sm">
                  SKU
                </TableHead>
                <TableHead className="text-gray-700 font-semibold text-sm">
                  Item Name
                </TableHead>
                <TableHead className="text-gray-700 font-semibold text-sm">
                  Category
                </TableHead>
                <TableHead className="text-gray-700 font-semibold text-sm">
                  Qty
                </TableHead>
                <TableHead className="text-gray-700 font-semibold text-sm">
                  Warehouse
                </TableHead>
                <TableHead className="text-gray-700 font-semibold text-sm">
                  Reorder Level
                </TableHead>
                <TableHead className="text-gray-700 font-semibold text-sm">
                  Unit Cost
                </TableHead>
                <TableHead className="text-gray-700 font-semibold text-sm">
                  Status
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredItems.map((item) => {
                const config = STATUS_CONFIG[item.status];
                const StatusIcon = config.icon;
                const stockPct = getStockPercentage(
                  item.quantity,
                  item.reorderLevel
                );

                return (
                  <TableRow
                    key={item.id}
                    className="hover:bg-gray-50 transition-colors border-b border-gray-100"
                  >
                    <TableCell className="font-mono text-xs text-[#64748b]">
                      {item.sku}
                    </TableCell>
                    <TableCell className="font-medium text-[#0f172a] text-sm">
                      {item.name}
                    </TableCell>
                    <TableCell>
                      <span
                        className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                          CATEGORY_COLORS[item.category] ||
                          'bg-gray-100 text-gray-700'
                        }`}
                      >
                        {item.category}
                      </span>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <span
                          className={`text-sm font-semibold ${config.qtyClass}`}
                        >
                          {item.quantity}
                        </span>
                        {/* Stock level mini bar */}
                        <div className="w-12 h-1.5 bg-gray-100 rounded-full overflow-hidden flex-shrink-0">
                          <div
                            className={`h-full rounded-full ${config.indicator}`}
                            style={{ width: `${stockPct}%` }}
                          />
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <span
                        className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                          WAREHOUSE_COLORS[item.warehouse] ||
                          'bg-gray-100 text-gray-700'
                        }`}
                      >
                        {item.warehouse}
                      </span>
                    </TableCell>
                    <TableCell className="text-sm text-[#64748b]">
                      {item.reorderLevel}
                    </TableCell>
                    <TableCell className="text-sm text-[#64748b]">
                      AED {item.unitCost.toLocaleString()}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1.5">
                        <span
                          className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${config.badge}`}
                        >
                          <StatusIcon size={12} />
                          {config.label}
                        </span>
                        {item.status === 'critical' && (
                          <span className="inline-flex items-center rounded bg-red-600 text-white px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider">
                            Reorder
                          </span>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </div>

      {filteredItems.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-[#94a3b8]">
          <Package size={48} className="mb-4 opacity-40" />
          <p className="text-lg font-medium">No items found</p>
          <p className="text-sm">
            Try adjusting your filters or search query
          </p>
        </div>
      )}
    </div>
  );
}
