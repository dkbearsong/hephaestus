import React from 'react';

export default function DiffViewer({ diffText }) {
  if (!diffText || !diffText.trim()) {
    return (
      <div className="p-4 text-center text-xs text-slate-500 font-mono italic">
        No git diff available for this change.
      </div>
    );
  }

  const lines = diffText.split('\n');

  return (
    <div className="bg-slate-950 rounded-lg border border-slate-800 font-mono text-xs overflow-x-auto shadow-inner">
      <div className="px-4 py-2 bg-slate-900 border-b border-slate-800 flex items-center justify-between text-slate-400">
        <span className="font-semibold text-slate-300">Unified Git Diff</span>
        <span className="text-[11px] text-slate-500">{lines.length} lines</span>
      </div>
      <pre className="p-3 leading-relaxed">
        {lines.map((line, idx) => {
          let lineClass = 'text-slate-300';
          let bgClass = 'transparent';

          if (line.startsWith('diff --git') || line.startsWith('index ')) {
            lineClass = 'text-purple-400 font-semibold';
            bgClass = 'rgba(168, 85, 247, 0.08)';
          } else if (line.startsWith('--- ') || line.startsWith('+++ ')) {
            lineClass = 'text-slate-400 font-medium';
          } else if (line.startsWith('@@')) {
            lineClass = 'text-cyan-400 font-semibold';
            bgClass = 'rgba(6, 182, 212, 0.1)';
          } else if (line.startsWith('+')) {
            lineClass = 'text-emerald-400';
            bgClass = 'rgba(16, 185, 129, 0.12)';
          } else if (line.startsWith('-')) {
            lineClass = 'text-rose-400';
            bgClass = 'rgba(244, 63, 94, 0.12)';
          }

          return (
            <div
              key={idx}
              className="flex items-start px-2 py-0.5 rounded-sm hover:brightness-125"
              style={{ backgroundColor: bgClass }}
            >
              <span className="w-8 select-none text-slate-600 text-right pr-3 shrink-0">
                {idx + 1}
              </span>
              <span className={`${lineClass} whitespace-pre-wrap break-all flex-1`}>
                {line || ' '}
              </span>
            </div>
          );
        })}
      </pre>
    </div>
  );
}
