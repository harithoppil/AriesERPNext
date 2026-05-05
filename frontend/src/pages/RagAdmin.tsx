import { useState } from 'react';
import { getRagDocuments } from '@/lib/api';
import type { RagDocument } from '@/types';
import {
  FileText, CheckCircle, Clock, XCircle, RefreshCw, Trash2, Database,
} from 'lucide-react';

const typeColors: Record<string, string> = {
  pdf: 'bg-red-100 text-red-700',
  doc: 'bg-blue-100 text-blue-700',
  txt: 'bg-gray-100 text-gray-700',
};

const statusColors: Record<string, string> = {
  indexed: 'bg-green-100 text-green-700',
  pending: 'bg-amber-100 text-amber-700',
  failed: 'bg-red-100 text-red-700',
};

export default function RagAdmin() {
  const [documents, setDocuments] = useState<RagDocument[]>(getRagDocuments());
  const [reindexingIds, setReindexingIds] = useState<Set<string>>(new Set());

  const totalDocs = documents.length;
  const indexedCount = documents.filter((d) => d.status === 'indexed').length;
  const pendingCount = documents.filter((d) => d.status === 'pending').length;
  const failedCount = documents.filter((d) => d.status === 'failed').length;

  const handleReindex = (id: string) => {
    setReindexingIds((prev) => new Set(prev).add(id));
    // Simulate reindexing
    setTimeout(() => {
      setDocuments((prev) =>
        prev.map((d) =>
          d.id === id
            ? { ...d, status: 'indexed' as const, indexedAt: new Date().toISOString() }
            : d
        )
      );
      setReindexingIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }, 2000);
  };

  const handleDelete = (id: string) => {
    if (confirm('Delete this document?')) {
      setDocuments(documents.filter((d) => d.id !== id));
    }
  };

  const stats = [
    {
      label: 'Total Documents',
      value: totalDocs,
      icon: FileText,
      color: 'text-blue-600',
      bg: 'bg-blue-50',
    },
    {
      label: 'Indexed',
      value: indexedCount,
      icon: CheckCircle,
      color: 'text-green-600',
      bg: 'bg-green-50',
    },
    {
      label: 'Pending',
      value: pendingCount,
      icon: Clock,
      color: 'text-amber-600',
      bg: 'bg-amber-50',
    },
    {
      label: 'Failed',
      value: failedCount,
      icon: XCircle,
      color: 'text-red-600',
      bg: 'bg-red-50',
    },
  ];

  return (
    <div className="p-6 bg-[#f8fafc] min-h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">RAG Index Admin</h1>
          <p className="text-sm text-gray-500 mt-1">
            Knowledge base indexing for AI RAG system
          </p>
        </div>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {stats.map((stat) => {
          const Icon = stat.icon;
          return (
            <div
              key={stat.label}
              className="bg-white rounded-xl shadow-sm border border-gray-100 p-4"
            >
              <div className="flex items-center gap-3">
                <div className={`w-10 h-10 rounded-lg ${stat.bg} flex items-center justify-center`}>
                  <Icon size={20} className={stat.color} />
                </div>
                <div>
                  <p className="text-2xl font-bold text-gray-900">{stat.value}</p>
                  <p className="text-xs text-gray-500">{stat.label}</p>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Documents table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="flex items-center gap-2 px-5 py-4 border-b border-gray-100">
          <Database size={16} className="text-[#1e3a5f]" />
          <h2 className="text-sm font-semibold text-gray-900">Documents</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-gray-700 font-semibold text-xs uppercase tracking-wider">
                <th className="text-left px-5 py-3">Name</th>
                <th className="text-left px-5 py-3">Type</th>
                <th className="text-left px-5 py-3">Size</th>
                <th className="text-left px-5 py-3">Status</th>
                <th className="text-left px-5 py-3">Indexed At</th>
                <th className="text-left px-5 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {documents.map((doc) => {
                const isReindexing = reindexingIds.has(doc.id);
                return (
                  <tr
                    key={doc.id}
                    className="hover:bg-gray-50 transition-colors"
                  >
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        <FileText size={16} className="text-gray-400" />
                        <span className="font-medium text-gray-900">
                          {doc.name}
                        </span>
                      </div>
                    </td>
                    <td className="px-5 py-3">
                      <span
                        className={`text-xs font-medium px-2.5 py-1 rounded-full ${
                          typeColors[doc.type] || 'bg-gray-100 text-gray-700'
                        }`}
                      >
                        {doc.type.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-gray-600">{doc.size}</td>
                    <td className="px-5 py-3">
                      <span
                        className={`text-xs font-medium px-2.5 py-1 rounded-full ${
                          statusColors[doc.status] || 'bg-gray-100 text-gray-700'
                        }`}
                      >
                        {doc.status.charAt(0).toUpperCase() + doc.status.slice(1)}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-gray-500">
                      {doc.indexedAt
                        ? new Date(doc.indexedAt).toLocaleDateString()
                        : '—'}
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => handleReindex(doc.id)}
                          disabled={isReindexing}
                          className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-[#0ea5e9] bg-blue-50 hover:bg-blue-100 rounded-lg transition-colors disabled:opacity-50"
                        >
                          <RefreshCw
                            size={12}
                            className={isReindexing ? 'animate-spin' : ''}
                          />
                          {isReindexing ? 'Reindexing...' : 'Reindex'}
                        </button>
                        <button
                          onClick={() => handleDelete(doc.id)}
                          className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                          title="Delete"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {documents.length === 0 && (
                <tr>
                  <td colSpan={6} className="text-center py-8 text-gray-400">
                    <Database size={24} className="mx-auto mb-2 opacity-50" />
                    <p className="text-sm">No documents found</p>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
