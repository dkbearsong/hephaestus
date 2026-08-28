import React, { useEffect, useState } from 'react';
import { X, GitCommit, CheckSquare, AlertTriangle, Sparkles, Terminal, FileCode2, Clock } from 'lucide-react';
import DiffViewer from './DiffViewer';
import { api } from '../services/api';

export default function WorkLogModal({ workLogId, onClose }) {
  const [log, setLog] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!workLogId) return;
    setLoading(true);
    api.getWorkLog(workLogId)
      .then((data) => setLog(data))
      .catch((e) => console.error('Error fetching work log:', e))
      .finally(() => setLoading(false));
  }, [workLogId]);

  if (!workLogId) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-4xl max-h-[90vh] shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Modal Header */}
        <div className="px-6 py-4 bg-slate-800/80 border-b border-slate-700/80 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-orange-500/20 text-orange-400 border border-orange-500/30">
              <FileCode2 className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs font-bold px-2 py-0.5 rounded bg-slate-800 text-slate-200 border border-slate-700">
                  {log?.jira_key || 'LOG'}
                </span>
                <h3 className="font-bold text-slate-100 text-base">
                  Full Work Log & Audit Review
                </h3>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                {log?.ticket_title} &bull; {log && new Date(log.timestamp).toLocaleString()}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {loading ? (
            <div className="py-16 text-center text-slate-400 text-sm animate-pulse">
              Loading full work log and diff details...
            </div>
          ) : !log ? (
            <div className="py-16 text-center text-rose-400 text-sm">
              Failed to load work log details.
            </div>
          ) : (
            <>
              {/* Metadata Card */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 p-4 rounded-xl bg-slate-950/60 border border-slate-800 text-xs">
                <div>
                  <span className="text-slate-500 uppercase text-[10px] font-bold block mb-1">
                    Project
                  </span>
                  <span
                    className="font-semibold"
                    style={{ color: log.project_color || '#3B82F6' }}
                  >
                    {log.project_name} ({log.project_key})
                  </span>
                </div>
                <div>
                  <span className="text-slate-500 uppercase text-[10px] font-bold block mb-1">
                    Git Branch
                  </span>
                  <span className="font-mono text-slate-300 truncate block">
                    {log.branch_name || 'N/A'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500 uppercase text-[10px] font-bold block mb-1">
                    Container Status
                  </span>
                  <span className="inline-flex items-center gap-1.5 text-amber-400 font-mono">
                    <span className="w-2 h-2 rounded-full bg-amber-400" />
                    Spun Down / Checkpointed
                  </span>
                </div>
              </div>

              {/* Target Prompt / Request */}
              <div className="space-y-1.5">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                  <Terminal className="w-3.5 h-3.5 text-orange-400" />
                  Target Prompt & Changes Requested
                </span>
                <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-300 text-xs font-mono leading-relaxed">
                  {log.prompt_processed || log.prompt_raw}
                </div>
              </div>

              {/* AI Breakdown: What was wrong vs What was done */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-4 rounded-xl bg-rose-950/20 border border-rose-900/50 space-y-2">
                  <span className="text-xs font-bold text-rose-300 flex items-center gap-1.5">
                    <AlertTriangle className="w-4 h-4 text-rose-400" />
                    What Was Wrong / Needed To Be Fixed
                  </span>
                  <p className="text-xs text-slate-300 leading-relaxed">
                    {log.what_was_wrong || 'No prior defect described.'}
                  </p>
                </div>

                <div className="p-4 rounded-xl bg-emerald-950/20 border border-emerald-900/50 space-y-2">
                  <span className="text-xs font-bold text-emerald-300 flex items-center gap-1.5">
                    <Sparkles className="w-4 h-4 text-emerald-400" />
                    What Was Done (Improvements Implemented)
                  </span>
                  <p className="text-xs text-slate-300 leading-relaxed">
                    {log.what_was_done || log.summary_changes}
                  </p>
                </div>
              </div>

              {/* User Verification Checklist */}
              {log.user_check_items && log.user_check_items.length > 0 && (
                <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-2.5">
                  <span className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
                    <CheckSquare className="w-4 h-4 text-amber-400" />
                    What Needs To Be Checked By The User
                  </span>
                  <ul className="space-y-1.5">
                    {log.user_check_items.map((item, idx) => (
                      <li key={idx} className="flex items-start gap-2 text-xs text-slate-300">
                        <span className="w-4 h-4 rounded border border-slate-700 bg-slate-900 flex items-center justify-center text-[10px] text-slate-400 shrink-0 mt-0.5">
                          {idx + 1}
                        </span>
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Git Unified Diff */}
              <div className="space-y-2">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                  <GitCommit className="w-3.5 h-3.5 text-purple-400" />
                  Committed Changes & Git Diff
                </span>
                <DiffViewer diffText={log.git_diff} />
              </div>

              {/* Full Execution Logs (Collapsible or raw preview) */}
              {log.full_log && (
                <details className="text-xs rounded-xl bg-slate-950 border border-slate-800/80 p-3 text-slate-400">
                  <summary className="font-semibold text-slate-300 cursor-pointer select-none">
                    Raw Execution Transcript & Harness Logs
                  </summary>
                  <pre className="mt-2 font-mono text-[11px] text-slate-400 whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto">
                    {log.full_log}
                  </pre>
                </details>
              )}
            </>
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-3 bg-slate-800/60 border-t border-slate-800 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg transition"
          >
            Close Work Log
          </button>
        </div>
      </div>
    </div>
  );
}
