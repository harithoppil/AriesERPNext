import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useStore } from '@/store/useStore';
import { Anchor, ArrowRight } from 'lucide-react';

export default function Login() {
  const navigate = useNavigate();
  const { login } = useStore();
  const [email, setEmail] = useState('admin@ariesmarine.com');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(false);

  const handleSignIn = (e: React.FormEvent) => {
    e.preventDefault();
    login({
      id: 'admin-001',
      name: 'Admin User',
      email: 'admin@ariesmarine.com',
      avatar: '',
      role: 'Administrator',
    });
    navigate('/dashboard');
  };

  return (
    <div className="min-h-[100dvh] flex flex-col items-center justify-center bg-gradient-to-br from-[#1e3a5f] to-[#0f172a] px-4">
      {/* Radial highlight */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_30%,rgba(14,165,233,0.15),transparent_60%)] pointer-events-none" />

      <div className="relative z-10 w-full max-w-md">
        {/* White card */}
        <div className="bg-white rounded-2xl shadow-2xl p-8">
          {/* Logo */}
          <div className="flex flex-col items-center mb-6">
            <img
              src="/aries-logo-transparent.png"
              alt="Aries Marine"
              className="w-16 h-16 mb-3"
            />
            <h1 className="text-2xl font-bold text-[#1e3a5f]">
              Aries Marine ERP
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              AI-Native Enterprise Platform
            </p>
          </div>

          {/* Login form */}
          <form onSubmit={handleSignIn} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none text-sm text-gray-900"
                placeholder="Enter your email"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none text-sm text-gray-900"
                placeholder="Enter your password"
              />
            </div>

            <div className="flex items-center justify-between text-sm">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  className="rounded border-gray-300 text-[#1e3a5f] focus:ring-[#0ea5e9]"
                />
                <span className="text-gray-600">Remember me</span>
              </label>
              <button
                type="button"
                className="text-[#0ea5e9] hover:underline"
                onClick={() => alert('Password reset link sent to your email.')}
              >
                Forgot password?
              </button>
            </div>

            <button
              type="submit"
              className="w-full flex items-center justify-center gap-2 py-2.5 bg-[#1e3a5f] text-white rounded-lg hover:bg-[#2d5a87] transition-colors font-medium text-sm"
            >
              Sign In
              <ArrowRight size={16} />
            </button>
          </form>

          {/* Demo hint */}
          <p className="text-xs text-gray-400 text-center mt-4">
            Demo: admin@ariesmarine.com / any password
          </p>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-center gap-2 text-gray-400 mt-6 text-sm">
          <Anchor size={14} />
          <span>Aries Marine Consultancy LLC</span>
        </div>
      </div>
    </div>
  );
}
