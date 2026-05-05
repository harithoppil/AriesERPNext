import React from 'react';
import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getWikiById } from '@/lib/api';
import {
  ArrowLeft, Save, Globe, Trash2, Plus, X, Tag,
} from 'lucide-react';

const categoryOptions = [
  'Training', 'Operations', 'Inspection', 'Safety', 'Finance', 'HR',
];

// Simple markdown-to-html preview
function renderMarkdownPreview(content: string) {
  const lines = content.split('\n');
  const elements: React.ReactNode[] = [];
  let key = 0;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (line.startsWith('### ')) {
      elements.push(
        <h3 key={key++} className="text-base font-semibold text-gray-900 mt-4 mb-2">
          {line.replace('### ', '')}
        </h3>
      );
    } else if (line.startsWith('## ')) {
      elements.push(
        <h2 key={key++} className="text-lg font-semibold text-gray-900 mt-5 mb-2 pb-1 border-b border-gray-200">
          {line.replace('## ', '')}
        </h2>
      );
    } else if (line.startsWith('# ')) {
      elements.push(
        <h1 key={key++} className="text-2xl font-bold text-[#1e3a5f] mt-4 mb-3">
          {line.replace('# ', '')}
        </h1>
      );
    } else if (line.startsWith('- ')) {
      // Collect consecutive list items
      const items: string[] = [];
      let j = i;
      while (j < lines.length && lines[j].startsWith('- ')) {
        items.push(lines[j].replace('- ', ''));
        j++;
      }
      elements.push(
        <ul key={key++} className="list-disc pl-5 space-y-1 my-3">
          {items.map((item, idx) => (
            <li key={idx} className="text-sm text-gray-700">{item}</li>
          ))}
        </ul>
      );
      i = j - 1;
    } else if (line.match(/^\d+\.\s/)) {
      const items: string[] = [];
      let j = i;
      while (j < lines.length && lines[j].match(/^\d+\.\s/)) {
        items.push(lines[j].replace(/^\d+\.\s/, ''));
        j++;
      }
      elements.push(
        <ol key={key++} className="list-decimal pl-5 space-y-1 my-3">
          {items.map((item, idx) => (
            <li key={idx} className="text-sm text-gray-700">{item}</li>
          ))}
        </ol>
      );
      i = j - 1;
    } else if (line.trim() === '') {
      elements.push(<div key={key++} className="h-2" />);
    } else {
      // Inline bold
      const formatted = line.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
      elements.push(
        <p
          key={key++}
          className="text-sm text-gray-700 leading-relaxed my-1"
          dangerouslySetInnerHTML={{ __html: formatted }}
        />
      );
    }
  }

  return elements;
}

export default function WikiEdit() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const existingPage = id && id !== 'new' ? getWikiById(id) : null;

  const [title, setTitle] = useState(existingPage?.title || '');
  const [category, setCategory] = useState(existingPage?.category || 'Operations');
  const [content, setContent] = useState(existingPage?.content || '# New Wiki Page\n\nStart writing here...');
  const [tags, setTags] = useState<string[]>(existingPage?.tags || []);
  const [newTag, setNewTag] = useState('');
  const [showTagInput, setShowTagInput] = useState(false);

  useEffect(() => {
    if (existingPage) {
      setTitle(existingPage.title);
      setCategory(existingPage.category);
      setContent(existingPage.content);
      setTags(existingPage.tags);
    }
  }, [existingPage]);

  const handleAddTag = () => {
    if (newTag.trim() && !tags.includes(newTag.trim())) {
      setTags([...tags, newTag.trim()]);
      setNewTag('');
    }
    setShowTagInput(false);
  };

  const handleRemoveTag = (tag: string) => {
    setTags(tags.filter((t) => t !== tag));
  };

  const handleSave = () => {
    alert('Draft saved!');
  };

  const handlePublish = () => {
    alert('Page published!');
    navigate('/wiki');
  };

  const handleDelete = () => {
    if (confirm('Are you sure you want to delete this page?')) {
      navigate('/wiki');
    }
  };

  return (
    <div className="flex flex-col h-[calc(100dvh-4rem)] bg-[#f8fafc]">
      {/* Header bar */}
      <div className="flex items-center justify-between px-6 py-3 bg-white border-b border-gray-200">
        <button
          onClick={() => navigate('/wiki')}
          className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900 transition-colors"
        >
          <ArrowLeft size={16} />
          Back to Wiki
        </button>
        <div className="flex items-center gap-2">
          <button
            onClick={handleSave}
            className="flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors text-sm font-medium"
          >
            <Save size={14} />
            Save
          </button>
          <button
            onClick={handlePublish}
            className="flex items-center gap-2 px-4 py-2 bg-[#1e3a5f] text-white rounded-lg hover:bg-[#2d5a87] transition-colors text-sm font-medium"
          >
            <Globe size={14} />
            Publish
          </button>
          {existingPage && (
            <button
              onClick={handleDelete}
              className="flex items-center gap-2 px-4 py-2 bg-red-50 text-red-600 rounded-lg hover:bg-red-100 transition-colors text-sm font-medium"
            >
              <Trash2 size={14} />
              Delete
            </button>
          )}
        </div>
      </div>

      {/* Title & Category row */}
      <div className="px-6 py-3 bg-white border-b border-gray-200 flex items-center gap-4">
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Page title"
          className="flex-1 text-lg font-semibold text-gray-900 placeholder-gray-400 outline-none border-none bg-transparent"
        />
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-500">Category:</span>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 outline-none focus:ring-2 focus:ring-[#0ea5e9] bg-white"
          >
            {categoryOptions.map((cat) => (
              <option key={cat} value={cat}>
                {cat}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Split pane */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Editor */}
        <div className="flex-1 flex flex-col border-r border-gray-200">
          <div className="px-4 py-2 bg-gray-50 border-b border-gray-200 text-xs font-medium text-gray-500 uppercase tracking-wider">
            Edit
          </div>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="flex-1 w-full p-4 text-sm font-mono text-gray-800 bg-white resize-none outline-none leading-relaxed"
            spellCheck={false}
          />
        </div>

        {/* Right: Preview */}
        <div className="flex-1 flex flex-col bg-[#f8fafc]">
          <div className="px-4 py-2 bg-gray-50 border-b border-gray-200 text-xs font-medium text-gray-500 uppercase tracking-wider">
            Preview
          </div>
          <div className="flex-1 overflow-y-auto p-6">
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 min-h-full">
              {renderMarkdownPreview(content)}
            </div>
          </div>
        </div>
      </div>

      {/* Tags bar */}
      <div className="flex items-center gap-2 px-6 py-3 bg-white border-t border-gray-200">
        <Tag size={14} className="text-gray-400" />
        <span className="text-sm text-gray-500 mr-2">Tags:</span>
        {tags.map((tag) => (
          <span
            key={tag}
            className="inline-flex items-center gap-1 text-xs px-2.5 py-1 bg-blue-50 text-blue-700 rounded-full"
          >
            {tag}
            <button
              onClick={() => handleRemoveTag(tag)}
              className="hover:text-blue-900"
            >
              <X size={10} />
            </button>
          </span>
        ))}
        {showTagInput ? (
          <div className="flex items-center gap-1">
            <input
              type="text"
              value={newTag}
              onChange={(e) => setNewTag(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleAddTag();
                if (e.key === 'Escape') setShowTagInput(false);
              }}
              autoFocus
              className="text-xs border border-gray-200 rounded-full px-2 py-1 outline-none focus:ring-1 focus:ring-[#0ea5e9] w-24"
            />
            <button onClick={handleAddTag} className="text-blue-600 hover:text-blue-800">
              <Plus size={14} />
            </button>
          </div>
        ) : (
          <button
            onClick={() => setShowTagInput(true)}
            className="inline-flex items-center gap-1 text-xs px-2.5 py-1 bg-gray-100 text-gray-500 rounded-full hover:bg-gray-200 transition-colors"
          >
            <Plus size={10} />
            Add tag
          </button>
        )}
      </div>
    </div>
  );
}
