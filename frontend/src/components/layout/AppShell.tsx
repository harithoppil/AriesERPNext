import { Outlet } from 'react-router-dom';
import { useStore } from '@/store/useStore';
import Header from './Header';
import Sidebar from './Sidebar';
import AiChatPanel from './AiChatPanel';

export default function AppShell() {
  const { sidebarOpen, chatOpen } = useStore();

  const sidebarWidth = sidebarOpen ? 240 : 64;
  const chatWidth = chatOpen ? 320 : 0;

  return (
    <div className="min-h-[100dvh] bg-surface">
      <Header />
      <Sidebar />
      <AiChatPanel />

      {/* Main Content */}
      <main
        className="pt-16 min-h-[100dvh] transition-all duration-300"
        style={{
          marginLeft: `${sidebarWidth}px`,
          marginRight: `${chatWidth}px`,
        }}
      >
        <div className="p-6 max-w-[1440px]">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
