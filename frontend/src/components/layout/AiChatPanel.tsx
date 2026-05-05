import { useState, useRef, useEffect } from 'react';
import { useStore } from '@/store/useStore';
import { getPersonas } from '@/lib/api';
import {
  Sparkles, X, Send, Bot, User,
} from 'lucide-react';

const quickActions = ['Generate Form', 'Create Dashboard', 'Summarize', 'Export'];

export default function AiChatPanel() {
  const { chatOpen, toggleChat, messages, sendMessage, activePersona, setPersona } = useStore();
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [personaDropdownOpen, setPersonaDropdownOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const personas = getPersonas();
  const activePersonaName = personas.find(p => p.id === activePersona)?.name || 'Sales Assistant';

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = () => {
    if (!input.trim()) return;
    setIsTyping(true);
    sendMessage(input.trim());
    setInput('');
    setTimeout(() => setIsTyping(false), 1500);
  };

  const handleQuickAction = (action: string) => {
    setIsTyping(true);
    sendMessage(`/${action.toLowerCase().replace(' ', '_')}`);
    setTimeout(() => setIsTyping(false), 1500);
  };

  if (!chatOpen) return null;

  return (
    <aside className="fixed right-0 top-16 h-[calc(100vh-4rem)] w-80 bg-[#f1f5f9] border-l border-gray-200 flex flex-col z-30">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-white">
        <div className="flex items-center gap-2">
          <Sparkles size={18} className="text-[#0ea5e9]" />
          <span className="font-semibold text-sm text-gray-900">AI Assistant</span>
        </div>
        <div className="flex items-center gap-2">
          {/* Persona selector */}
          <div className="relative">
            <button
              onClick={() => setPersonaDropdownOpen(!personaDropdownOpen)}
              className="flex items-center gap-1 px-2 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded-md transition-colors"
            >
              <Bot size={12} />
              <span className="max-w-[80px] truncate">{activePersonaName}</span>
            </button>
            {personaDropdownOpen && (
              <>
                <div className="fixed inset-0" onClick={() => setPersonaDropdownOpen(false)} />
                <div className="absolute right-0 top-8 w-48 bg-white rounded-lg shadow-lg border border-gray-100 py-1 z-50">
                  {personas.map((p) => (
                    <button
                      key={p.id}
                      onClick={() => { setPersona(p.id); setPersonaDropdownOpen(false); }}
                      className={`w-full text-left px-3 py-2 text-xs hover:bg-gray-50 ${activePersona === p.id ? 'bg-blue-50 text-[#0ea5e9]' : 'text-gray-700'}`}
                    >
                      <div className="font-medium">{p.name}</div>
                      <div className="text-gray-400 truncate">{p.description}</div>
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
          <button onClick={toggleChat} className="p-1 hover:bg-gray-100 rounded">
            <X size={16} className="text-gray-500" />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex gap-2 ${msg.sender === 'user' ? 'flex-row-reverse' : ''}`}
          >
            <div className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 ${
              msg.sender === 'user' ? 'bg-[#1e3a5f]' : 'bg-[#0ea5e9]'
            }`}>
              {msg.sender === 'user' ? <User size={14} className="text-white" /> : <Bot size={14} className="text-white" />}
            </div>
            <div className={`max-w-[80%] px-4 py-2.5 text-sm ${
              msg.sender === 'user'
                ? 'bg-[#0ea5e9] text-white rounded-2xl rounded-tr-sm'
                : 'bg-white shadow-sm rounded-2xl rounded-tl-sm text-gray-800 border border-gray-100'
            }`}>
              {msg.content}
            </div>
          </div>
        ))}

        {isTyping && (
          <div className="flex gap-2">
            <div className="w-7 h-7 rounded-full bg-[#0ea5e9] flex items-center justify-center flex-shrink-0">
              <Bot size={14} className="text-white" />
            </div>
            <div className="bg-white shadow-sm rounded-2xl rounded-tl-sm px-4 py-3 border border-gray-100">
              <div className="flex gap-1">
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Quick actions */}
      <div className="px-4 py-2 flex flex-wrap gap-2">
        {quickActions.map((action) => (
          <button
            key={action}
            onClick={() => handleQuickAction(action)}
            className="px-3 py-1 text-xs bg-white border border-gray-200 rounded-full text-gray-600 hover:bg-[#0ea5e9] hover:text-white hover:border-[#0ea5e9] transition-colors"
          >
            {action}
          </button>
        ))}
      </div>

      {/* Input */}
      <div className="px-4 py-3 border-t border-gray-200 bg-white">
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder="Type a message..."
            rows={1}
            className="flex-1 resize-none border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent bg-gray-50"
          />
          <button
            onClick={handleSend}
            className="p-2 bg-[#0ea5e9] hover:bg-[#0284c7] text-white rounded-lg transition-colors"
          >
            <Send size={16} />
          </button>
        </div>
      </div>
    </aside>
  );
}
