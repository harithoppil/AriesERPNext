import { useState } from 'react';
import {
  FileImage, Download, Check, Phone, Mail, Globe,
} from 'lucide-react';

const templates = ['Letter', 'Memo', 'Quotation', 'Report'];

const companyInfo = {
  name: 'Aries Marine Consultancy LLC',
  address: 'Office 402, Al Sila Tower\nAl Maryah Island, Abu Dhabi, UAE',
  phone: '+971 2 555 0123',
  email: 'info@ariesmarine.ae',
  website: 'www.ariesmarine.ae',
};

export default function LetterheadGenerator() {
  const [template, setTemplate] = useState('Letter');
  const [date, setDate] = useState(new Date().toISOString().split('T')[0]);
  const [ref, setRef] = useState('AMC-2026-001');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [sigName, setSigName] = useState('');
  const [sigTitle, setSigTitle] = useState('');
  const [includeSig, setIncludeSig] = useState(true);
  const [showToast, setShowToast] = useState(false);

  const handleExport = () => {
    setShowToast(true);
    setTimeout(() => setShowToast(false), 3000);
  };

  const formatDate = (dateStr: string) => {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-GB', {
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    });
  };

  return (
    <div className="p-6 bg-[#f8fafc] min-h-full relative">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900 flex items-center gap-2">
            <FileImage size={20} className="text-[#1e3a5f]" />
            Letterhead Generator
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Create branded documents with Aries Marine letterhead
          </p>
        </div>
        <button
          onClick={handleExport}
          className="flex items-center gap-2 px-4 py-2 bg-[#1e3a5f] text-white rounded-lg hover:bg-[#2d5a87] transition-colors text-sm font-medium"
        >
          <Download size={14} />
          Export PDF
        </button>
      </div>

      {/* 2-column layout */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: Settings */}
        <div className="space-y-4">
          {/* Template selector */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Template
            </label>
            <select
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none bg-white"
            >
              {templates.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>

          {/* Company info (read-only) */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Company Details</h3>
            <div className="flex items-start gap-3 mb-2">
              <img
                src="/aries-logo-transparent.png"
                alt="Aries Marine"
                className="w-12 h-12 object-contain"
              />
              <div>
                <p className="text-sm font-semibold text-[#1e3a5f]">{companyInfo.name}</p>
                <p className="text-xs text-gray-500 whitespace-pre-line">{companyInfo.address}</p>
              </div>
            </div>
            <div className="mt-3 space-y-1">
              <p className="text-xs text-gray-500 flex items-center gap-1.5">
                <Phone size={10} className="text-gray-400" />
                {companyInfo.phone}
              </p>
              <p className="text-xs text-gray-500 flex items-center gap-1.5">
                <Mail size={10} className="text-gray-400" />
                {companyInfo.email}
              </p>
              <p className="text-xs text-gray-500 flex items-center gap-1.5">
                <Globe size={10} className="text-gray-400" />
                {companyInfo.website}
              </p>
            </div>
          </div>

          {/* Document details */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Document Details</h3>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Date</label>
                <input
                  type="date"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Reference</label>
                <input
                  type="text"
                  value={ref}
                  onChange={(e) => setRef(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Subject</label>
                <input
                  type="text"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  placeholder="Enter subject"
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Body</label>
                <textarea
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  placeholder="Enter document body..."
                  rows={6}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none resize-none"
                />
              </div>
            </div>
          </div>

          {/* Signature */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Signature Block</h3>
            <div className="space-y-3">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={includeSig}
                  onChange={(e) => setIncludeSig(e.target.checked)}
                  className="rounded border-gray-300 text-[#1e3a5f] focus:ring-[#0ea5e9]"
                />
                <span className="text-sm text-gray-700">Include signature</span>
              </label>
              {includeSig && (
                <>
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Name</label>
                    <input
                      type="text"
                      value={sigName}
                      onChange={(e) => setSigName(e.target.value)}
                      placeholder="Full name"
                      className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Title</label>
                    <input
                      type="text"
                      value={sigTitle}
                      onChange={(e) => setSigTitle(e.target.value)}
                      placeholder="Job title"
                      className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none"
                    />
                  </div>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Right: A4 Preview */}
        <div className="flex flex-col items-center">
          <h3 className="text-sm font-medium text-gray-500 mb-3">A4 Preview</h3>
          <div className="w-full max-w-[210mm] aspect-[210/297] bg-white shadow-lg border border-gray-200 p-8 overflow-hidden">
            {/* Letterhead */}
            <div className="flex items-start justify-between border-b-2 border-[#1e3a5f] pb-4 mb-6">
              <div className="flex items-center gap-3">
                <img
                  src="/aries-logo-transparent.png"
                  alt="Aries Marine"
                  className="w-14 h-14 object-contain"
                />
                <div>
                  <p className="text-base font-bold text-[#1e3a5f]">{companyInfo.name}</p>
                  <p className="text-[10px] text-gray-500 whitespace-pre-line leading-tight">
                    {companyInfo.address}
                  </p>
                </div>
              </div>
              <div className="text-right text-[9px] text-gray-500 space-y-0.5">
                <p className="flex items-center justify-end gap-1">
                  <Phone size={8} />
                  {companyInfo.phone}
                </p>
                <p className="flex items-center justify-end gap-1">
                  <Mail size={8} />
                  {companyInfo.email}
                </p>
                <p className="flex items-center justify-end gap-1">
                  <Globe size={8} />
                  {companyInfo.website}
                </p>
              </div>
            </div>

            {/* Template label */}
            <div className="text-right mb-4">
              <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">
                {template}
              </span>
            </div>

            {/* Date & Ref */}
            <div className="mb-6 text-sm">
              <p className="text-gray-700">
                <span className="font-medium">Date:</span>{' '}
                {formatDate(date) || '—'}
              </p>
              <p className="text-gray-700 mt-1">
                <span className="font-medium">Ref:</span>{' '}
                {ref || '—'}
              </p>
            </div>

            {/* Subject */}
            {subject && (
              <div className="mb-6">
                <h2 className="text-lg font-bold text-[#1e3a5f] mb-1">{subject}</h2>
                <div className="w-16 h-0.5 bg-[#0ea5e9]" />
              </div>
            )}

            {/* Body */}
            <div className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap min-h-[200px]">
              {body || (
                <span className="text-gray-300 italic">
                  Document body will appear here...
                </span>
              )}
            </div>

            {/* Signature */}
            {includeSig && (sigName || sigTitle) && (
              <div className="mt-10 pt-4 border-t border-gray-200">
                <p className="text-sm font-semibold text-gray-900">{sigName}</p>
                <p className="text-xs text-gray-500">{sigTitle}</p>
              </div>
            )}

            {/* Footer */}
            <div className="mt-8 pt-3 border-t border-gray-100 text-center">
              <p className="text-[8px] text-gray-400">
                {companyInfo.name} · Abu Dhabi, UAE · {companyInfo.website}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Toast */}
      {showToast && (
        <div className="fixed bottom-6 right-6 bg-green-600 text-white px-4 py-3 rounded-xl shadow-lg flex items-center gap-2 text-sm z-50 animate-in slide-in-from-right-4 fade-in duration-300">
          <Check size={16} />
          Document exported successfully!
        </div>
      )}
    </div>
  );
}
