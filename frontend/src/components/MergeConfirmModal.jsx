import React, { useState } from 'react';
import { AlertTriangle, GitMerge, Trash2, CheckCircle2, X } from 'lucide-react';

export default function MergeConfirmModal({ ticket, isOpen, onClose, onConfirmMerge }) {
  const [confirmed, setConfirmed] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!isOpen || !ticket) return null;

  const handleMerge = async () => {
    setIsSubmitting(true);
    try {
      await onConfirmMerge(ticket.id);
      onClose();
    } catch (e) {
      console.error('Merge failed:', e);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="px-6 py-4 bg-slate-800/80 border-b border-slate-700 flex items-center justify-between">
          <div className="flex items-center gap-2.5 text-orange-400">
            <GitMerge className="w-5 h-5" />
            <h3 className="font-bold text-slate-100 text-sm md:text-base">
              Confirm Branch Merge to Main
            </h3>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-4 text-xs text-slate-300">
          <p>
            You are about to merge branch{' '}
            <code className="px-1.5 py-0.5 rounded bg-slate-800 text-orange-300 font-mono">
              {ticket.branch_name}
            </code>{' '}
            associated with Jira ticket{' '}
            <strong className="text-slate-100">{ticket.jira_key}</strong> into main.
          </p>

          <div className="p-3.5 rounded-xl bg-amber-950/30 border border-amber-800/60 space-y-2 text-amber-200">
            <div className="font-semibold flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
              Automated Teardown & Jira Push
            </div>
            <ul className="space-y-1 text-[11px] text-amber-300/90 list-disc pl-5">
              <li>
                The branch Docker container{' '}
                <span className="font-mono">{ticket.container_id || 'active container'}</span> will be permanently deleted.
              </li>
              <li>Local checkpointed images will be cleaned up and pruned.</li>
              <li>
                Jira ticket <strong>{ticket.jira_key}</strong> will be updated with label{' '}
                <code>ai-merged</code> and transitioned to <strong>Complete / Done</strong>.
              </li>
            </ul>
          </div>

          <label className="flex items-center gap-2.5 p-3 rounded-lg bg-slate-950 border border-slate-800 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
              className="w-4 h-4 accent-orange-500 rounded cursor-pointer"
            />
            <span className="text-slate-200 font-medium">
              I have reviewed the work logs and diff, and approve merging to main.
            </span>
          </label>
        </div>

        {/* Footer */}
        <div className="px-6 py-3 bg-slate-800/60 border-t border-slate-800 flex justify-end gap-2.5">
          <button
            onClick={onClose}
            disabled={isSubmitting}
            className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold"
          >
            Cancel
          </button>
          <button
            onClick={handleMerge}
            disabled={!confirmed || isSubmitting}
            className={`px-4 py-2 rounded-lg font-semibold flex items-center gap-2 transition ${
              confirmed && !isSubmitting
                ? 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-600/30 cursor-pointer'
                : 'bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700'
            }`}
          >
            <GitMerge className="w-4 h-4" />
            {isSubmitting ? 'Merging & Pruning...' : 'Finalize Git Merge'}
          </button>
        </div>
      </div>
    </div>
  );
}
