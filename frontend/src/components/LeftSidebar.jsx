import React, { useState } from 'react';
import {
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  Clock,
  FolderGit2,
  GitBranch,
  History,
  MessageSquare,
  Sparkles,
  AlertCircle,
  CheckCircle2,
  ExternalLink
} from 'lucide-react';

export default function LeftSidebar({
  isCollapsed,
  onToggleCollapse,
  projects,
  projectTickets,
  recentActions,
  selectedProjectId,
  selectedTicketId,
  currentView,
  onSelectProject,
  onSelectTicket,
  onViewQueueHistory,
  onSelectWorkLog
}) {
  // State tracking expanded projects
  const [expandedProjects, setExpandedProjects] = useState({});

  const toggleProjectExpand = (e, projectId) => {
    e.stopPropagation(); // Don't trigger project click
    setExpandedProjects((prev) => ({
      ...prev,
      [projectId]: !prev[projectId]
    }));
  };

  if (isCollapsed) {
    return (
      <aside className="w-12 bg-slate-900 border-r border-slate-800 flex flex-col items-center py-4 shrink-0 transition-all duration-300">
        <button
          onClick={onToggleCollapse}
          title="Expand Sidebar"
          className="p-2 rounded-lg bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700 mb-6"
        >
          <ChevronRight className="w-4 h-4" />
        </button>

        <button
          onClick={onViewQueueHistory}
          title="Queue History"
          className={`p-2 rounded-lg mb-3 ${
            currentView === 'queue-history'
              ? 'bg-orange-500/20 text-orange-400 border border-orange-500/40'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
          }`}
        >
          <History className="w-4 h-4" />
        </button>

        <div className="w-6 h-px bg-slate-800 my-2" />

        <div className="flex flex-col gap-2">
          {projects.map((p) => (
            <button
              key={p.id}
              onClick={() => onSelectProject(p.id)}
              title={p.name}
              className="w-7 h-7 rounded-md flex items-center justify-center text-xs font-bold font-mono transition shadow"
              style={{
                backgroundColor: `${p.color || '#3B82F6'}22`,
                color: p.color || '#3B82F6',
                border: `1px solid ${p.color || '#3B82F6'}55`
              }}
            >
              {p.key.slice(0, 2)}
            </button>
          ))}
        </div>
      </aside>
    );
  }

  return (
    <aside className="w-72 bg-slate-900 border-r border-slate-800 flex flex-col shrink-0 h-[calc(100vh-3.5rem)] transition-all duration-300">
      {/* Sidebar Header & Collapse Toggle */}
      <div className="px-3.5 py-3 border-b border-slate-800/80 flex items-center justify-between">
        <span className="text-xs font-bold text-slate-300 uppercase tracking-wider">
          Workspace Navigation
        </span>
        <button
          onClick={onToggleCollapse}
          title="Collapse Sidebar"
          className="p-1 rounded-md text-slate-400 hover:text-white hover:bg-slate-800 transition"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-6">
        {/* Section 1: Top - 5 Most Recent Actions & Queue History Link */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-slate-400" />
              Recent Actions
            </span>
          </div>

          <div className="space-y-1.5">
            {recentActions.length === 0 ? (
              <div className="text-[11px] text-slate-500 italic p-2">No recent actions recorded</div>
            ) : (
              recentActions.slice(0, 5).map((action) => (
                <div
                  key={action.id}
                  onClick={() => onSelectWorkLog(action.id)}
                  className="p-2 rounded-lg bg-slate-950/60 border border-slate-800 hover:border-slate-700 hover:bg-slate-800/50 cursor-pointer transition text-xs group"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span
                      className="font-bold text-[10px] font-mono px-1.5 py-0.2 rounded"
                      style={{
                        backgroundColor: `${action.project_color || '#3B82F6'}22`,
                        color: action.project_color || '#3B82F6',
                        border: `1px solid ${action.project_color || '#3B82F6'}44`
                      }}
                    >
                      {action.jira_key}
                    </span>
                    <span className="text-[10px] text-slate-500">
                      {new Date(action.timestamp).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit'
                      })}
                    </span>
                  </div>
                  <p className="text-slate-300 text-[11px] line-clamp-1 group-hover:text-slate-100">
                    {action.summary_changes || action.prompt_processed}
                  </p>
                </div>
              ))
            )}
          </div>

          {/* Link to view entire queue history */}
          <button
            onClick={onViewQueueHistory}
            className={`mt-2.5 w-full flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg text-xs font-semibold border transition ${
              currentView === 'queue-history'
                ? 'bg-orange-500/20 text-orange-300 border-orange-500/50'
                : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-slate-200 hover:border-slate-700'
            }`}
          >
            <History className="w-3.5 h-3.5 text-orange-400" />
            View Entire Queue History
          </button>
        </div>

        {/* Section 2: Projects List with Expand/Collapse Ticket History */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
              <FolderGit2 className="w-3.5 h-3.5 text-slate-400" />
              Projects
            </span>
            <span className="text-[10px] text-slate-500">{projects.length} Active</span>
          </div>

          <div className="space-y-1.5">
            {projects.map((project) => {
              const isExpanded = !!expandedProjects[project.id];
              const isSelected = selectedProjectId === project.id && currentView === 'project-details';
              const tickets = projectTickets[project.id] || [];

              return (
                <div key={project.id} className="rounded-lg bg-slate-950/40 border border-slate-800/80 overflow-hidden">
                  {/* Project Row Header */}
                  <div
                    className={`flex items-center p-2 transition cursor-pointer ${
                      isSelected
                        ? 'bg-slate-800/90 text-white font-semibold'
                        : 'hover:bg-slate-800/50 text-slate-300'
                    }`}
                  >
                    {/* Expand/Collapse Button to the left of the project */}
                    <button
                      onClick={(e) => toggleProjectExpand(e, project.id)}
                      className="p-1 rounded text-slate-400 hover:text-slate-100 hover:bg-slate-700/60 mr-1.5 shrink-0"
                      title={isExpanded ? 'Collapse tickets' : 'Expand tickets'}
                    >
                      {isExpanded ? (
                        <ChevronDown className="w-3.5 h-3.5" />
                      ) : (
                        <ChevronRight className="w-3.5 h-3.5" />
                      )}
                    </button>

                    {/* Project Name (Clicking opens Project Details page) */}
                    <div
                      onClick={() => onSelectProject(project.id)}
                      className="flex-1 flex items-center gap-2 min-w-0"
                    >
                      <span
                        className="w-2.5 h-2.5 rounded-full shrink-0"
                        style={{ backgroundColor: project.color || '#3B82F6' }}
                      />
                      <span
                        className="truncate text-xs font-medium"
                        style={{ color: project.color || '#3B82F6' }}
                      >
                        {project.name}
                      </span>
                    </div>

                    {/* Ticket Count Badge */}
                    <span className="text-[10px] text-slate-500 font-mono ml-1">
                      {project.ticket_count || tickets.length}
                    </span>
                  </div>

                  {/* Collapsible Ticket & Chat History */}
                  {isExpanded && (
                    <div className="pl-6 pr-2 py-1.5 space-y-1 bg-slate-900/60 border-t border-slate-800/50">
                      {tickets.length === 0 ? (
                        <div className="text-[10px] text-slate-500 italic py-1">
                          No active tickets yet.
                        </div>
                      ) : (
                        tickets.map((t) => {
                          const isTicketActive = selectedTicketId === t.id && currentView === 'ticket-review';

                          let statusBadgeClass = 'bg-slate-800 text-slate-400';
                          if (t.status === 'paused_waiting_input') {
                            statusBadgeClass = 'bg-rose-950 text-rose-300 border border-rose-800';
                          } else if (t.status === 'review_ready') {
                            statusBadgeClass = 'bg-amber-950 text-amber-300 border border-amber-800';
                          } else if (t.status === 'merged') {
                            statusBadgeClass = 'bg-emerald-950 text-emerald-300 border border-emerald-800';
                          }

                          return (
                            <div
                              key={t.id}
                              onClick={() => onSelectTicket(t.id)}
                              className={`p-1.5 rounded text-[11px] cursor-pointer flex items-center justify-between gap-1 transition ${
                                isTicketActive
                                  ? 'bg-orange-500/20 text-orange-200 font-medium'
                                  : 'hover:bg-slate-800 text-slate-400 hover:text-slate-200'
                              }`}
                            >
                              <div className="flex items-center gap-1.5 min-w-0">
                                <MessageSquare className="w-3 h-3 text-slate-500 shrink-0" />
                                <span className="font-mono text-[10px] font-semibold text-slate-300">
                                  {t.jira_key}
                                </span>
                                <span className="truncate text-slate-300">{t.title}</span>
                              </div>

                              {t.status === 'paused_waiting_input' && (
                                <span className="w-2 h-2 rounded-full bg-rose-500 animate-ping shrink-0" />
                              )}
                            </div>
                          );
                        })
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </aside>
  );
}
