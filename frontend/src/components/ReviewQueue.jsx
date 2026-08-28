import React, { useState } from 'react';
import {
  GitBranch,
  GitMerge,
  Send,
  FileCode,
  CheckCircle2,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Terminal,
  ExternalLink,
  MessageSquare,
  Clock,
  Sparkles
} from 'lucide-react';

export default function ReviewQueue({
  ticket,
  workLogs = [],
  chatMessages = [],
  onSelectWorkLog,
  onSubmitPromptUpdate,
  onOpenMergeModal,
  onSwitchToChat
}) {
  const [expandedLogIds, setExpandedLogIds] = useState({});
  const [newPromptText, setNewPromptText] = useState('');
  const [isSubmittingPrompt, setIsSubmittingPrompt] = useState(false);

  if (!ticket) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center text-slate-500">
        <GitBranch className="w-12 h-12 stroke-[1.5] mb-3 text-slate-600" />
        <h3 className="text-base font-semibold text-slate-300">No Ticket Selected</h3>
        <p className="text-xs max-w-sm mt-1">
          Select a ticket or branch from the left sidebar to review changes, direct the agent, or finalize a git merge.
        </p>
      </div>
    );
  }

  const toggleLogExpand = (logId) => {
    setExpandedLogIds((prev) => ({
      ...prev,
      [logId]: !prev[logId]
    }));
  };

  const handlePromptSubmit = async (e) => {
    e.preventDefault();
    if (!newPromptText.trim()) return;

    setIsSubmittingPrompt(true);
    try {
      await onSubmitPromptUpdate(ticket.id, newPromptText);
      setNewPromptText('');
    } catch (err) {
      console.error('Failed to submit prompt update:', err);
    } finally {
      setIsSubmittingPrompt(false);
    }
  };

  const isMerged = ticket.status === 'merged';

  return (
    <div className="flex-1 flex flex-col overflow-y-auto p-6 space-y-6">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-5 rounded-2xl bg-slate-900/90 border border-slate-800 shadow-xl">
        <div>
          <div className="flex items-center gap-2.5 mb-1.5">
            <span className="px-2.5 py-0.5 rounded-md font-mono text-xs font-bold bg-slate-800 text-slate-200 border border-slate-700">
              {ticket.jira_key}
            </span>
            <span
              className="text-xs font-semibold px-2.5 py-0.5 rounded-full"
              style={{
                backgroundColor: `${ticket.project_color || '#3B82F6'}22`,
                color: ticket.project_color || '#3B82F6',
                border: `1px solid ${ticket.project_color || '#3B82F6'}55`
              }}
            >
              {ticket.project_name}
            </span>

            {isMerged ? (
              <span className="px-2 py-0.5 text-[10px] font-bold rounded-full bg-emerald-950 text-emerald-300 border border-emerald-800">
                Merged & Cleaned Up
              </span>
            ) : ticket.status === 'paused_waiting_input' ? (
              <span className="px-2 py-0.5 text-[10px] font-bold rounded-full bg-rose-950 text-rose-300 border border-rose-800 animate-pulse">
                Paused Waiting on Input
              </span>
            ) : (
              <span className="px-2 py-0.5 text-[10px] font-bold rounded-full bg-amber-950 text-amber-300 border border-amber-800">
                Review Ready
              </span>
            )}
          </div>

          <h2 className="text-lg font-bold text-slate-100">{ticket.title}</h2>

          <div className="flex items-center gap-4 text-xs text-slate-400 mt-2 font-mono">
            <span className="flex items-center gap-1.5 text-purple-400">
              <GitBranch className="w-3.5 h-3.5" />
              {ticket.branch_name || 'No branch'}
            </span>
            <span className="text-slate-500">&bull;</span>
            <span className="text-slate-400">
              Container: {ticket.container_id || 'isolated sandbox'}
            </span>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2.5">
          <button
            onClick={onSwitchToChat}
            className="px-3.5 py-2 rounded-xl text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 flex items-center gap-2 transition"
          >
            <MessageSquare className="w-3.5 h-3.5 text-cyan-400" />
            Agent Chat ({chatMessages.length})
          </button>

          {!isMerged && (
            <button
              onClick={() => onOpenMergeModal(ticket)}
              className="px-4 py-2 rounded-xl text-xs font-bold bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white shadow-lg shadow-emerald-950/40 flex items-center gap-2 transition cursor-pointer"
            >
              <GitMerge className="w-4 h-4" />
              Merge to Main
            </button>
          )}
        </div>
      </div>

      {/* Previous Work Queue Entries */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-orange-400" />
            Previous Work Queue & Change Reviews ({workLogs.length})
          </h3>
        </div>

        {workLogs.length === 0 ? (
          <div className="p-8 text-center text-xs text-slate-500 bg-slate-900/40 rounded-xl border border-slate-800">
            No work logs recorded yet for this ticket. Submit a prompt below to direct the coding agent!
          </div>
        ) : (
          workLogs.map((log) => {
            const isExpanded = !!expandedLogIds[log.id];

            return (
              <div
                key={log.id}
                className="rounded-xl bg-slate-900/80 border border-slate-800 overflow-hidden shadow-sm hover:border-slate-700 transition"
              >
                {/* Entry Header: Timestamp, Associated Ticket, Target Prompt, Summary */}
                <div
                  onClick={() => toggleLogExpand(log.id)}
                  className="p-4 flex items-start justify-between gap-4 cursor-pointer hover:bg-slate-800/40 transition select-none"
                >
                  <div className="flex items-start gap-3 min-w-0 flex-1">
                    <div className="p-2 rounded-lg bg-orange-500/10 text-orange-400 border border-orange-500/20 shrink-0 mt-0.5">
                      <FileCode className="w-4 h-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-mono text-[10px] font-bold px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
                          {ticket.jira_key}
                        </span>
                        <span className="text-[11px] text-slate-500 flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {new Date(log.timestamp).toLocaleString()}
                        </span>
                      </div>

                      <div className="text-xs font-semibold text-slate-200 mb-1">
                        Prompt: <span className="font-normal font-mono text-slate-300">{log.prompt_processed || log.prompt_raw}</span>
                      </div>

                      <p className="text-xs text-slate-400 leading-relaxed line-clamp-2">
                        {log.summary_changes || log.what_was_done}
                      </p>
                    </div>
                  </div>

                  <button
                    className="text-slate-400 hover:text-white p-1 rounded-md bg-slate-800/60"
                    title={isExpanded ? 'Collapse' : 'Expand'}
                  >
                    {isExpanded ? (
                      <ChevronUp className="w-4 h-4" />
                    ) : (
                      <ChevronDown className="w-4 h-4" />
                    )}
                  </button>
                </div>

                {/* Expanded Details: Short List of Changes Made + Button to View Full Work Log */}
                {isExpanded && (
                  <div className="px-5 pb-4 pt-2 bg-slate-950/60 border-t border-slate-800/80 space-y-3">
                    <div>
                      <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400 block mb-1.5">
                        Short List of Changes Made
                      </span>
                      <ul className="space-y-1 text-xs text-slate-300 list-disc pl-5">
                        {log.summary_changes?.split('.').filter(s => s.trim()).map((change, idx) => (
                          <li key={idx}>{change.trim()}.</li>
                        )) || <li>{log.what_was_done}</li>}
                      </ul>
                    </div>

                    {/* Button to view the entire work log entry */}
                    <div className="pt-2 flex items-center justify-between border-t border-slate-800/60">
                      <span className="text-[11px] text-slate-500 italic">
                        Includes AI defect breakdown, git diff, and user checklist.
                      </span>
                      <button
                        onClick={() => onSelectWorkLog(log.id)}
                        className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-orange-600 hover:bg-orange-500 text-white shadow-md flex items-center gap-1.5 cursor-pointer transition"
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                        See Entire Work Log Entry
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Review Queue Action: Direct AI Agent to make further changes */}
      {!isMerged && (
        <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
              <Terminal className="w-4 h-4 text-orange-400" />
              Direct Agent Further (Submit Prompt Update)
            </h4>
            <span className="text-[11px] text-slate-500">
              Spins container back up & continues work on branch
            </span>
          </div>

          <form onSubmit={handlePromptSubmit} className="space-y-3">
            <textarea
              rows={3}
              placeholder="e.g. Please refine the error handling in charge_service.py to log structured JSON instead of plain strings..."
              value={newPromptText}
              onChange={(e) => setNewPromptText(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-orange-500 font-mono"
            />

            <div className="flex justify-end">
              <button
                type="submit"
                disabled={!newPromptText.trim() || isSubmittingPrompt}
                className="px-4 py-2 rounded-xl text-xs font-bold bg-orange-600 hover:bg-orange-500 disabled:bg-slate-800 disabled:text-slate-500 text-white shadow-lg shadow-orange-600/20 flex items-center gap-2 transition cursor-pointer"
              >
                <Send className="w-3.5 h-3.5" />
                {isSubmittingPrompt ? 'Dispatching to Harness...' : 'Submit Prompt Update'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
