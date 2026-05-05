import { useState } from 'react';
import { getChannels } from '@/lib/api';
import type { Channel } from '@/types';
import {
  Plus, Settings, Unlink, Mail, MessageCircle, Globe, AlertTriangle,
} from 'lucide-react';

const channelIcons: Record<string, React.ReactNode> = {
  email: <Mail size={20} className="text-blue-600" />,
  whatsapp: <MessageCircle size={20} className="text-green-600" />,
  teams: <Globe size={20} className="text-purple-600" />,
  slack: <MessageCircle size={20} className="text-indigo-600" />,
  telegram: <MessageCircle size={20} className="text-sky-600" />,
};

const statusConfig = {
  connected: { dot: 'bg-green-500', text: 'text-green-700', bg: 'bg-green-50', label: 'Connected' },
  disconnected: { dot: 'bg-gray-400', text: 'text-gray-600', bg: 'bg-gray-100', label: 'Disconnected' },
  error: { dot: 'bg-red-500', text: 'text-red-700', bg: 'bg-red-50', label: 'Connection Error' },
};

function formatLastSync(iso: string) {
  const date = new Date(iso);
  const now = new Date('2026-05-05T12:00:00Z');
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins} min ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
}

export default function ChannelHub() {
  const [channels, setChannels] = useState<Channel[]>(getChannels());

  const toggleConnection = (id: string) => {
    setChannels((prev) =>
      prev.map((ch) => {
        if (ch.id !== id) return ch;
        if (ch.status === 'connected') {
          return { ...ch, status: 'disconnected' as const, messagesToday: 0 };
        }
        return {
          ...ch,
          status: 'connected' as const,
          lastSync: new Date().toISOString(),
        };
      })
    );
  };

  return (
    <div className="p-6 bg-[#f8fafc] min-h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Channel Hub</h1>
          <p className="text-sm text-gray-500 mt-1">
            Manage omni-channel integrations
          </p>
        </div>
        <button
          onClick={() => alert('Connect new channel - coming soon!')}
          className="flex items-center gap-2 px-4 py-2 bg-[#1e3a5f] text-white rounded-lg hover:bg-[#2d5a87] transition-colors text-sm font-medium"
        >
          <Plus size={16} />
          Connect Channel
        </button>
      </div>

      {/* Channel grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {channels.map((channel) => {
          const status = statusConfig[channel.status];
          return (
            <div
              key={channel.id}
              className="bg-white rounded-xl shadow-sm border border-gray-100 p-5 hover:shadow-md transition-shadow"
            >
              {/* Header */}
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-gray-50 flex items-center justify-center">
                    {channelIcons[channel.type] || <Globe size={20} className="text-gray-600" />}
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-gray-900">
                      {channel.name}
                    </h3>
                    <p className="text-xs text-gray-500">{channel.description}</p>
                  </div>
                </div>
              </div>

              {/* Divider */}
              <div className="border-t border-gray-100 my-3" />

              {/* Status row */}
              <div className="space-y-2 mb-3">
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${status.dot}`} />
                  <span className={`text-xs font-medium ${status.text}`}>
                    {status.label}
                  </span>
                  {channel.status === 'error' && (
                    <AlertTriangle size={12} className="text-red-500 ml-1" />
                  )}
                </div>
                <div className="flex items-center justify-between text-xs text-gray-500">
                  <span>Last sync: {formatLastSync(channel.lastSync)}</span>
                  <span>
                    Messages today:{' '}
                    <span className="font-medium text-gray-700">
                      {channel.status === 'disconnected' ? '—' : channel.messagesToday}
                    </span>
                  </span>
                </div>
              </div>

              {/* Divider */}
              <div className="border-t border-gray-100 my-3" />

              {/* Actions */}
              <div className="flex items-center gap-2">
                <button
                  onClick={() => alert(`Configure ${channel.name}`)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-50 hover:bg-gray-100 rounded-lg transition-colors"
                >
                  <Settings size={12} />
                  Configure
                </button>
                <button
                  onClick={() => toggleConnection(channel.id)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                    channel.status === 'connected'
                      ? 'text-red-600 bg-red-50 hover:bg-red-100'
                      : 'text-green-700 bg-green-50 hover:bg-green-100'
                  }`}
                >
                  <Unlink size={12} />
                  {channel.status === 'connected' ? 'Disconnect' : 'Connect'}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
