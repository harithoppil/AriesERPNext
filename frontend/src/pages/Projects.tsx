import { useMemo } from 'react';
import { getProjects } from '@/lib/api';

import {
  Plus,
  FolderKanban,
  Play,
  Clock,
  CheckCircle,
  PauseCircle,
  MapPin,
  Users,
  Calendar,
} from 'lucide-react';
import { format, parseISO } from 'date-fns';

const STATUS_CONFIG = {
  active: {
    label: 'Active',
    dot: 'bg-green-500',
    icon: Play,
  },
  planning: {
    label: 'Planning',
    dot: 'bg-blue-500',
    icon: Clock,
  },
  completed: {
    label: 'Completed',
    dot: 'bg-gray-500',
    icon: CheckCircle,
  },
  'on-hold': {
    label: 'On Hold',
    dot: 'bg-amber-500',
    icon: PauseCircle,
  },
};

function getProgressColor(progress: number): string {
  if (progress >= 80) return 'bg-green-500';
  if (progress >= 50) return 'bg-[#0ea5e9]';
  if (progress >= 20) return 'bg-amber-500';
  return 'bg-[#1e3a5f]';
}

function formatBudget(value: number): string {
  if (value >= 1000000) {
    return `AED ${(value / 1000000).toFixed(1)}M`;
  }
  if (value >= 1000) {
    return `AED ${(value / 1000).toFixed(0)}K`;
  }
  return `AED ${value}`;
}

export default function Projects() {
  const projects = getProjects();

  const stats = useMemo(() => {
    return {
      active: projects.filter((p) => p.status === 'active').length,
      planning: projects.filter((p) => p.status === 'planning').length,
      completed: projects.filter((p) => p.status === 'completed').length,
      onHold: projects.filter((p) => p.status === 'on-hold').length,
    };
  }, [projects]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-[#0f172a]">Projects</h2>
          <p className="text-sm text-[#64748b] mt-1">
            {projects.length} projects
          </p>
        </div>
        <button className="inline-flex items-center gap-2 bg-[#1e3a5f] text-white hover:bg-[#2d5a87] rounded-lg px-4 py-2.5 text-sm font-medium transition-colors w-fit">
          <Plus size={16} />
          New Project
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
          <div className="flex items-center gap-2 mb-2">
            <Play size={16} className="text-green-500" />
            <span className="text-xs font-medium text-[#64748b] uppercase">
              Active
            </span>
          </div>
          <p className="text-2xl font-bold text-[#0f172a]">{stats.active}</p>
        </div>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
          <div className="flex items-center gap-2 mb-2">
            <Clock size={16} className="text-blue-500" />
            <span className="text-xs font-medium text-[#64748b] uppercase">
              Planning
            </span>
          </div>
          <p className="text-2xl font-bold text-[#0f172a]">{stats.planning}</p>
        </div>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
          <div className="flex items-center gap-2 mb-2">
            <CheckCircle size={16} className="text-gray-500" />
            <span className="text-xs font-medium text-[#64748b] uppercase">
              Completed
            </span>
          </div>
          <p className="text-2xl font-bold text-[#0f172a]">
            {stats.completed}
          </p>
        </div>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
          <div className="flex items-center gap-2 mb-2">
            <PauseCircle size={16} className="text-amber-500" />
            <span className="text-xs font-medium text-[#64748b] uppercase">
              On Hold
            </span>
          </div>
          <p className="text-2xl font-bold text-[#0f172a]">{stats.onHold}</p>
        </div>
      </div>

      {/* Project Cards Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {projects.map((project) => {
          const config = STATUS_CONFIG[project.status];
          const progressColor = getProgressColor(project.progress);

          return (
            <div
              key={project.id}
              className="bg-white rounded-2xl shadow-sm border border-gray-100 hover:shadow-md transition-shadow duration-200 p-5"
            >
              {/* Status + Name */}
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span
                    className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${config.dot}`}
                  />
                  <h3 className="font-semibold text-[#0f172a] text-lg leading-tight">
                    {project.name}
                  </h3>
                </div>
              </div>

              {/* Client */}
              <p className="text-sm text-[#64748b] mb-4">{project.client}</p>

              {/* Divider */}
              <div className="border-t border-gray-100 my-3" />

              {/* Progress */}
              <div className="mb-4">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs font-medium text-[#64748b]">
                    Progress
                  </span>
                  <span className="text-xs font-bold text-[#0f172a]">
                    {project.progress}%
                  </span>
                </div>
                <div className="w-full h-2.5 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${progressColor}`}
                    style={{ width: `${project.progress}%` }}
                  />
                </div>
              </div>

              {/* Budget */}
              <p className="text-sm font-medium text-[#0f172a] mb-3">
                Budget:{" "}
                <span className="text-[#0ea5e9]">
                  {formatBudget(project.budgetSpent)}
                </span>{" "}
                <span className="text-[#94a3b8]">/ {formatBudget(project.budgetTotal)}</span>
              </p>

              {/* Info Grid */}
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div className="flex items-center gap-2 text-sm text-[#64748b]">
                  <Calendar size={14} className="text-[#94a3b8] flex-shrink-0" />
                  <div>
                    <span className="text-[10px] text-[#94a3b8] uppercase block">
                      Start
                    </span>
                    <span className="text-[#0f172a] font-medium">
                      {format(parseISO(project.startDate), 'MMM yyyy')}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-2 text-sm text-[#64748b]">
                  <Calendar size={14} className="text-[#94a3b8] flex-shrink-0" />
                  <div>
                    <span className="text-[10px] text-[#94a3b8] uppercase block">
                      End
                    </span>
                    <span className="text-[#0f172a] font-medium">
                      {format(parseISO(project.endDate), 'MMM yyyy')}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-2 text-sm text-[#64748b]">
                  <MapPin size={14} className="text-[#94a3b8] flex-shrink-0" />
                  <div>
                    <span className="text-[10px] text-[#94a3b8] uppercase block">
                      Location
                    </span>
                    <span className="text-[#0f172a] font-medium">
                      {project.location}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-2 text-sm text-[#64748b]">
                  <Users size={14} className="text-[#94a3b8] flex-shrink-0" />
                  <div>
                    <span className="text-[10px] text-[#94a3b8] uppercase block">
                      Team
                    </span>
                    <span className="text-[#0f172a] font-medium">
                      {project.team} members
                    </span>
                  </div>
                </div>
              </div>

              {/* Divider */}
              <div className="border-t border-gray-100 my-3" />

              {/* Description */}
              <p className="text-sm text-[#64748b] line-clamp-2">
                {project.description}
              </p>
            </div>
          );
        })}
      </div>

      {projects.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-[#94a3b8]">
          <FolderKanban size={48} className="mb-4 opacity-40" />
          <p className="text-lg font-medium">No projects found</p>
        </div>
      )}
    </div>
  );
}
