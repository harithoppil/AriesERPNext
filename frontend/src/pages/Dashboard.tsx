import { format } from 'date-fns';
import { useNavigate } from 'react-router-dom';
import {
  LineChart, Line, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from 'recharts';
import {
  Inbox, FolderKanban, Users, DollarSign, TrendingUp, TrendingDown,
  ArrowRight,
} from 'lucide-react';
import { getDashboardMetrics, getEnquiries, getProjects } from '@/lib/api';

const revenueData = [
  { month: 'Jan', value: 1.2 },
  { month: 'Feb', value: 1.5 },
  { month: 'Mar', value: 1.8 },
  { month: 'Apr', value: 2.1 },
  { month: 'May', value: 2.4 },
  { month: 'Jun', value: 2.8 },
];

const projectStatusData = [
  { name: 'Active', value: 4, color: '#1e3a5f' },
  { name: 'Planning', value: 3, color: '#0ea5e9' },
  { name: 'Completed', value: 5, color: '#10b981' },
  { name: 'On Hold', value: 1, color: '#f59e0b' },
];

const statusBadgeClasses: Record<string, string> = {
  approved: 'bg-green-100 text-green-700',
  proposal: 'bg-blue-100 text-blue-700',
  negotiation: 'bg-amber-100 text-amber-700',
  qualified: 'bg-purple-100 text-purple-700',
  new: 'bg-gray-100 text-gray-700',
};

const statusLabels: Record<string, string> = {
  approved: 'Approved',
  proposal: 'Proposal',
  negotiation: 'Negotiation',
  qualified: 'Qualified',
  new: 'New',
};

const kpiIcons: Record<string, React.ComponentType<{ size?: number; className?: string }>> = {
  Inbox, FolderKanban, Users, DollarSign,
  FileText: FolderKanban, Package: Inbox, Wrench: Users, AlertTriangle: DollarSign,
};

export default function Dashboard() {
  const navigate = useNavigate();
  const metrics = getDashboardMetrics();
  const enquiries = getEnquiries().slice(0, 5);
  const activeProjects = getProjects().filter(p => p.status === 'active').slice(0, 4);
  const today = format(new Date(), 'EEEE, d MMMM yyyy');

  return (
    <div className="space-y-6">
      {/* Header bar */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900">Dashboard</h2>
          <p className="text-sm text-gray-500 mt-0.5">{today}</p>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {metrics.slice(0, 4).map((metric) => {
          const Icon = kpiIcons[metric.icon] || DollarSign;
          const isPositive = metric.changeType === 'increase';
          return (
            <div
              key={metric.label}
              className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 hover:shadow-md transition-shadow"
            >
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <p className="text-sm text-gray-500">{metric.label}</p>
                  <p className="text-3xl font-bold text-gray-900 mt-1">
                    {metric.prefix}{typeof metric.value === 'number' ? metric.value.toLocaleString() : metric.value}{metric.suffix}
                  </p>
                  <div className={`flex items-center gap-1 mt-2 text-xs font-medium ${isPositive ? 'text-green-600' : 'text-red-600'}`}>
                    {isPositive ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                    <span>{isPositive ? '+' : ''}{metric.change}%</span>
                  </div>
                </div>
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${
                  metric.label.includes('Revenue') ? 'bg-emerald-100' :
                  metric.label.includes('Offshore') ? 'bg-green-100' :
                  metric.label.includes('Projects') ? 'bg-indigo-100' : 'bg-blue-100'
                }`}>
                  <Icon size={24} className={
                    metric.label.includes('Revenue') ? 'text-emerald-600' :
                    metric.label.includes('Offshore') ? 'text-green-600' :
                    metric.label.includes('Projects') ? 'text-indigo-600' : 'text-blue-600'
                  } />
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Revenue Trend */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
          <h3 className="text-base font-semibold text-gray-900 mb-4">Revenue Trend</h3>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={revenueData}>
              <defs>
                <linearGradient id="revenueGradient" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="#0ea5e9" />
                  <stop offset="100%" stopColor="#1e3a5f" />
                </linearGradient>
                <linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#0ea5e9" stopOpacity={0.15} />
                  <stop offset="100%" stopColor="#0ea5e9" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="month" tick={{ fontSize: 12, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
              <YAxis
                tick={{ fontSize: 12, fill: '#94a3b8' }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v) => `AED ${v}M`}
                domain={[0, 3.2]}
              />
              <Tooltip
                formatter={(value: number) => [`AED ${value}M`, 'Revenue']}
                contentStyle={{ borderRadius: '12px', border: '1px solid #e2e8f0', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
              />
              <Area type="monotone" dataKey="value" stroke="none" fill="url(#areaGradient)" />
              <Line
                type="monotone"
                dataKey="value"
                stroke="url(#revenueGradient)"
                strokeWidth={3}
                dot={{ r: 4, fill: '#0ea5e9', strokeWidth: 2, stroke: '#fff' }}
                activeDot={{ r: 6, fill: '#1e3a5f', strokeWidth: 2, stroke: '#fff' }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Project Status */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
          <h3 className="text-base font-semibold text-gray-900 mb-4">Project Status</h3>
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie
                data={projectStatusData}
                cx="50%"
                cy="45%"
                innerRadius={60}
                outerRadius={100}
                paddingAngle={3}
                dataKey="value"
                stroke="none"
              >
                {projectStatusData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip
                formatter={(value: number, name: string) => [`${value}`, name]}
                contentStyle={{ borderRadius: '12px', border: '1px solid #e2e8f0' }}
              />
              <Legend
                verticalAlign="bottom"
                iconType="circle"
                iconSize={10}
                formatter={(value: string) => <span className="text-sm text-gray-700 ml-1">{value}</span>}
              />
              {/* Center label */}
              <text x="50%" y="42%" textAnchor="middle" dominantBaseline="middle" className="text-2xl font-bold fill-gray-900">
                8
              </text>
              <text x="50%" y="52%" textAnchor="middle" dominantBaseline="middle" className="text-xs fill-gray-400">
                Total
              </text>
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Bottom Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Recent Enquiries */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-base font-semibold text-gray-900">Recent Enquiries</h3>
            <span className="text-xs text-gray-400">{getEnquiries().length} total</span>
          </div>
          <div className="space-y-3">
            {enquiries.map((enq) => (
              <div
                key={enq.id}
                className="flex items-center gap-3 p-3 hover:bg-gray-50 rounded-xl transition-colors cursor-pointer"
                onClick={() => navigate(`/enquiries/${enq.id}`)}
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">{enq.service} - {enq.client}</p>
                  <p className="text-xs text-gray-500 mt-0.5">{enq.contactName}</p>
                </div>
                <div className="text-right flex-shrink-0">
                  <p className="text-sm font-semibold text-gray-900">
                    {enq.currency} {(enq.value / 1000).toFixed(0)}K
                  </p>
                  <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium mt-1 ${statusBadgeClasses[enq.status]}`}>
                    {statusLabels[enq.status]}
                  </span>
                </div>
              </div>
            ))}
          </div>
          <button
            onClick={() => navigate('/enquiries')}
            className="flex items-center gap-1 mt-4 text-sm text-[#0ea5e9] hover:underline font-medium"
          >
            View All <ArrowRight size={14} />
          </button>
        </div>

        {/* Active Projects */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
          <h3 className="text-base font-semibold text-gray-900 mb-4">Active Projects</h3>
          <div className="space-y-4">
            {activeProjects.map((project) => (
              <div key={project.id} className="p-3 border border-gray-100 rounded-xl">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm font-medium text-gray-900">{project.name}</p>
                  <span className="text-xs font-semibold text-gray-700">{project.progress}%</span>
                </div>
                <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${project.progress}%`,
                      backgroundColor: project.progress >= 75 ? '#10b981' : project.progress >= 40 ? '#0ea5e9' : '#f59e0b',
                    }}
                  />
                </div>
                <div className="flex items-center justify-between mt-2 text-xs text-gray-500">
                  <span>AED {(project.budgetSpent / 1000000).toFixed(1)}M / AED {(project.budgetTotal / 1000000).toFixed(1)}M</span>
                  <span>{project.location}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
