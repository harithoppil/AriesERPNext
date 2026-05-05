import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { getEnquiries } from '@/lib/api';
import {
  Table, TableHeader, TableBody, TableHead, TableRow, TableCell,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Inbox, Plus, Search, User, Calendar, DollarSign,
} from 'lucide-react';

const STATUS_OPTIONS = [
  { value: 'all', label: 'All Statuses' },
  { value: 'new', label: 'New' },
  { value: 'qualified', label: 'Qualified' },
  { value: 'proposal', label: 'Proposal' },
  { value: 'negotiation', label: 'Negotiation' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
];

const STATUS_BADGE: Record<string, string> = {
  new: 'bg-blue-100 text-blue-700',
  qualified: 'bg-purple-100 text-purple-700',
  proposal: 'bg-amber-100 text-amber-700',
  negotiation: 'bg-orange-100 text-orange-700',
  approved: 'bg-green-100 text-green-700',
  rejected: 'bg-red-100 text-red-700',
};

const STATUS_LABEL: Record<string, string> = {
  new: 'New',
  qualified: 'Qualified',
  proposal: 'Proposal',
  negotiation: 'Negotiation',
  approved: 'Approved',
  rejected: 'Rejected',
};

const SERVICE_PILL: Record<string, string> = {
  'ROV Inspection': 'bg-cyan-100 text-cyan-700',
  'Crane Rental': 'bg-orange-100 text-orange-700',
  'Diving Support': 'bg-indigo-100 text-indigo-700',
  'NDT Inspection': 'bg-teal-100 text-teal-700',
  'Subsea Cable Laying': 'bg-violet-100 text-violet-700',
  'Platform Maintenance': 'bg-gray-100 text-gray-700',
  'Survey Services': 'bg-emerald-100 text-emerald-700',
  'Communication Systems': 'bg-pink-100 text-pink-700',
};

function formatCurrency(value: number, currency: string): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    maximumFractionDigits: 0,
    notation: 'compact',
  }).format(value);
}

function formatRelativeDate(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date('2026-05-05');
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays} days ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function getInitials(name: string): string {
  return name
    .split(' ')
    .map((w) => w[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

function Avatar({ name }: { name: string }) {
  return (
    <div className="w-8 h-8 rounded-full bg-[#1e3a5f] flex items-center justify-center text-white text-xs font-semibold flex-shrink-0">
      {getInitials(name)}
    </div>
  );
}

export default function EnquiriesList() {
  const navigate = useNavigate();
  const enquiries = getEnquiries();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');

  const stats = useMemo(() => {
    const total = enquiries.length;
    const newCount = enquiries.filter((e) => e.status === 'new').length;
    const qualified = enquiries.filter((e) => e.status === 'qualified').length;
    const approved = enquiries.filter((e) => e.status === 'approved').length;
    return { total, new: newCount, qualified, approved };
  }, [enquiries]);

  const filtered = useMemo(() => {
    return enquiries.filter((e) => {
      const matchesSearch =
        !search ||
        e.client.toLowerCase().includes(search.toLowerCase()) ||
        e.service.toLowerCase().includes(search.toLowerCase()) ||
        e.id.toLowerCase().includes(search.toLowerCase());
      const matchesStatus =
        statusFilter === 'all' || e.status === statusFilter;
      return matchesSearch && matchesStatus;
    });
  }, [enquiries, search, statusFilter]);

  const statCards = [
    { label: 'Total', value: stats.total, icon: Inbox, color: 'text-gray-700 bg-gray-50' },
    { label: 'New', value: stats.new, icon: Inbox, color: 'text-blue-700 bg-blue-50' },
    { label: 'Qualified', value: stats.qualified, icon: User, color: 'text-purple-700 bg-purple-50' },
    { label: 'Approved', value: stats.approved, icon: DollarSign, color: 'text-green-700 bg-green-50' },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-[#0f172a]">Enquiries</h2>
          <p className="text-sm text-gray-500 mt-0.5">
            Manage and track sales enquiries
          </p>
        </div>
        <button
          type="button"
          className="inline-flex items-center gap-2 px-4 py-2.5 bg-[#0ea5e9] hover:bg-[#0284c7] text-white rounded-lg font-medium text-sm transition-colors shadow-sm"
        >
          <Plus size={18} />
          New Enquiry
        </button>
      </div>

      {/* Stats Bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {statCards.map((card) => {
          const Icon = card.icon;
          return (
            <div
              key={card.label}
              className="bg-white rounded-xl border border-gray-100 shadow-sm p-4 flex items-center gap-3"
            >
              <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${card.color}`}>
                <Icon size={20} />
              </div>
              <div>
                <p className="text-2xl font-bold text-[#0f172a]">{card.value}</p>
                <p className="text-xs text-gray-500">{card.label}</p>
              </div>
            </div>
          );
        })}
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between">
        <div className="relative w-full sm:w-80">
          <Search
            size={18}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
          />
          <Input
            placeholder="Search client, service..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10 border-gray-200 rounded-lg focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent"
          />
        </div>
        <div className="flex items-center gap-2 w-full sm:w-auto">
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-full sm:w-44 border-gray-200 rounded-lg focus:ring-2 focus:ring-[#0ea5e9]">
              <SelectValue placeholder="Filter by status" />
            </SelectTrigger>
            <SelectContent>
              {STATUS_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <span className="text-xs text-gray-400 whitespace-nowrap flex-shrink-0">
            {filtered.length} result{filtered.length !== 1 ? 's' : ''}
          </span>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-gray-50 border-b border-gray-100">
                <TableHead className="text-gray-700 font-semibold text-sm pl-4">
                  ID
                </TableHead>
                <TableHead className="text-gray-700 font-semibold text-sm">
                  Client
                </TableHead>
                <TableHead className="text-gray-700 font-semibold text-sm">
                  Service
                </TableHead>
                <TableHead className="text-gray-700 font-semibold text-sm">
                  Value
                </TableHead>
                <TableHead className="text-gray-700 font-semibold text-sm">
                  Assigned To
                </TableHead>
                <TableHead className="text-gray-700 font-semibold text-sm">
                  Status
                </TableHead>
                <TableHead className="text-gray-700 font-semibold text-sm">
                  Date
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((enq) => (
                <TableRow
                  key={enq.id}
                  className="border-b border-gray-100 hover:bg-gray-50 transition-colors cursor-pointer"
                  onClick={() => navigate(`/enquiries/${enq.id}`)}
                >
                  <TableCell className="pl-4">
                    <span className="font-mono text-sm font-medium text-[#0f172a]">
                      #{enq.id.toUpperCase()}
                    </span>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2.5">
                      <Avatar name={enq.client} />
                      <span className="font-medium text-sm text-[#0f172a]">
                        {enq.client}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <span
                      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                        SERVICE_PILL[enq.service] || 'bg-gray-100 text-gray-700'
                      }`}
                    >
                      {enq.service}
                    </span>
                  </TableCell>
                  <TableCell>
                    <span className="font-medium text-sm text-[#0f172a]">
                      {formatCurrency(enq.value, enq.currency)}
                    </span>
                  </TableCell>
                  <TableCell>
                    <span className="text-sm text-gray-600">
                      {enq.assignedTo}
                    </span>
                  </TableCell>
                  <TableCell>
                    <Badge
                      className={`${STATUS_BADGE[enq.status]} border-0 font-medium text-xs`}
                      variant="outline"
                    >
                      {STATUS_LABEL[enq.status]}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1.5 text-sm text-gray-500">
                      <Calendar size={14} className="text-gray-400" />
                      {formatRelativeDate(enq.date)}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
              {filtered.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={7}
                    className="text-center py-12 text-gray-400"
                  >
                    <Inbox size={32} className="mx-auto mb-2 text-gray-300" />
                    <p className="text-sm">No enquiries found</p>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
}
