import React, { useState, useEffect, useRef } from 'react';
import { api } from '../services/api';
import { Terminal, Database, Code, CheckCircle, XCircle } from 'lucide-react';

export default function RunDetails({ runId, onBack }) {
  const [run, setRun] = useState(null);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const eventEndRef = useRef(null);

  useEffect(() => {
    const fetchRunData = async () => {
      try {
        const runData = await api.getRun(runId);
        setRun(runData);
        const eventsData = await api.getRunEvents(runId);
        setEvents(eventsData);
      } catch (e) {
        console.error('Error fetching run details:', e);
      } finally {
        setLoading(false);
      }
    };

    fetchRunData();

    // Connect to SSE Stream
    const protocol = window.location.protocol === 'https:' ? 'https:' : 'http:';
    const baseUrl = `${protocol}//${window.location.host}/api`;
    const evtSource = new EventSource(`${baseUrl}/runs/${runId}/stream`);

    evtSource.onmessage = function(event) {
      try {
        const newEvent = JSON.parse(event.data);
        setEvents(prev => {
          // simple dedup by id
          if (prev.some(e => e.id === newEvent.id)) return prev;
          return [...prev, newEvent].sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
        });
      } catch (err) {
        console.error('Error parsing SSE event:', err);
      }
    };

    return () => {
      evtSource.close();
    };
  }, [runId]);

  useEffect(() => {
    eventEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events]);

  if (loading) return <div className="p-8 flex items-center justify-center h-full text-slate-400">Loading details...</div>;
  if (!run) return <div className="p-8 text-red-400">Run not found.</div>;

  return (
    <div className="flex flex-col h-full bg-slate-900 text-slate-200">
      <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-950">
        <div className="flex items-center gap-4">
          <button onClick={onBack} className="text-slate-400 hover:text-white px-3 py-1 rounded bg-slate-800">&larr; Back</button>
          <h2 className="text-xl font-bold font-mono text-blue-400">{run.jira_key || 'UNKNOWN'}</h2>
          <span className={`px-2 py-1 text-xs rounded-full font-bold ${
            run.status === 'COMPLETED' ? 'bg-green-900/50 text-green-400' :
            run.status === 'FAILED' ? 'bg-red-900/50 text-red-400' :
            run.status === 'QUEUED' ? 'bg-slate-700 text-slate-300' :
            'bg-blue-900/50 text-blue-400'
          }`}>
            {run.status}
          </span>
        </div>
        <div className="text-sm text-slate-500">
          Platform: <span className="text-slate-300 mr-4">{run.target_platform}</span>
          Branch: <span className="text-slate-300 font-mono">{run.branch_name || 'N/A'}</span>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Main Event Stream */}
        <div className="flex-1 p-4 overflow-y-auto flex flex-col gap-3 font-mono text-sm">
          {events.length === 0 ? (
            <div className="text-slate-600 text-center mt-10">No events recorded yet.</div>
          ) : (
            events.map((evt, idx) => (
              <div key={evt.id || idx} className="bg-slate-950 border border-slate-800 p-3 rounded flex flex-col gap-2">
                <div className="flex items-center justify-between text-xs text-slate-500">
                  <span className="flex items-center gap-2 text-slate-400 font-semibold">
                    {evt.event_type === 'MCP_TOOL_CALL' ? <Database size={14} className="text-purple-400"/> :
                     evt.event_type === 'DOCKER_STDOUT' ? <Terminal size={14} className="text-green-400"/> :
                     <Code size={14} className="text-blue-400"/>}
                    {evt.event_type}
                  </span>
                  <span>{new Date(evt.timestamp).toLocaleTimeString()}</span>
                </div>
                {evt.payload && (
                  <pre className="bg-black/50 p-2 rounded text-slate-300 whitespace-pre-wrap overflow-x-auto text-xs border border-slate-800/50">
                    {typeof evt.payload === 'object' ? JSON.stringify(evt.payload, null, 2) : evt.payload}
                  </pre>
                )}
              </div>
            ))
          )}
          <div ref={eventEndRef} />
        </div>

        {/* Sidebar details */}
        <div className="w-80 border-l border-slate-800 bg-slate-950 p-4 flex flex-col gap-6 overflow-y-auto">
          {run.prep_summary && (
            <div>
              <h3 className="text-sm font-bold text-slate-400 mb-2 uppercase tracking-wider">Preparation Summary</h3>
              <div className="bg-slate-900 border border-slate-800 rounded p-3 text-sm">
                <ul className="space-y-2">
                  <li className="flex items-start gap-2">
                    <CheckCircle size={14} className="text-green-500 mt-1 shrink-0" />
                    <span>Test Command: <br/><code className="text-slate-400 text-xs">{run.prep_summary.test_command || 'None'}</code></span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle size={14} className="text-green-500 mt-1 shrink-0" />
                    <span>Build Command: <br/><code className="text-slate-400 text-xs">{run.prep_summary.build_command || 'None'}</code></span>
                  </li>
                </ul>
              </div>
            </div>
          )}

          {run.error_message && (
            <div>
              <h3 className="text-sm font-bold text-red-400 mb-2 uppercase tracking-wider flex items-center gap-2"><XCircle size={14}/> Error</h3>
              <div className="bg-red-950/20 border border-red-900/50 text-red-200 rounded p-3 text-xs whitespace-pre-wrap font-mono">
                {run.error_message}
              </div>
            </div>
          )}

          {run.metrics && (
             <div>
               <h3 className="text-sm font-bold text-slate-400 mb-2 uppercase tracking-wider">Execution Metrics</h3>
               <pre className="text-xs bg-slate-900 p-3 rounded border border-slate-800 text-blue-300 overflow-x-auto">
                 {JSON.stringify(run.metrics, null, 2)}
               </pre>
             </div>
          )}
        </div>
      </div>
    </div>
  );
}
