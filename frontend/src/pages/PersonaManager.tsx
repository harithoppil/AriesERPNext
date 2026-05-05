import { useState } from 'react';
import { getPersonas } from '@/lib/api';
import type { Persona } from '@/types';
import {
  Sparkles, Plus, Pencil, Zap, X, Wand2, FileText, BarChart3, Download,
} from 'lucide-react';

const toolOptions = [
  { value: '/summarize', label: 'Summarize', icon: FileText },
  { value: '/generate_form', label: 'Generate Form', icon: Wand2 },
  { value: '/create_dashboard', label: 'Create Dashboard', icon: BarChart3 },
  { value: '/export', label: 'Export', icon: Download },
];

const toneOptions = ['Professional', 'Friendly', 'Formal', 'Analytical', 'Supportive', 'Technical'];

function ToolIcon({ tool }: { tool: string }) {
  const found = toolOptions.find((t) => t.value === tool);
  if (found) {
    const Icon = found.icon;
    return <Icon size={10} />;
  }
  return <Sparkles size={10} />;
}

export default function PersonaManager() {
  const [personas, setPersonas] = useState<Persona[]>(getPersonas());
  const [showDialog, setShowDialog] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  // Form state
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [tone, setTone] = useState('Professional');
  const [selectedTools, setSelectedTools] = useState<string[]>([]);
  const [systemPrompt, setSystemPrompt] = useState('');

  const resetForm = () => {
    setName('');
    setDescription('');
    setTone('Professional');
    setSelectedTools([]);
    setSystemPrompt('');
    setEditingId(null);
  };

  const openCreate = () => {
    resetForm();
    setShowDialog(true);
  };

  const openEdit = (persona: Persona) => {
    setName(persona.name);
    setDescription(persona.description);
    setTone(persona.tone);
    setSelectedTools(persona.tools);
    setSystemPrompt(persona.systemPrompt);
    setEditingId(persona.id);
    setShowDialog(true);
  };

  const toggleTool = (tool: string) => {
    setSelectedTools((prev) =>
      prev.includes(tool) ? prev.filter((t) => t !== tool) : [...prev, tool]
    );
  };

  const handleSubmit = () => {
    if (!name.trim()) {
      alert('Please enter a name');
      return;
    }

    if (editingId) {
      setPersonas((prev) =>
        prev.map((p) =>
          p.id === editingId
            ? { ...p, name, description, tone, tools: selectedTools, systemPrompt }
            : p
        )
      );
    } else {
      const newPersona: Persona = {
        id: `persona-${Date.now()}`,
        name,
        description,
        tone,
        tools: selectedTools,
        systemPrompt,
      };
      setPersonas([...personas, newPersona]);
    }

    setShowDialog(false);
    resetForm();
  };

  const handleActivate = (personaName: string) => {
    alert(`Activated persona: ${personaName}`);
  };

  return (
    <div className="p-6 bg-[#f8fafc] min-h-full relative">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">AI Personas</h1>
          <p className="text-sm text-gray-500 mt-1">
            Configure AI assistant personalities
          </p>
        </div>
        <button
          onClick={openCreate}
          className="flex items-center gap-2 px-4 py-2 bg-[#1e3a5f] text-white rounded-lg hover:bg-[#2d5a87] transition-colors text-sm font-medium"
        >
          <Plus size={16} />
          Create Persona
        </button>
      </div>

      {/* Persona grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {personas.map((persona) => (
          <div
            key={persona.id}
            className="bg-white rounded-xl shadow-sm border border-gray-100 p-5 hover:shadow-md transition-shadow"
          >
            {/* Header */}
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center">
                  <Sparkles size={20} className="text-[#0ea5e9]" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-gray-900">
                    {persona.name}
                  </h3>
                  <p className="text-xs text-gray-500">{persona.description}</p>
                </div>
              </div>
            </div>

            {/* Divider */}
            <div className="border-t border-gray-100 my-3" />

            {/* Tools */}
            <div className="mb-3">
              <span className="text-xs text-gray-500 mb-1.5 block">Tools:</span>
              <div className="flex flex-wrap gap-1.5">
                {persona.tools.map((tool) => (
                  <span
                    key={tool}
                    className="inline-flex items-center gap-1 text-xs px-2 py-1 bg-blue-50 text-blue-700 rounded-full"
                  >
                    <ToolIcon tool={tool} />
                    {tool.replace('/', '')}
                  </span>
                ))}
              </div>
            </div>

            {/* Divider */}
            <div className="border-t border-gray-100 my-3" />

            {/* Footer */}
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-500">
                Tone: <span className="font-medium text-gray-700">{persona.tone}</span>
              </span>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => openEdit(persona)}
                  className="p-1.5 text-gray-400 hover:text-[#1e3a5f] hover:bg-gray-100 rounded-lg transition-colors"
                  title="Edit"
                >
                  <Pencil size={14} />
                </button>
                <button
                  onClick={() => handleActivate(persona.name)}
                  className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-green-700 bg-green-50 hover:bg-green-100 rounded-lg transition-colors"
                >
                  <Zap size={12} />
                  Activate
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Create/Edit Dialog */}
      {showDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto mx-4">
            <div className="flex items-center justify-between p-5 border-b border-gray-100">
              <h2 className="text-lg font-semibold text-gray-900">
                {editingId ? 'Edit Persona' : 'Create Persona'}
              </h2>
              <button
                onClick={() => {
                  setShowDialog(false);
                  resetForm();
                }}
                className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <X size={18} />
              </button>
            </div>

            <div className="p-5 space-y-4">
              {/* Name */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Name
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Sales Assistant"
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none"
                />
              </div>

              {/* Description */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Description
                </label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="What does this persona do?"
                  rows={2}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none resize-none"
                />
              </div>

              {/* Tone */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Tone
                </label>
                <select
                  value={tone}
                  onChange={(e) => setTone(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none bg-white"
                >
                  {toneOptions.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </div>

              {/* Tools */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Tools
                </label>
                <div className="space-y-2">
                  {toolOptions.map((tool) => {
                    const Icon = tool.icon;
                    const checked = selectedTools.includes(tool.value);
                    return (
                      <label
                        key={tool.value}
                        className="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 cursor-pointer transition-colors"
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleTool(tool.value)}
                          className="rounded border-gray-300 text-[#1e3a5f] focus:ring-[#0ea5e9]"
                        />
                        <Icon size={14} className="text-gray-500" />
                        <span className="text-sm text-gray-700">{tool.label}</span>
                      </label>
                    );
                  })}
                </div>
              </div>

              {/* System Prompt */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  System Prompt
                </label>
                <textarea
                  value={systemPrompt}
                  onChange={(e) => setSystemPrompt(e.target.value)}
                  placeholder="Enter the system prompt for this persona..."
                  rows={4}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-[#0ea5e9] focus:border-transparent outline-none resize-none font-mono"
                />
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center justify-end gap-2 p-5 border-t border-gray-100">
              <button
                onClick={() => {
                  setShowDialog(false);
                  resetForm();
                }}
                className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSubmit}
                className="px-4 py-2 text-sm bg-[#1e3a5f] text-white rounded-lg hover:bg-[#2d5a87] transition-colors"
              >
                {editingId ? 'Save Changes' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
