import { useLocation } from 'react-router-dom';
import { useStore } from '@/store/useStore';
import {
  LayoutDashboard, Inbox, Users, Wrench, FolderKanban, Package,
  ShoppingCart, FileText, CreditCard, Truck, BookOpen,
  GitBranch, Bot, MessageSquare, Database, Sparkles, FileImage,
  ChevronLeft, ChevronRight,
} from 'lucide-react';

const navGroups = [
  {
    label: 'Main',
    items: [
      { label: 'Dashboard', icon: LayoutDashboard, route: '/dashboard' },
      { label: 'Enquiries', icon: Inbox, route: '/enquiries', badge: 6 },
      { label: 'Personnel', icon: Users, route: '/personnel' },
      { label: 'Assets', icon: Wrench, route: '/assets' },
      { label: 'Projects', icon: FolderKanban, route: '/projects' },
      { label: 'Stock', icon: Package, route: '/stock' },
      { label: 'Purchase Orders', icon: ShoppingCart, route: '/purchase-orders' },
      { label: 'Invoices', icon: FileText, route: '/invoices' },
      { label: 'Payments', icon: CreditCard, route: '/payments' },
      { label: 'Suppliers', icon: Truck, route: '/suppliers' },
      { label: 'Wiki', icon: BookOpen, route: '/wiki' },
    ],
  },
  {
    label: 'AI Admin',
    items: [
      { label: 'Workflows', icon: GitBranch, route: '/settings/workflows' },
      { label: 'Personas', icon: Bot, route: '/settings/personas' },
      { label: 'Channels', icon: MessageSquare, route: '/settings/channels' },
      { label: 'RAG Index', icon: Database, route: '/settings/rag' },
    ],
  },
  {
    label: 'Tools',
    items: [
      { label: 'Dynamic UI', icon: Sparkles, route: '/dynamic/ui-1' },
      { label: 'Letterhead', icon: FileImage, route: '/tools/letterhead' },
    ],
  },
];

export default function Sidebar() {
  const location = useLocation();
  const { sidebarOpen, mobileOpen, toggleSidebar, toggleMobile } = useStore();

  return (
    <>
      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={toggleMobile}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed left-0 top-16 h-[calc(100vh-4rem)] bg-[#0f172a] text-[#cbd5e1] transition-all duration-300 z-40 overflow-y-auto
          ${sidebarOpen ? 'w-60' : 'w-16'}
          ${mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
        `}
      >
        {/* Logo header */}
        <div className={`flex items-center gap-3 px-4 py-4 border-b border-slate-800 ${!sidebarOpen && 'lg:justify-center'}`}>
          <img src="/aries-logo-transparent.png" alt="Aries" className="w-8 h-8" />
          {sidebarOpen && (
            <div className="leading-tight">
              <div className="font-bold text-white text-sm">Aries</div>
              <div className="text-[10px] text-slate-400">Marine</div>
            </div>
          )}
        </div>

        {/* Navigation */}
        <nav className="pb-20">
          {navGroups.map((group) => (
            <div key={group.label}>
              {sidebarOpen && (
                <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider px-4 pt-4 pb-2">
                  {group.label}
                </div>
              )}
              {group.items.map((item) => {
                const isActive = location.pathname === item.route;
                const Icon = item.icon;
                return (
                  <a
                    key={item.route}
                    href={`#${item.route}`}
                    className={`flex items-center gap-3 px-4 py-3 text-sm transition-colors relative
                      ${isActive
                        ? 'bg-[#1e3a5f] text-white border-l-4 border-[#0ea5e9]'
                        : 'text-slate-300 hover:bg-slate-800 hover:text-white border-l-4 border-transparent'
                      }
                      ${!sidebarOpen && 'lg:justify-center'}
                    `}
                    onClick={(e) => {
                      e.preventDefault();
                      window.location.hash = item.route;
                      if (mobileOpen) toggleMobile();
                    }}
                  >
                    <Icon size={20} />
                    {sidebarOpen && (
                      <>
                        <span className="flex-1">{item.label}</span>
                        {'badge' in item && item.badge && (
                          <span className="bg-red-500 text-white text-[10px] font-bold rounded-full w-5 h-5 flex items-center justify-center">
                            {item.badge}
                          </span>
                        )}
                      </>
                    )}
                  </a>
                );
              })}
            </div>
          ))}
        </nav>

        {/* Toggle button (desktop only) */}
        <button
          onClick={toggleSidebar}
          className="hidden lg:flex absolute bottom-4 right-4 w-8 h-8 bg-slate-800 hover:bg-slate-700 rounded-full items-center justify-center text-slate-400 hover:text-white transition-colors"
        >
          {sidebarOpen ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
        </button>
      </aside>
    </>
  );
}
