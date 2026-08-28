import React, { useEffect, useState } from 'react';
import { History, Clock, FileCode, ExternalLink, Calendar, RefreshCw } from 'lucide-react';
import { api } from '../services/api';

export default function QueueHistoryView({ onSelectWorkLog, onSelectTicket }) {
  const [windows, setWindows] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchHistory = () => {
    setLoading(true);
    api.getQueueHistory()
      .then((data) => setWindows(data))
      .catch((err) => console.error('Failed to load queue history:', err))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchHistory();
  }, []);

  return (
    <div className="flex-1 flex flex-col overflow-y-auto p-6 space-y-6">
      {/* Page Title & Refresh */}
      <div className="flex items-center justify-between pb-4 border-b border-slate-800">
        <div>
          <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2.5">
            <History className="w-5 h-5 text-orange-400" />
            Entire Work Queue History
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Chronological audit log grouped in <strong>5-minute windows</strong> underneath their respective projects.
          </p>
        </div>

        <button
          onClick={fetchHistory}
          disabled={loading}
          className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 flex items-center gap-1.5 transition"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {loading ? (
        <div className="py-20 text-center text-slate-400 text-sm animate-pulse">
          Loading 5-minute queue history windows...
        </div>
      ) : windows.length === 0 ? (
        <div className="py-20 text-center text-slate-500 text-xs bg-slate-900/40 rounded-2xl border border-slate-800">
          No work logs recorded in the queue history yet.
        </div>
      ) : (
        <div className="space-y-8">
          {windows.map((win) => {
            const startDate = new Date(win.window_start);
            const endDate = new Date(win.window_end);

            return (
              <div key={win.key} className="space-y-4">
                {/* 5-Minute Window Header */}
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-800 text-slate-300 text-xs font-mono font-semibold border border-slate-700 shadow-sm">
                    <Clock className="w-3.5 h-3.5 text-orange-400" />
                    <span>
                      {startDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} -{' '}
                      {endDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                  <span className="text-xs text-slate-500 font-medium">
                    {startDate.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })}
                  </span>
                  <div className="flex-1 h-px bg-slate-800" />
                </div>

                {/* Projects in this 5-Minute Window */}
                <div className="space-y-4 pl-4 border-l-2 border-slate-800">
                  {win.projects.map((proj) => {
                    const projectColor = proj.project_color || '#3B82F6';

                    return (
                      <div
                        key={proj.project_id}
                        className="p-4 rounded-xl bg-slate-900/70 border border-slate-800/90 shadow-md space-y-3"
                      >
                        {/* Project Header with its own SET COLOR FOR THE FONT */}
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span
                              className="w-3 h-3 rounded-full shrink-0"
                              style={{ backgroundColor: projectColor }}
                            />
                            {/* Project Name in its own set font color */}
                            <h4
                              className="font-bold text-sm tracking-wide font-mono"
                              style={{ color: projectColor }}
                            >
                              {proj.project_name} [{proj.project_key}]
                            </h4>
                          </div>

                          <span className="text-[11px] text-slate-500 font-mono">
                            {proj.items.length} {proj.items.length === 1 ? 'change' : 'changes'}
                          </span>
                        </div>

                        {/* List of Changes in this Window */}
                        <div className="divide-y divide-slate-800/60">
                          {proj.items.map((item) => (
                            <div
                              key={item.id}
                              className="py-2.5 flex items-start justify-between gap-4 first:pt-0 last:pb-0 hover:bg-slate-800/30 p-2 rounded-lg transition"
                            >
                              <div className="min-w-0 flex-1 space-y-1">
                                <div className="flex items-center gap-2">
                                  <span
                                    onClick={() => onSelectTicket(item.ticket_id)}
                                    className="font-mono text-[10px] font-bold px-1.5 py-0.2 rounded bg-slate-800 text-slate-200 cursor-pointer hover:bg-slate-700"
                                  >
                                    {item.jira_key}
                                  </span>
                                  <span className="text-xs font-semibold text-slate-200">
                                    {item.ticket_title}
                                  </span>
                                </div>

                                <p className="text-xs text-slate-400 line-clamp-2 leading-relaxed">
                                  {item.summary_changes || item.what_was_done}
                                </p>
                              </div>

                              <button
                                onClick={() => onSelectWorkLog(item.id)}
                                className="px-2.5 py-1 text-[11px] font-medium bg-slate-800 hover:bg-slate-700 text-slate-300 rounded border border-slate-700 flex items-center gap-1 shrink-0 transition"
                              >
                                <ExternalLink className="w-3 h-3 text-orange-400" />
                                Work Log
                              </button>
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
