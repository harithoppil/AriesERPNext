import { useState } from 'react';
import { getWorkflows } from '@/lib/api';
import type { Workflow } from '@/types';
import {
  GitBranch, Plus, Play, Pencil, Trash2,
} from 'lucide-react';

interface MiniFlowProps {
  nodes: number;
  status: string;
}

function MiniFlow({ nodes }: MiniFlowProps) {
  // Create a simple linear flow: Start -> Process x (nodes-2) -> End
  const processNodes = Math.max(0, nodes - 2);
  return (
    <div className="flex items-center gap-1 py-3">
      {/* Start node */}
      <div className="flex flex-col items-center">
        <div className="w-6 h-6 rounded-full bg-green-500 flex items-center justify-center">
          <div className="w-2 h-2 rounded-full bg-white" />
        </div>
        <span className="text-[9px] text-gray-500 mt-0.5">Start</span>
      </div>
      {/* Connector */}
      <div className="w-4 h-0.5 bg-gray-300 -mt-4" />

      {/* Process nodes */}
      {Array.from({ length: Math.min(processNodes, 3) }).map((_, i) => (
        <div key={i} className="flex items-center">
          <div className="flex flex-col items-center">
            <div className="w-6 h-5 rounded bg-[#0ea5e9] flex items-center justify-center">
              <div className="w-1.5 h-1.5 rounded-full bg-white" />
            </div>
            <span className="text-[9px] text-gray-500 mt-0.5">Proc</span>
          </div>
          {i < Math.min(processNodes, 3) - 1 && (
            <div className="w-3 h-0.5 bg-gray-300 -mt-4" />
          )}
        </div>
      ))}
      {processNodes > 3 && (
        <>
          <div className="w-2 h-0.5 bg-gray-300 -mt-4" />
          <span className="text-[9px] text-gray-400 -mt-4 px-0.5">...</span>
          <div className="w-2 h-0.5 bg-gray-300 -mt-4" />
        </>
      )}

      {/* Connector to end */}
      <div className="w-4 h-0.5 bg-gray-300 -mt-4" />

      {/* End node */}
      <div className="flex flex-col items-center">
        <div className="w-6 h-6 rounded-full bg-red-500 flex items-center justify-center">
          <div className="w-2 h-2 rounded-full bg-white" />
        </div>
        <span className="text-[9px] text-gray-500 mt-0.5">End</span>
      </div>
    </div>
  );
}

export default function WorkflowBuilder() {
  const [workflows, setWorkflows] = useState<Workflow[]>(getWorkflows());

  const handleDelete = (id: string) => {
    if (confirm('Delete this workflow?')) {
      setWorkflows(workflows.filter((w) => w.id !== id));
    }
  };

  const handleRun = (name: string) => {
    alert(`Running workflow: ${name}`);
  };

  return (
    <div className="p-6 bg-[#f8fafc] min-h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Workflow Builder</h1>
          <p className="text-sm text-gray-500 mt-1">
            Design and manage automated workflows
          </p>
        </div>
        <button
          onClick={() => alert('Create new workflow - coming soon!')}
          className="flex items-center gap-2 px-4 py-2 bg-[#1e3a5f] text-white rounded-lg hover:bg-[#2d5a87] transition-colors text-sm font-medium"
        >
          <Plus size={16} />
          New Workflow
        </button>
      </div>

      {/* Workflow grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {workflows.map((workflow) => (
          <div
            key={workflow.id}
            className="bg-white rounded-xl shadow-sm border border-gray-100 p-5 hover:shadow-md transition-shadow"
          >
            {/* Header */}
            <div className="flex items-start justify-between mb-2">
              <div className="flex items-center gap-2">
                <div
                  className={`w-2.5 h-2.5 rounded-full ${
                    workflow.status === 'active' ? 'bg-green-500' : 'bg-amber-500'
                  }`}
                />
                <h3 className="text-sm font-semibold text-gray-900">
                  {workflow.name}
                </h3>
              </div>
              <GitBranch size={16} className="text-gray-400" />
            </div>

            {/* Description */}
            <p className="text-xs text-gray-500 mb-3">{workflow.description}</p>

            {/* Divider */}
            <div className="border-t border-gray-100" />

            {/* Mini flow */}
            <MiniFlow nodes={workflow.nodes} status={workflow.status} />

            {/* Divider */}
            <div className="border-t border-gray-100" />

            {/* Footer */}
            <div className="flex items-center justify-between mt-3">
              <div className="text-xs text-gray-500">
                <span>{workflow.nodes} nodes</span>
                <span className="mx-2">·</span>
                <span>{workflow.runs} runs</span>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => alert(`Edit ${workflow.name}`)}
                  className="p-1.5 text-gray-400 hover:text-[#1e3a5f] hover:bg-gray-100 rounded-lg transition-colors"
                  title="Edit"
                >
                  <Pencil size={14} />
                </button>
                <button
                  onClick={() => handleRun(workflow.name)}
                  className="p-1.5 text-gray-400 hover:text-green-600 hover:bg-green-50 rounded-lg transition-colors"
                  title="Run"
                >
                  <Play size={14} />
                </button>
                <button
                  onClick={() => handleDelete(workflow.id)}
                  className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                  title="Delete"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
