import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { getWikiPages } from '@/lib/api';
import {
  Search, Plus, FileText, ChevronRight, Clock, User,
} from 'lucide-react';

const categories = [
  { label: 'All', count: 6 },
  { label: 'Operations', count: 1 },
  { label: 'Safety', count: 2 },
  { label: 'Technical', count: 1 },
  { label: 'HR', count: 1 },
  { label: 'Equipment', count: 0 },
  { label: 'Projects', count: 1 },
];

const categoryColors: Record<string, string> = {
  Training: 'bg-blue-100 text-blue-700',
  Operations: 'bg-indigo-100 text-indigo-700',
  Inspection: 'bg-purple-100 text-purple-700',
  Safety: 'bg-green-100 text-green-700',
  Finance: 'bg-amber-100 text-amber-700',
  HR: 'bg-pink-100 text-pink-700',
  Projects: 'bg-cyan-100 text-cyan-700',
  Technical: 'bg-teal-100 text-teal-700',
  Equipment: 'bg-orange-100 text-orange-700',
};

export default function Wiki() {
  const navigate = useNavigate();
  const wikiPages = getWikiPages();
  const [activeCategory, setActiveCategory] = useState('All');
  const [searchQuery, setSearchQuery] = useState('');

  const filteredPages = useMemo(() => {
    return wikiPages.filter((page) => {
      const matchesCategory =
        activeCategory === 'All' || page.category === activeCategory;
      const matchesSearch =
        searchQuery === '' ||
        page.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        page.author.toLowerCase().includes(searchQuery.toLowerCase()) ||
        page.content.toLowerCase().includes(searchQuery.toLowerCase());
      return matchesCategory && matchesSearch;
    });
  }, [wikiPages, activeCategory, searchQuery]);

  const getDescription = (content: string) => {
    return content.replace(/#/g, '').replace(/\n/g, ' ').trim().slice(0, 120) + '...';
  };

  return (
    <div className="flex h-[calc(100dvh-4rem)]">
      {/* Category sidebar */}
      <aside className="w-[200px] bg-white border-r border-gray-200 flex-shrink-0 overflow-y-auto">
        <div className="p-4">
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
            Categories
          </h2>
          <nav className="space-y-1">
            {categories.map((cat) => (
              <button
                key={cat.label}
                onClick={() => setActiveCategory(cat.label)}
                className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors ${
                  activeCategory === cat.label
                    ? 'bg-[#1e3a5f] text-white'
                    : 'text-gray-700 hover:bg-gray-100'
                }`}
              >
                <span className="flex items-center gap-2">
                  <ChevronRight
                    size={14}
                    className={
                      activeCategory === cat.label
                        ? 'text-white'
                        : 'text-gray-400'
                    }
                  />
                  {cat.label}
                </span>
                <span
                  className={`text-xs font-medium ${
                    activeCategory === cat.label
                      ? 'text-white/80'
                      : 'text-gray-400'
                  }`}
                >
                  {cat.count}
                </span>
              </button>
            ))}
          </nav>
        </div>
      </aside>

      {/* Content area */}
      <main className="flex-1 overflow-y-auto bg-[#f8fafc] p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-xl font-semibold text-gray-900">Wiki</h1>
          <div className="flex items-center gap-3">
            <div className="relative">
              <Search
                size={16}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
              />
              <input
                type="text"
                placeholder="Search wiki..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none w-64"
              />
            </div>
            <button
              onClick={() => navigate('/wiki/edit/new')}
              className="flex items-center gap-2 px-4 py-2 bg-[#1e3a5f] text-white rounded-lg hover:bg-[#2d5a87] transition-colors text-sm font-medium"
            >
              <Plus size={16} />
              New Page
            </button>
          </div>
        </div>

        {/* Wiki cards */}
        <div className="space-y-3">
          {filteredPages.map((page) => (
            <div
              key={page.id}
              className="bg-white rounded-xl shadow-sm border border-gray-100 p-5 hover:shadow-md transition-shadow"
            >
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-3">
                  <FileText size={18} className="text-[#0ea5e9]" />
                  <button
                    onClick={() => navigate(`/wiki/${page.id}`)}
                    className="text-base font-semibold text-[#1e3a5f] hover:text-[#0ea5e9] transition-colors"
                  >
                    {page.title}
                  </button>
                </div>
                <span
                  className={`text-xs font-medium px-2.5 py-1 rounded-full ${
                    categoryColors[page.category] ||
                    'bg-gray-100 text-gray-700'
                  }`}
                >
                  {page.category}
                </span>
              </div>
              <div className="flex items-center gap-4 text-xs text-gray-500 mb-3 ml-[30px]">
                <span className="flex items-center gap-1">
                  <Clock size={12} />
                  {page.lastEdited}
                </span>
                <span className="flex items-center gap-1">
                  <User size={12} />
                  {page.author}
                </span>
              </div>
              <p className="text-sm text-gray-600 ml-[30px]">
                {getDescription(page.content)}
              </p>
              {/* Tags */}
              <div className="flex items-center gap-2 ml-[30px] mt-3">
                {page.tags.map((tag) => (
                  <span
                    key={tag}
                    className="text-[10px] px-2 py-0.5 bg-gray-100 text-gray-500 rounded-full"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          ))}
          {filteredPages.length === 0 && (
            <div className="text-center py-12 text-gray-400">
              <FileText size={40} className="mx-auto mb-3 opacity-50" />
              <p className="text-sm">No wiki pages found</p>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
