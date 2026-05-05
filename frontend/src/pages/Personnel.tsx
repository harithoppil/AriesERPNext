import { useState, useMemo } from 'react';
import { getPersonnel } from '@/lib/api';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Search,
  Plus,
  Mail,
  Phone,
  MapPin,
  ShieldCheck,
  ShieldAlert,
  AlertTriangle,
  User,
} from 'lucide-react';
import { format, differenceInDays, parseISO } from 'date-fns';

const DEPARTMENTS = [
  'All',
  'Operations',
  'Engineering',
  'Sales',
  'Inspection',
  'Finance',
  'HSE',
  'Maintenance',
  'Projects',
  'Survey',
  'Procurement',
  'HR',
];

function getInitials(name: string): string {
  return name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

function getDaysUntilExpiry(expiryDate?: string): number | null {
  if (!expiryDate) return null;
  try {
    return differenceInDays(parseISO(expiryDate), new Date());
  } catch {
    return null;
  }
}

function CertBadge({
  cert,
}: {
  cert: {
    name: string;
    status: 'valid' | 'expiring' | 'expired';
    expiryDate?: string;
    level?: string;
  };
}) {
  const daysLeft = getDaysUntilExpiry(cert.expiryDate);
  const displayName = cert.name;
  const levelText = cert.level ? ` (${cert.level})` : '';

  if (cert.status === 'expired') {
    return (
      <div
        className="inline-flex items-center gap-1 bg-red-100 text-red-700 border border-red-200 rounded-full px-2.5 py-0.5 text-xs font-medium"
        title={cert.expiryDate ? `Expired on ${format(parseISO(cert.expiryDate), 'MMM d, yyyy')}` : 'Expired'}
      >
        <ShieldAlert size={12} />
        <span>
          {displayName}
          {levelText}
        </span>
      </div>
    );
  }

  if (cert.status === 'expiring') {
    return (
      <div
        className="inline-flex items-center gap-1 bg-amber-100 text-amber-700 border border-amber-200 rounded-full px-2.5 py-0.5 text-xs font-medium"
        title={
          daysLeft !== null
            ? `Expires in ${daysLeft} day${daysLeft !== 1 ? 's' : ''} (${format(parseISO(cert.expiryDate!), 'MMM d, yyyy')})`
            : 'Expiring soon'
        }
      >
        <AlertTriangle size={12} />
        <span>
          {displayName}
          {levelText}
        </span>
      </div>
    );
  }

  return (
    <div
      className="inline-flex items-center gap-1 bg-green-100 text-green-700 border border-green-200 rounded-full px-2.5 py-0.5 text-xs font-medium"
      title={cert.expiryDate ? `Valid until ${format(parseISO(cert.expiryDate), 'MMM d, yyyy')}` : 'Valid'}
    >
      <ShieldCheck size={12} />
      <span>
        {displayName}
        {levelText}
      </span>
    </div>
  );
}

const DEPARTMENT_COLORS: Record<string, string> = {
  Operations: 'bg-[#1e3a5f] text-white',
  Engineering: 'bg-[#0ea5e9] text-white',
  Sales: 'bg-green-600 text-white',
  Inspection: 'bg-purple-600 text-white',
  Finance: 'bg-amber-600 text-white',
  HSE: 'bg-red-600 text-white',
  Maintenance: 'bg-slate-600 text-white',
  Projects: 'bg-teal-600 text-white',
  Survey: 'bg-indigo-600 text-white',
  Procurement: 'bg-pink-600 text-white',
  HR: 'bg-rose-500 text-white',
};

export default function Personnel() {
  const [departmentFilter, setDepartmentFilter] = useState('All');
  const [searchQuery, setSearchQuery] = useState('');

  const personnel = getPersonnel();

  const filteredPersonnel = useMemo(() => {
    return personnel.filter((emp) => {
      const matchesDept =
        departmentFilter === 'All' || emp.department === departmentFilter;
      const matchesSearch =
        !searchQuery ||
        emp.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        emp.role.toLowerCase().includes(searchQuery.toLowerCase()) ||
        emp.email.toLowerCase().includes(searchQuery.toLowerCase()) ||
        emp.location.toLowerCase().includes(searchQuery.toLowerCase());
      return matchesDept && matchesSearch;
    });
  }, [personnel, departmentFilter, searchQuery]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-[#0f172a]">Personnel</h2>
          <p className="text-sm text-[#64748b] mt-1">
            {personnel.length} employees
          </p>
        </div>
        <button className="inline-flex items-center gap-2 bg-[#1e3a5f] text-white hover:bg-[#2d5a87] rounded-lg px-4 py-2.5 text-sm font-medium transition-colors w-fit">
          <Plus size={16} />
          Add Employee
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1 max-w-md">
          <Search
            size={16}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-[#94a3b8]"
          />
          <Input
            placeholder="Search employees..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9 border-[#e2e8f0] rounded-lg focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent"
          />
        </div>
        <Select value={departmentFilter} onValueChange={setDepartmentFilter}>
          <SelectTrigger className="w-[200px] border-[#e2e8f0] rounded-lg focus:ring-2 focus:ring-[#0ea5e9]">
            <SelectValue placeholder="All Departments" />
          </SelectTrigger>
          <SelectContent>
            {DEPARTMENTS.map((dept) => (
              <SelectItem key={dept} value={dept}>
                {dept}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Employee Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {filteredPersonnel.map((emp) => (
          <div
            key={emp.id}
            className="bg-white rounded-2xl shadow-sm border border-gray-100 hover:shadow-md transition-shadow duration-200 p-5"
          >
            {/* Avatar + Name */}
            <div className="flex items-start gap-3">
              <div className="w-12 h-12 rounded-full bg-[#1e3a5f] flex items-center justify-center text-white text-sm font-semibold flex-shrink-0">
                {emp.avatar ? (
                  <img
                    src={emp.avatar}
                    alt={emp.name}
                    className="w-full h-full rounded-full object-cover"
                  />
                ) : (
                  getInitials(emp.name)
                )}
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="font-semibold text-[#0f172a] truncate">
                  {emp.name}
                </h3>
                <p className="text-sm text-[#64748b]">{emp.role}</p>
                <span
                  className={`inline-block mt-1.5 text-[10px] font-semibold uppercase tracking-wider rounded-full px-2 py-0.5 ${
                    DEPARTMENT_COLORS[emp.department] ||
                    'bg-gray-100 text-gray-700'
                  }`}
                >
                  {emp.department}
                </span>
              </div>
            </div>

            {/* Divider */}
            <div className="border-t border-gray-100 my-4" />

            {/* Contact Info */}
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm text-[#64748b]">
                <Mail size={14} className="text-[#94a3b8] flex-shrink-0" />
                <span className="truncate">{emp.email}</span>
              </div>
              <div className="flex items-center gap-2 text-sm text-[#64748b]">
                <Phone size={14} className="text-[#94a3b8] flex-shrink-0" />
                <span>{emp.phone}</span>
              </div>
              <div className="flex items-center gap-2 text-sm text-[#64748b]">
                <MapPin size={14} className="text-[#94a3b8] flex-shrink-0" />
                <span>{emp.location}</span>
              </div>
            </div>

            {/* Divider */}
            <div className="border-t border-gray-100 my-4" />

            {/* Certifications */}
            <div>
              <p className="text-xs font-medium text-[#94a3b8] uppercase tracking-wider mb-2">
                Certifications
              </p>
              {emp.certifications.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {emp.certifications.map((cert, idx) => (
                    <CertBadge key={idx} cert={cert} />
                  ))}
                </div>
              ) : (
                <p className="text-xs text-[#94a3b8] italic">
                  No certifications on file
                </p>
              )}
            </div>
          </div>
        ))}
      </div>

      {filteredPersonnel.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-[#94a3b8]">
          <User size={48} className="mb-4 opacity-40" />
          <p className="text-lg font-medium">No employees found</p>
          <p className="text-sm">
            Try adjusting your search or department filter
          </p>
        </div>
      )}
    </div>
  );
}
