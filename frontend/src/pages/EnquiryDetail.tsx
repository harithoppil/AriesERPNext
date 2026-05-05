import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getEnquiryById } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import {
  ArrowLeft, CheckCircle, XCircle, Send, FileText, User, Mail, Phone,
  Calendar, DollarSign, Briefcase, MessageSquare, Clock, Star, AlertTriangle,
} from 'lucide-react';

const STATUS_ORDER = ['new', 'qualified', 'proposal', 'negotiation', 'approved'];

const STATUS_LABEL: Record<string, string> = {
  new: 'New',
  qualified: 'Qualified',
  proposal: 'Proposal',
  negotiation: 'Negotiation',
  approved: 'Approved',
  rejected: 'Rejected',
};

const STATUS_BADGE: Record<string, string> = {
  new: 'bg-blue-100 text-blue-700',
  qualified: 'bg-purple-100 text-purple-700',
  proposal: 'bg-amber-100 text-amber-700',
  negotiation: 'bg-orange-100 text-orange-700',
  approved: 'bg-green-100 text-green-700',
  rejected: 'bg-red-100 text-red-700',
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

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

function getInitials(name: string): string {
  return name
    .split(' ')
    .map((w) => w[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

function Avatar({ name, size = 32 }: { name: string; size?: number }) {
  return (
    <div
      className="rounded-full bg-[#1e3a5f] flex items-center justify-center text-white text-xs font-semibold flex-shrink-0"
      style={{ width: size, height: size }}
    >
      {getInitials(name)}
    </div>
  );
}

export default function EnquiryDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const enquiry = getEnquiryById(id || '');
  const [noteText, setNoteText] = useState('');
  const [notes, setNotes] = useState<string[]>([]);

  if (!enquiry) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <AlertTriangle size={48} className="text-gray-300 mb-4" />
        <h2 className="text-xl font-semibold text-gray-700">Enquiry not found</h2>
        <p className="text-sm text-gray-500 mt-1 mb-6">
          The enquiry you are looking for does not exist.
        </p>
        <Button
          variant="outline"
          onClick={() => navigate('/enquiries')}
          className="gap-2"
        >
          <ArrowLeft size={16} />
          Back to Enquiries
        </Button>
      </div>
    );
  }

  const allNotes = [...enquiry.notes, ...notes];

  const handleAddNote = () => {
    if (!noteText.trim()) return;
    setNotes((prev) => [...prev, noteText.trim()]);
    setNoteText('');
  };

  // Timeline computation
  const currentIndex = STATUS_ORDER.indexOf(enquiry.status);
  const isRejected = enquiry.status === 'rejected';

  // Action buttons based on status
  const renderActions = () => {
    switch (enquiry.status) {
      case 'new':
        return (
          <div className="space-y-3">
            <Button className="w-full gap-2 bg-purple-600 hover:bg-purple-700 text-white">
              <CheckCircle size={16} />
              Qualify Enquiry
            </Button>
            <Button className="w-full gap-2" variant="destructive">
              <XCircle size={16} />
              Reject Enquiry
            </Button>
          </div>
        );
      case 'qualified':
        return (
          <div className="space-y-3">
            <Button className="w-full gap-2 bg-amber-500 hover:bg-amber-600 text-white">
              <Send size={16} />
              Send Proposal
            </Button>
            <Button className="w-full gap-2" variant="destructive">
              <XCircle size={16} />
              Reject Enquiry
            </Button>
          </div>
        );
      case 'proposal':
        return (
          <div className="space-y-3">
            <Button className="w-full gap-2 bg-orange-500 hover:bg-orange-600 text-white">
              <Star size={16} />
              Move to Negotiation
            </Button>
            <Button className="w-full gap-2" variant="destructive">
              <XCircle size={16} />
              Mark Lost
            </Button>
          </div>
        );
      case 'negotiation':
        return (
          <div className="space-y-3">
            <Button className="w-full gap-2 bg-green-600 hover:bg-green-700 text-white">
              <CheckCircle size={16} />
              Approve Enquiry
            </Button>
            <Button className="w-full gap-2" variant="destructive">
              <XCircle size={16} />
              Reject Enquiry
            </Button>
          </div>
        );
      case 'approved':
        return (
          <div className="p-4 bg-green-50 rounded-lg text-center">
            <CheckCircle size={32} className="text-green-500 mx-auto mb-2" />
            <p className="font-medium text-green-800">Approved</p>
            <p className="text-xs text-green-600 mt-1">
              This enquiry has been approved.
            </p>
          </div>
        );
      case 'rejected':
        return (
          <div className="p-4 bg-red-50 rounded-lg text-center">
            <XCircle size={32} className="text-red-500 mx-auto mb-2" />
            <p className="font-medium text-red-800">Rejected</p>
            <p className="text-xs text-red-600 mt-1">
              This enquiry has been rejected.
            </p>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <div className="space-y-6">
      {/* Back button */}
      <button
        type="button"
        onClick={() => navigate('/enquiries')}
        className="inline-flex items-center gap-2 text-sm text-gray-500 hover:text-[#0f172a] transition-colors"
      >
        <ArrowLeft size={18} />
        Back to Enquiries
      </button>

      {/* Enquiry Title Header */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <h2 className="text-2xl font-bold text-[#0f172a]">
              #{enquiry.id.toUpperCase()}
            </h2>
            <Badge
              className={`${STATUS_BADGE[enquiry.status]} border-0 font-medium text-xs`}
              variant="outline"
            >
              {STATUS_LABEL[enquiry.status]}
            </Badge>
          </div>
          <p className="text-sm text-gray-500">{enquiry.description}</p>
        </div>
        <div className="text-right">
          <p className="text-2xl font-bold text-[#0f172a]">
            {formatCurrency(enquiry.value, enquiry.currency)}
          </p>
          <p className="text-xs text-gray-400 mt-0.5">
            Created {formatDate(enquiry.date)}
          </p>
        </div>
      </div>

      {/* 3-Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Detail Card */}
        <Card className="rounded-xl border-gray-100 shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-semibold text-[#0f172a] flex items-center gap-2">
              <FileText size={18} className="text-gray-400" />
              Enquiry Details
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-5 pt-0">
            {/* Client */}
            <div>
              <p className="text-xs text-gray-400 uppercase tracking-wider mb-1.5">
                Client
              </p>
              <div className="flex items-center gap-2.5">
                <Avatar name={enquiry.client} />
                <span className="font-semibold text-[#0f172a]">
                  {enquiry.client}
                </span>
              </div>
            </div>

            {/* Contact */}
            <div>
              <p className="text-xs text-gray-400 uppercase tracking-wider mb-1.5">
                Contact Person
              </p>
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-sm text-[#0f172a]">
                  <User size={14} className="text-gray-400" />
                  {enquiry.contactName}
                </div>
                <div className="flex items-center gap-2 text-sm text-[#0f172a]">
                  <Mail size={14} className="text-gray-400" />
                  <a
                    href={`mailto:${enquiry.email}`}
                    className="text-[#0ea5e9] hover:underline"
                  >
                    {enquiry.email}
                  </a>
                </div>
                <div className="flex items-center gap-2 text-sm text-[#0f172a]">
                  <Phone size={14} className="text-gray-400" />
                  {enquiry.phone}
                </div>
              </div>
            </div>

            {/* Service */}
            <div>
              <p className="text-xs text-gray-400 uppercase tracking-wider mb-1.5">
                Service
              </p>
              <span
                className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-medium ${
                  SERVICE_PILL[enquiry.service] || 'bg-gray-100 text-gray-700'
                }`}
              >
                <Briefcase size={12} className="mr-1.5" />
                {enquiry.service}
              </span>
            </div>

            {/* Assigned */}
            <div>
              <p className="text-xs text-gray-400 uppercase tracking-wider mb-1.5">
                Assigned To
              </p>
              <div className="flex items-center gap-2.5">
                <Avatar name={enquiry.assignedTo} size={28} />
                <span className="text-sm font-medium text-[#0f172a]">
                  {enquiry.assignedTo}
                </span>
              </div>
            </div>

            {/* Value */}
            <div>
              <p className="text-xs text-gray-400 uppercase tracking-wider mb-1.5">
                Estimated Value
              </p>
              <div className="flex items-center gap-2 text-lg font-bold text-[#0f172a]">
                <DollarSign size={18} className="text-[#10b981]" />
                {formatCurrency(enquiry.value, enquiry.currency)}
              </div>
            </div>

            {/* Date */}
            <div>
              <p className="text-xs text-gray-400 uppercase tracking-wider mb-1.5">
                Date Received
              </p>
              <div className="flex items-center gap-2 text-sm text-[#0f172a]">
                <Calendar size={14} className="text-gray-400" />
                {formatDate(enquiry.date)}
              </div>
            </div>

            {/* Description */}
            <div>
              <p className="text-xs text-gray-400 uppercase tracking-wider mb-1.5">
                Description
              </p>
              <p className="text-sm text-gray-600 leading-relaxed">
                {enquiry.description}
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Middle: Status Timeline */}
        <Card className="rounded-xl border-gray-100 shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-semibold text-[#0f172a] flex items-center gap-2">
              <Clock size={18} className="text-gray-400" />
              Status Timeline
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <div className="relative pl-3">
              {/* Vertical line */}
              <div className="absolute left-[22px] top-2 bottom-2 w-0.5 bg-gray-100" />

              <div className="space-y-0">
                {STATUS_ORDER.map((status, idx) => {
                  const isActive =
                    !isRejected && idx <= currentIndex;
                  const isCurrent = enquiry.status === status;

                  return (
                    <div
                      key={status}
                      className="relative flex items-start gap-3 py-3"
                    >
                      {/* Dot */}
                      <div
                        className={`relative z-10 w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 ${
                          isActive || (isRejected && enquiry.status === status)
                            ? isCurrent
                              ? enquiry.status === 'approved'
                                ? 'bg-green-500'
                                : enquiry.status === 'rejected'
                                  ? 'bg-red-500'
                                  : 'bg-[#0ea5e9]'
                              : 'bg-[#0ea5e9]'
                            : 'bg-gray-200'
                        }`}
                      >
                        {(isActive && !isCurrent) || (isRejected && status === enquiry.status) ? (
                          <CheckCircle size={12} className="text-white" />
                        ) : isCurrent ? (
                          <div className="w-2 h-2 rounded-full bg-white" />
                        ) : (
                          <div className="w-2 h-2 rounded-full bg-gray-400" />
                        )}
                      </div>

                      {/* Label */}
                      <div className="flex-1">
                        <p
                          className={`text-sm font-medium ${
                            isActive || (isRejected && status === enquiry.status)
                              ? 'text-[#0f172a]'
                              : 'text-gray-400'
                          }`}
                        >
                          {STATUS_LABEL[status]}
                        </p>
                        {isCurrent && (
                          <p className="text-xs text-gray-400 mt-0.5">
                            Current status
                          </p>
                        )}
                      </div>
                    </div>
                  );
                })}

                {/* Rejected marker if applicable */}
                {isRejected && (
                  <div className="relative flex items-start gap-3 py-3">
                    <div className="relative z-10 w-5 h-5 rounded-full bg-red-500 flex items-center justify-center flex-shrink-0 mt-0.5">
                      <XCircle size={12} className="text-white" />
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-medium text-red-600">
                        Rejected
                      </p>
                      <p className="text-xs text-gray-400 mt-0.5">
                        Enquiry has been rejected
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Right: Actions + Notes */}
        <div className="space-y-6">
          {/* Actions Card */}
          <Card className="rounded-xl border-gray-100 shadow-sm">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold text-[#0f172a] flex items-center gap-2">
                <Star size={18} className="text-gray-400" />
                Actions
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              {renderActions()}
            </CardContent>
          </Card>

          {/* Notes Card */}
          <Card className="rounded-xl border-gray-100 shadow-sm">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold text-[#0f172a] flex items-center gap-2">
                <MessageSquare size={18} className="text-gray-400" />
                Notes
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0 space-y-4">
              {/* Existing notes */}
              {allNotes.length > 0 && (
                <div className="space-y-2.5 max-h-64 overflow-y-auto pr-1">
                  {allNotes.map((note, idx) => (
                    <div
                      key={idx}
                      className="p-3 bg-gray-50 rounded-lg text-sm text-gray-700"
                    >
                      {note}
                    </div>
                  ))}
                </div>
              )}
              {allNotes.length === 0 && (
                <p className="text-xs text-gray-400 text-center py-4">
                  No notes yet
                </p>
              )}

              {/* Add note */}
              <div className="space-y-2 pt-2 border-t border-gray-100">
                <Textarea
                  placeholder="Add a note..."
                  value={noteText}
                  onChange={(e) => setNoteText(e.target.value)}
                  className="min-h-[80px] border-gray-200 rounded-lg focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent resize-none text-sm"
                />
                <Button
                  onClick={handleAddNote}
                  disabled={!noteText.trim()}
                  className="w-full gap-2 bg-[#1e3a5f] hover:bg-[#2d5a87] text-white"
                  size="sm"
                >
                  <MessageSquare size={14} />
                  Add Note
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
