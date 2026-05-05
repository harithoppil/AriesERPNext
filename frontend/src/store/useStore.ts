import { create } from 'zustand';
import type { User, ChatMessage, Notification } from '@/types';

interface AppState {
  // Sidebar
  sidebarOpen: boolean; mobileOpen: boolean;
  toggleSidebar: () => void; toggleMobile: () => void;
  // Chat
  chatOpen: boolean; messages: ChatMessage[]; activePersona: string;
  toggleChat: () => void; sendMessage: (content: string) => void; setPersona: (id: string) => void;
  // User
  user: User | null; login: (user: User) => void; logout: () => void;
  // Notifications
  notifications: Notification[]; markRead: (id: string) => void; markAllRead: () => void;
}

export const useStore = create<AppState>((set) => ({
  sidebarOpen: true,
  mobileOpen: false,
  toggleSidebar: () => set(s => ({ sidebarOpen: !s.sidebarOpen })),
  toggleMobile: () => set(s => ({ mobileOpen: !s.mobileOpen })),
  chatOpen: true,
  messages: [
    { id: '1', sender: 'ai', content: 'Welcome to Aries Marine ERP. How can I assist you today?', timestamp: new Date().toISOString() },
  ],
  activePersona: 'sales-assistant',
  toggleChat: () => set(s => ({ chatOpen: !s.chatOpen })),
  sendMessage: (content) => {
    const userMsg: ChatMessage = { id: Date.now().toString(), sender: 'user', content, timestamp: new Date().toISOString() };
    set(s => ({ messages: [...s.messages, userMsg] }));
    setTimeout(() => {
      const aiMsg: ChatMessage = { id: (Date.now()+1).toString(), sender: 'ai', content: `I understand you're asking about "${content}". Let me help you with that...`, timestamp: new Date().toISOString() };
      set(s => ({ messages: [...s.messages, aiMsg] }));
    }, 800);
  },
  setPersona: (id) => set({ activePersona: id }),
  user: null,
  login: (user) => set({ user }),
  logout: () => set({ user: null }),
  notifications: [],
  markRead: (id) => set(s => ({ notifications: s.notifications.map(n => n.id === id ? { ...n, read: true } : n) })),
  markAllRead: () => set(s => ({ notifications: s.notifications.map(n => ({ ...n, read: true })) })),
}));
