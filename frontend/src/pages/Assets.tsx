import { useState, useMemo } from 'react';
import { getAssets } from '@/lib/api';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Wrench, CheckCircle, AlertTriangle, XCircle } from 'lucide-react';
import { format, parseISO } from 'date-fns';

const CATEGORIES = ['All', 'ROV', 'NDT', 'Crane', 'Diving', 'Survey', 'Communication'];

const CATEGORY_COLORS: Record<string, string> = {
  ROV: 'bg-blue-100 text-blue-700',
  NDT: 'bg-purple-100 text-purple-700',
  Crane: 'bg-orange-100 text-orange-700',
  Diving: 'bg-teal-100 text-teal-700',
  Survey: 'bg-green-100 text-green-700',
  Communication: 'bg-gray-100 text-gray-700',
};

const STATUS_CONFIG = {
  calibrated: {
    label: 'Calibrated',
    dot: 'bg-green-500',
    badge: 'bg-green-100 text-green-700',
    icon: CheckCircle,
  },
  'due-soon': {
    label: 'Due Soon',
    dot: 'bg-amber-500',
    badge: 'bg-amber-100 text-amber-700',
    icon: AlertTriangle,
  },
  overdue: {
    label: 'Overdue',
    dot: 'bg-red-500',
    badge: 'bg-red-100 text-red-700',
    icon: XCircle,
  },
};

export default function Assets() {
  const [activeCategory, setActiveCategory] = useState('All');

  const assets = getAssets();

  const filteredAssets = useMemo(() => {
    if (activeCategory === 'All') return assets;
    return assets.filter((a) => a.category === activeCategory);
  }, [assets, activeCategory]);

  const stats = useMemo(() => {
    const filtered = activeCategory === 'All' ? assets : filteredAssets;
    return {
      total: filtered.length,
      calibrated: filtered.filter((a) => a.status === 'calibrated').length,
      dueSoon: filtered.filter((a) => a.status === 'due-soon').length,
      overdue: filtered.filter((a) => a.status === 'overdue').length,
    };
  }, [assets, filteredAssets, activeCategory]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-[#0f172a]">Assets</h2>
          <p className="text-sm text-[#64748b] mt-1">
            {activeCategory === 'All'
              ? `${assets.length} total assets`
              : `${filteredAssets.length} ${activeCategory} assets`}
          </p>
        </div>
      </div>

      {/* Category Filter Chips */}
      <div className="flex flex-wrap gap-2">
        {CATEGORIES.map((cat) => (
          <button
            key={cat}
            onClick={() => setActiveCategory(cat)}
            className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
              activeCategory === cat
                ? 'bg-[#1e3a5f] text-white'
                : 'bg-gray-100 text-[#64748b] hover:bg-gray-200'
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
          <div className="flex items-center gap-2 mb-2">
            <Wrench size={16} className="text-[#64748b]" />
            <span className="text-xs font-medium text-[#64748b] uppercase">
              Total
            </span>
          </div>
          <p className="text-2xl font-bold text-[#0f172a]">{stats.total}</p>
        </div>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
          <div className="flex items-center gap-2 mb-2">
            <CheckCircle size={16} className="text-green-500" />
            <span className="text-xs font-medium text-[#64748b] uppercase">
              Calibrated
            </span>
          </div>
          <p className="text-2xl font-bold text-[#0f172a]">{stats.calibrated}</p>
        </div>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle size={16} className="text-amber-500" />
            <span className="text-xs font-medium text-[#64748b] uppercase">
              Due Soon
            </span>
          </div>
          <p className="text-2xl font-bold text-[#0f172a]">{stats.dueSoon}</p>
        </div>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
          <div className="flex items-center gap-2 mb-2">
            <XCircle size={16} className="text-red-500" />
            <span className="text-xs font-medium text-[#64748b] uppercase">
              Overdue
            </span>
          </div>
          <p className="text-2xl font-bold text-[#0f172a]">{stats.overdue}</p>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-gray-50 hover:bg-gray-50">
                <TableHead className="text-gray-700 font-semibold text-sm">
                  Asset ID
                </TableHead>
                <TableHead className="text-gray-700 font-semibold text-sm">
                  Name
                </TableHead>
                <TableHead className="text-gray-700 font-semibold text-sm">
                  Category
                </TableHead>
                <TableHead className="text-gray-700 font-semibold text-sm">
                  Serial #
                </TableHead>
                <TableHead className="text-gray-700 font-semibold text-sm">
                  Location
                </TableHead>
                <TableHead className="text-gray-700 font-semibold text-sm">
                  Last Calibration
                </TableHead>
                <TableHead className="text-gray-700 font-semibold text-sm">
                  Next Calibration
                </TableHead>
                <TableHead className="text-gray-700 font-semibold text-sm">
                  Status
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredAssets.map((asset) => {
                const config = STATUS_CONFIG[asset.status];
                const StatusIcon = config.icon;

                return (
                  <TableRow
                    key={asset.id}
                    className="hover:bg-gray-50 transition-colors border-b border-gray-100"
                  >
                    <TableCell className="font-mono text-xs text-[#64748b]">
                      #{asset.id.toUpperCase().replace('AST-', 'AST-')}
                    </TableCell>
                    <TableCell className="font-medium text-[#0f172a]">
                      {asset.name}
                    </TableCell>
                    <TableCell>
                      <span
                        className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                          CATEGORY_COLORS[asset.category] ||
                          'bg-gray-100 text-gray-700'
                        }`}
                      >
                        {asset.category}
                      </span>
                    </TableCell>
                    <TableCell className="font-mono text-xs text-[#64748b]">
                      {asset.serialNumber}
                    </TableCell>
                    <TableCell className="text-sm text-[#64748b]">
                      {asset.location}
                    </TableCell>
                    <TableCell className="text-sm text-[#64748b]">
                      {format(
                        parseISO(asset.lastCalibration),
                        'MMM d, yyyy'
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <span
                          className={`w-2 h-2 rounded-full flex-shrink-0 ${config.dot}`}
                        />
                        <span className="text-sm text-[#64748b]">
                          {format(
                            parseISO(asset.nextCalibration),
                            'MMM d, yyyy'
                          )}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <span
                        className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${config.badge}`}
                      >
                        <StatusIcon size={12} />
                        {config.label}
                      </span>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </div>

      {filteredAssets.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-[#94a3b8]">
          <Wrench size={48} className="mb-4 opacity-40" />
          <p className="text-lg font-medium">No assets found</p>
          <p className="text-sm">Select a different category filter</p>
        </div>
      )}
    </div>
  );
}
