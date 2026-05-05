import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { getDynamicUIById } from '@/lib/api';
import {
  ArrowLeft, Sparkles, Download, Plus,
} from 'lucide-react';

// ─── Dashboard Sub-Components ───

function KpiCard({ label, value, change, prefix, suffix }: {
  label: string; value: string | number; change: number;
  prefix?: string; suffix?: string;
}) {
  const positive = change >= 0;
  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-bold text-gray-900">
          {prefix}{value}{suffix}
        </span>
        <span className={`text-xs font-medium ${positive ? 'text-green-600' : 'text-red-600'}`}>
          {positive ? '+' : ''}{change}%
        </span>
      </div>
    </div>
  );
}

function SimpleBarChart({ data }: { data: { label: string; value: number; color: string }[] }) {
  const max = Math.max(...data.map((d) => d.value));
  return (
    <div className="space-y-3">
      {data.map((bar) => (
        <div key={bar.label} className="flex items-center gap-3">
          <span className="text-xs text-gray-500 w-20 text-right flex-shrink-0">{bar.label}</span>
          <div className="flex-1 h-6 bg-gray-100 rounded-md overflow-hidden">
            <div
              className="h-full rounded-md transition-all duration-500"
              style={{
                width: `${(bar.value / max) * 100}%`,
                backgroundColor: bar.color,
              }}
            />
          </div>
          <span className="text-xs font-medium text-gray-700 w-8">{bar.value}</span>
        </div>
      ))}
    </div>
  );
}

function DataTable({ columns, rows }: { columns: string[]; rows: Record<string, string | number>[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-50 text-gray-700 font-semibold text-xs uppercase tracking-wider">
            {columns.map((col) => (
              <th key={col} className="text-left px-3 py-2 border-b border-gray-100">{col}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {rows.map((row, i) => (
            <tr key={i} className="hover:bg-gray-50 transition-colors">
              {columns.map((col) => (
                <td key={col} className="px-3 py-2 text-gray-700">{row[col]}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Renderers ───

function DashboardRenderer({ title: _title, description }: { title: string; description: string }) {
  const kpiData = [
    { label: 'Total Enquiries', value: 24, change: 12, prefix: '', suffix: '' },
    { label: 'Conversion Rate', value: 18, change: 5, prefix: '', suffix: '%' },
    { label: 'Avg Deal Size', value: 320, change: -3, prefix: 'AED ', suffix: 'K' },
    { label: 'Revenue', value: 4.2, change: 8, prefix: 'AED ', suffix: 'M' },
  ];

  const chartData = [
    { label: 'New', value: 8, color: '#94a3b8' },
    { label: 'Qualified', value: 6, color: '#0ea5e9' },
    { label: 'Proposal', value: 5, color: '#38bdf8' },
    { label: 'Negotiation', value: 3, color: '#1e3a5f' },
    { label: 'Approved', value: 2, color: '#10b981' },
  ];

  const tableColumns = ['Client', 'Service', 'Value', 'Status'];
  const tableRows = [
    { Client: 'ADNOC', Service: 'ROV Inspection', Value: 'AED 450K', Status: 'Approved' },
    { Client: 'ZADCO', Service: 'Crane Rental', Value: 'AED 280K', Status: 'Proposal' },
    { Client: 'Saudi Aramco', Service: 'Diving Support', Value: 'SAR 720K', Status: 'Negotiation' },
    { Client: 'Qatar Petroleum', Service: 'NDT Testing', Value: 'QAR 195K', Status: 'Qualified' },
    { Client: 'Borouge', Service: 'Cable Laying', Value: 'AED 890K', Status: 'New' },
  ];

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-500">{description}</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {kpiData.map((kpi) => (
          <KpiCard key={kpi.label} {...kpi} />
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
          <h3 className="text-sm font-semibold text-gray-900 mb-4">Enquiry Funnel</h3>
          <SimpleBarChart data={chartData} />
        </div>
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
          <h3 className="text-sm font-semibold text-gray-900 mb-4">Recent Enquiries</h3>
          <DataTable columns={tableColumns} rows={tableRows} />
        </div>
      </div>
    </div>
  );
}

function FormRenderer({ title, description, config }: {
  title: string; description: string; config: Record<string, unknown>;
}) {
  const fields = (config.fields as string[]) || ['client', 'contact', 'service', 'value', 'description'];
  const fieldConfig: Record<string, { label: string; type: string; placeholder: string; options?: string[] }> = {
    client: { label: 'Client Name', type: 'text', placeholder: 'Enter client name' },
    contact: { label: 'Contact Person', type: 'text', placeholder: 'Enter contact name' },
    service: { label: 'Service Type', type: 'select', placeholder: 'Select service', options: ['ROV Inspection', 'Crane Rental', 'Diving Support', 'NDT Testing', 'Survey'] },
    value: { label: 'Estimated Value', type: 'number', placeholder: 'Enter value' },
    description: { label: 'Description', type: 'textarea', placeholder: 'Enter project description' },
    email: { label: 'Email', type: 'email', placeholder: 'Enter email address' },
    phone: { label: 'Phone', type: 'tel', placeholder: 'Enter phone number' },
    location: { label: 'Location', type: 'text', placeholder: 'Enter location' },
  };

  const [formData, setFormData] = useState<Record<string, string>>({});

  const handleChange = (field: string, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    alert('Form submitted! (demo)');
  };

  return (
    <div className="max-w-2xl mx-auto">
      <h2 className="text-lg font-semibold text-gray-900 mb-1">{title}</h2>
      <p className="text-sm text-gray-500 mb-6">{description}</p>
      <form onSubmit={handleSubmit} className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 space-y-4">
        {(config.layout === 'two-column') ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {fields.map((field) => {
              const fc = fieldConfig[field] || { label: field, type: 'text', placeholder: field };
              return (
                <div key={field} className={field === 'description' ? 'sm:col-span-2' : ''}>
                  <label className="block text-sm font-medium text-gray-700 mb-1">{fc.label}</label>
                  {fc.type === 'select' ? (
                    <select
                      value={formData[field] || ''}
                      onChange={(e) => handleChange(field, e.target.value)}
                      className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none bg-white"
                    >
                      <option value="">{fc.placeholder}</option>
                      {fc.options?.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
                    </select>
                  ) : fc.type === 'textarea' ? (
                    <textarea
                      value={formData[field] || ''}
                      onChange={(e) => handleChange(field, e.target.value)}
                      placeholder={fc.placeholder}
                      rows={3}
                      className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none resize-none"
                    />
                  ) : (
                    <input
                      type={fc.type}
                      value={formData[field] || ''}
                      onChange={(e) => handleChange(field, e.target.value)}
                      placeholder={fc.placeholder}
                      className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none"
                    />
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          fields.map((field) => {
            const fc = fieldConfig[field] || { label: field, type: 'text', placeholder: field };
            return (
              <div key={field}>
                <label className="block text-sm font-medium text-gray-700 mb-1">{fc.label}</label>
                {fc.type === 'select' ? (
                  <select
                    value={formData[field] || ''}
                    onChange={(e) => handleChange(field, e.target.value)}
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none bg-white"
                  >
                    <option value="">{fc.placeholder}</option>
                    {fc.options?.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
                  </select>
                ) : fc.type === 'textarea' ? (
                  <textarea
                    value={formData[field] || ''}
                    onChange={(e) => handleChange(field, e.target.value)}
                    placeholder={fc.placeholder}
                    rows={3}
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none resize-none"
                  />
                ) : (
                  <input
                    type={fc.type}
                    value={formData[field] || ''}
                    onChange={(e) => handleChange(field, e.target.value)}
                    placeholder={fc.placeholder}
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none"
                  />
                )}
              </div>
            );
          })
        )}
        <div className="pt-2">
          <button
            type="submit"
            className="px-6 py-2 bg-[#1e3a5f] text-white rounded-lg hover:bg-[#2d5a87] transition-colors text-sm font-medium"
          >
            Submit
          </button>
        </div>
      </form>
    </div>
  );
}

function KanbanRenderer({ title, description, config }: {
  title: string; description: string; config: Record<string, unknown>;
}) {
  const swimlanes = (config.swimlanes as string[]) || ['Backlog', 'In Progress', 'Review', 'Done'];
  const groupBy = config.groupBy as string;

  const mockCards: Record<string, { id: string; title: string; assignee: string; tag: string }[]> = {
    Backlog: [
      { id: 'k-1', title: 'Prepare ROV inspection report', assignee: 'Omar', tag: 'ROV' },
      { id: 'k-2', title: 'Update client contact info', assignee: 'Sarah', tag: 'Admin' },
      { id: 'k-3', title: 'Schedule crane maintenance', assignee: 'James', tag: 'Crane' },
    ],
    'In Progress': [
      { id: 'k-4', title: 'ADNOC pipeline survey', assignee: 'Omar', tag: 'Survey' },
      { id: 'k-5', title: 'Quote for ZADCO project', assignee: 'Sarah', tag: 'Sales' },
    ],
    Review: [
      { id: 'k-6', title: 'NDT inspection results', assignee: 'Lisa', tag: 'NDT' },
    ],
    Done: [
      { id: 'k-7', title: 'BOSIET renewal - Priya', assignee: 'Aisha', tag: 'HR' },
      { id: 'k-8', title: 'Equipment calibration Q2', assignee: 'Tom', tag: 'Maint' },
    ],
  };

  const tagColors: Record<string, string> = {
    ROV: 'bg-blue-100 text-blue-700',
    Admin: 'bg-gray-100 text-gray-700',
    Crane: 'bg-orange-100 text-orange-700',
    Survey: 'bg-purple-100 text-purple-700',
    Sales: 'bg-green-100 text-green-700',
    NDT: 'bg-amber-100 text-amber-700',
    HR: 'bg-pink-100 text-pink-700',
    Maint: 'bg-teal-100 text-teal-700',
  };

  return (
    <div>
      <h2 className="text-lg font-semibold text-gray-900 mb-1">{title}</h2>
      <p className="text-sm text-gray-500 mb-4">{description}</p>
      {groupBy && (
        <p className="text-xs text-gray-400 mb-4">Grouped by: {groupBy}</p>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {swimlanes.map((lane) => (
          <div key={lane} className="bg-gray-100 rounded-xl p-3">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-gray-700">{lane}</h3>
              <span className="text-xs text-gray-500 bg-white px-2 py-0.5 rounded-full">
                {(mockCards[lane] || []).length}
              </span>
            </div>
            <div className="space-y-2">
              {(mockCards[lane] || []).map((card) => (
                <div
                  key={card.id}
                  className="bg-white rounded-lg shadow-sm border border-gray-200 p-3 cursor-grab hover:shadow-md transition-shadow"
                >
                  <p className="text-sm font-medium text-gray-900 mb-2">{card.title}</p>
                  <div className="flex items-center justify-between">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${tagColors[card.tag] || 'bg-gray-100'}`}>
                      {card.tag}
                    </span>
                    <div className="w-5 h-5 rounded-full bg-[#1e3a5f] text-white text-[9px] flex items-center justify-center font-medium">
                      {card.assignee.charAt(0)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <button className="w-full mt-2 py-1.5 text-xs text-gray-500 hover:text-gray-700 hover:bg-white/50 rounded-lg transition-colors flex items-center justify-center gap-1">
              <Plus size={12} />
              Add card
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

function ReportRenderer({ title, description, config }: {
  title: string; description: string; config: Record<string, unknown>;
}) {
  const period = config.period as string;
  const charts = config.charts as string[];

  const summaryData = [
    { label: 'Total Revenue', value: 'AED 4.2M', change: '+8%' },
    { label: 'Operating Costs', value: 'AED 2.8M', change: '-3%' },
    { label: 'Net Profit', value: 'AED 1.4M', change: '+15%' },
    { label: 'Active Projects', value: '8', change: '+2' },
  ];

  const chartData = [
    { label: 'Jan', value: 320, color: '#0ea5e9' },
    { label: 'Feb', value: 410, color: '#0ea5e9' },
    { label: 'Mar', value: 380, color: '#0ea5e9' },
    { label: 'Apr', value: 520, color: '#1e3a5f' },
    { label: 'May', value: 490, color: '#0ea5e9' },
  ];

  const detailColumns = ['Item', 'Category', 'Amount', 'Trend'];
  const detailRows = [
    { Item: 'ROV Services', Category: 'Operations', Amount: 'AED 1.8M', Trend: '↑ 12%' },
    { Item: 'Crane Rental', Category: 'Equipment', Amount: 'AED 980K', Trend: '↑ 5%' },
    { Item: 'NDT Inspection', Category: 'Inspection', Amount: 'AED 720K', Trend: '↓ 2%' },
    { Item: 'Diving Support', Category: 'Subsea', Amount: 'AED 450K', Trend: '↑ 8%' },
    { Item: 'Survey', Category: 'Survey', Amount: 'AED 250K', Trend: '→ 0%' },
  ];

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-gray-900 mb-1">{title}</h2>
        <p className="text-sm text-gray-500">{description}</p>
        <p className="text-xs text-gray-400 mt-1">Period: {period} | Charts: {charts?.join(', ')}</p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {summaryData.map((item) => (
          <div key={item.label} className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
            <p className="text-xs text-gray-500 mb-1">{item.label}</p>
            <div className="flex items-baseline gap-2">
              <span className="text-xl font-bold text-gray-900">{item.value}</span>
              <span className={`text-xs font-medium ${item.change.startsWith('+') ? 'text-green-600' : item.change.startsWith('-') ? 'text-red-600' : 'text-gray-500'}`}>
                {item.change}
              </span>
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Chart */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
          <h3 className="text-sm font-semibold text-gray-900 mb-4">Monthly Revenue (AED K)</h3>
          <SimpleBarChart data={chartData} />
        </div>
        {/* Detail table */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
          <h3 className="text-sm font-semibold text-gray-900 mb-4">Revenue Breakdown</h3>
          <DataTable columns={detailColumns} rows={detailRows} />
        </div>
      </div>
    </div>
  );
}

// ─── Main Component ───

export default function DynamicRenderer() {
  const { id } = useParams<{ id: string }>();
  const ui = id ? getDynamicUIById(id) : null;

  const handleRegenerate = () => {
    alert('Regenerating UI...');
  };

  const handleExport = () => {
    alert('Exporting... (demo)');
  };

  if (!ui) {
    return (
      <div className="p-6 bg-[#f8fafc] min-h-full">
        <div className="text-center py-12 text-gray-400">
          <Sparkles size={40} className="mx-auto mb-3 opacity-50" />
          <p className="text-sm">Dynamic UI not found</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 bg-[#f8fafc] min-h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <button
            onClick={() => window.history.back()}
            className="p-2 hover:bg-gray-200 rounded-lg transition-colors"
          >
            <ArrowLeft size={18} className="text-gray-600" />
          </button>
          <div>
            <h1 className="text-xl font-semibold text-gray-900 flex items-center gap-2">
              <Sparkles size={20} className="text-[#0ea5e9]" />
              AI-Generated Interface
            </h1>
            <p className="text-xs text-gray-500">Type: {ui.type}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleRegenerate}
            className="flex items-center gap-2 px-4 py-2 bg-[#1e3a5f] text-white rounded-lg hover:bg-[#2d5a87] transition-colors text-sm font-medium"
          >
            <Sparkles size={14} />
            Regenerate
          </button>
          <button
            onClick={handleExport}
            className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors text-sm font-medium"
          >
            <Download size={14} />
            Export
          </button>
        </div>
      </div>

      {/* Content based on type */}
      {ui.type === 'dashboard' && (
        <DashboardRenderer title={ui.title} description={ui.description} />
      )}
      {ui.type === 'form' && (
        <FormRenderer title={ui.title} description={ui.description} config={ui.config} />
      )}
      {ui.type === 'kanban' && (
        <KanbanRenderer title={ui.title} description={ui.description} config={ui.config} />
      )}
      {ui.type === 'report' && (
        <ReportRenderer title={ui.title} description={ui.description} config={ui.config} />
      )}
    </div>
  );
}
