import React from 'react';
import { AlertTriangle, CheckCircle2, XCircle, ArrowRight, ShieldAlert, Clock } from 'lucide-react';

export default function NotificationPopup({
  notifications,
  isOpen,
  onClose,
  onSelectTicket,
  onRespond
}) {
  if (!isOpen) return null;

  return (
    <div className="absolute right-0 top-12 w-96 max-h-[500px] bg-slate-900 border border-slate-700 rounded-xl shadow-2xl z-50 flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
      <div className="px-4 py-3 bg-slate-800/80 border-b border-slate-700/80 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-sm text-slate-100">Agent Notifications</span>
          <span className="px-2 py-0.5 text-xs font-bold rounded-full bg-slate-700 text-slate-300">
            {notifications.length}
          </span>
        </div>
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-slate-200 text-xs px-2 py-1 rounded bg-slate-800 hover:bg-slate-700"
        >
          Close
        </button>
      </div>

      <div className="overflow-y-auto p-3 space-y-2.5 max-h-[420px]">
        {notifications.length === 0 ? (
          <div className="py-8 text-center text-slate-400 text-xs">
            No active agent notifications pending.
          </div>
        ) : (
          notifications.map((notif) => {
            const isNeedsInput = notif.type === 'needs_input';
            const isCompleted = notif.type === 'completed';

            return (
              <div
                key={notif.id}
                className={`p-3 rounded-lg border text-xs transition-all ${
                  isNeedsInput
                    ? 'bg-rose-950/40 border-rose-800/60 hover:border-rose-600'
                    : 'bg-amber-950/30 border-amber-800/50 hover:border-amber-600'
                }`}
              >
                <div className="flex items-start gap-2.5">
                  {isNeedsInput ? (
                    <div className="p-1.5 rounded-md bg-rose-900/60 text-rose-400 shrink-0 mt-0.5">
                      <ShieldAlert className="w-4 h-4 text-rose-400 animate-pulse" />
                    </div>
                  ) : (
                    <div className="p-1.5 rounded-md bg-amber-900/60 text-amber-400 shrink-0 mt-0.5">
                      <CheckCircle2 className="w-4 h-4 text-amber-400" />
                    </div>
                  )}

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-1 mb-1">
                      <span className={`font-semibold truncate ${isNeedsInput ? 'text-rose-200' : 'text-amber-200'}`}>
                        {notif.title}
                      </span>
                      <span className="text-[10px] text-slate-500 shrink-0 flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {new Date(notif.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>

                    <p className="text-slate-300 text-[11px] leading-relaxed mb-2.5 line-clamp-3">
                      {notif.message}
                    </p>

                    <div className="flex items-center justify-between pt-1 border-t border-slate-800/80">
                      <button
                        onClick={() => {
                          onSelectTicket(notif.ticket_id);
                          onClose();
                        }}
                        className="inline-flex items-center gap-1 text-[11px] font-medium text-orange-400 hover:text-orange-300"
                      >
                        Go to Ticket & Chat <ArrowRight className="w-3 h-3" />
                      </button>

                      {isNeedsInput && (
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => onRespond(notif.id, 'approve')}
                            className="px-2 py-0.5 text-[10px] font-medium bg-emerald-700 hover:bg-emerald-600 text-white rounded"
                          >
                            Approve
                          </button>
                          <button
                            onClick={() => onRespond(notif.id, 'deny')}
                            className="px-2 py-0.5 text-[10px] font-medium bg-slate-800 hover:bg-slate-700 text-rose-300 rounded border border-slate-700"
                          >
                            Deny
                          </button>
                        </div>
                      )}

                      {isCompleted && (
                        <button
                          onClick={() => onRespond(notif.id, 'dismiss')}
                          className="px-2 py-0.5 text-[10px] font-medium bg-slate-800 hover:bg-slate-700 text-slate-300 rounded border border-slate-700"
                        >
                          Dismiss
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
