import { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useStore } from '@/store/useStore';
import { getNotifications } from '@/lib/api';
import {
  Menu, Search, Bell, MessageSquare, ChevronDown,
} from 'lucide-react';

const routeTitles: Record<string, string> = {
  '/dashboard': 'Dashboard',
  '/enquiries': 'Enquiries',
  '/personnel': 'Personnel',
  '/assets': 'Assets',
  '/projects': 'Projects',
  '/stock': 'Stock',
  '/purchase-orders': 'Purchase Orders',
  '/invoices': 'Invoices',
  '/payments': 'Payments',
  '/suppliers': 'Suppliers',
  '/wiki': 'Wiki',
  '/settings/workflows': 'Workflows',
  '/settings/personas': 'Personas',
  '/settings/channels': 'Channels',
  '/settings/rag': 'RAG Index',
  '/dynamic/ui-1': 'Dynamic UI',
  '/tools/letterhead': 'Letterhead Generator',
};

export default function Header() {
  const location = useLocation();
  const { toggleMobile, toggleChat, notifications: storeNotifications } = useStore();
  const [notifOpen, setNotifOpen] = useState(false);
  const [userOpen, setUserOpen] = useState(false);

  const pageTitle = routeTitles[location.pathname] || 'Aries Marine ERP';
  const notifications = storeNotifications.length > 0 ? storeNotifications : getNotifications();
  const unreadCount = notifications.filter(n => !n.read).length;

  return (
    <header className="h-16 bg-white shadow-sm fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-4">
      {/* Left: hamburger + title */}
      <div className="flex items-center gap-3">
        <button
          onClick={toggleMobile}
          className="lg:hidden p-2 hover:bg-gray-100 rounded-lg"
        >
          <Menu size={20} />
        </button>
        <h1 className="text-lg font-semibold text-gray-900">{pageTitle}</h1>
      </div>

      {/* Center: search */}
      <div className="hidden md:flex items-center bg-gray-100 rounded-lg px-3 py-2 w-96">
        <Search size={18} className="text-gray-400 mr-2" />
        <input
          type="text"
          placeholder="Search..."
          className="bg-transparent border-none outline-none text-sm w-full text-gray-700 placeholder-gray-400"
        />
      </div>

      {/* Right: actions */}
      <div className="flex items-center gap-2">
        {/* Notifications */}
        <div className="relative">
          <button
            onClick={() => setNotifOpen(!notifOpen)}
            className="relative p-2 hover:bg-gray-100 rounded-lg"
          >
            <Bell size={20} className="text-gray-600" />
            {unreadCount > 0 && (
              <span className="absolute top-1 right-1 w-4 h-4 bg-red-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center">
                {unreadCount}
              </span>
            )}
          </button>

          {notifOpen && (
            <>
              <div className="fixed inset-0" onClick={() => setNotifOpen(false)} />
              <div className="absolute right-0 top-12 w-80 bg-white rounded-xl shadow-lg border border-gray-100 py-2 z-50">
                <div className="flex items-center justify-between px-4 py-2 border-b border-gray-100">
                  <span className="font-semibold text-sm text-gray-900">Notifications</span>
                  <button className="text-xs text-[#0ea5e9] hover:underline">Mark all as read</button>
                </div>
                {notifications.map((n) => (
                  <div key={n.id} className={`flex items-start gap-3 px-4 py-3 hover:bg-gray-50 ${!n.read ? 'bg-blue-50/50' : ''}`}>
                    <div className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${
                      n.type === 'warning' ? 'bg-amber-500' : n.type === 'error' ? 'bg-red-500' : n.type === 'success' ? 'bg-green-500' : 'bg-blue-500'
                    }`} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-gray-800">{n.message}</p>
                      <p className="text-xs text-gray-400 mt-0.5">{n.time}</p>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        {/* AI Chat toggle */}
        <button
          onClick={toggleChat}
          className="p-2 hover:bg-gray-100 rounded-lg"
        >
          <MessageSquare size={20} className="text-gray-600" />
        </button>

        {/* User avatar */}
        <div className="relative">
          <button
            onClick={() => setUserOpen(!userOpen)}
            className="flex items-center gap-2 p-1 hover:bg-gray-100 rounded-lg ml-1"
          >
            <div className="w-8 h-8 rounded-full bg-[#1e3a5f] flex items-center justify-center text-white text-xs font-semibold">
              AH
            </div>
            <ChevronDown size={14} className="text-gray-400 hidden sm:block" />
          </button>

          {userOpen && (
            <>
              <div className="fixed inset-0" onClick={() => setUserOpen(false)} />
              <div className="absolute right-0 top-12 w-48 bg-white rounded-xl shadow-lg border border-gray-100 py-1 z-50">
                <div className="px-4 py-2 border-b border-gray-100">
                  <p className="text-sm font-medium text-gray-900">Ahmed Hassan</p>
                  <p className="text-xs text-gray-500">ahmed@ariesmarine.ae</p>
                </div>
                <button className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">Profile</button>
                <button className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">Settings</button>
                <button className="w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-gray-50">Logout</button>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
