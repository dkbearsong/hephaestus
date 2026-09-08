import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import RunDetails from './RunDetails';

export default function RunDashboard() {
  const [runs, setRuns] = useState([]);
  const [stats, setStats] = useState(null);
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchDashboardData = async () => {
    setLoading(true);
    try {
      const runsData = await api.getRuns();
      setRuns(runsData);
      const statsData = await api.getStats();
      setStats(statsData);
    } catch (e) {
      console.error('Error fetching dashboard data:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
  }, []);

  if (selectedRunId) {
    return <RunDetails runId={selectedRunId} onBack={() => setSelectedRunId(null)} />;
  }

  return (
    <div className="p-6 h-full flex flex-col bg-slate-900 text-slate-100 overflow-y-auto">
      <h1 className="text-2xl font-bold mb-4">Coding Agent Runs Dashboard</h1>

      {stats && (
        <div className="flex gap-4 mb-8">
          <div className="bg-slate-800 p-4 rounded-lg shadow border border-slate-700 flex-1">
            <h3 className="text-slate-400 text-sm font-semibold uppercase">Total Runs</h3>
            <p className="text-3xl font-bold mt-2">{stats.total_runs}</p>
          </div>
          <div className="bg-slate-800 p-4 rounded-lg shadow border border-slate-700 flex-1">
            <h3 className="text-slate-400 text-sm font-semibold uppercase">Success Rate</h3>
            <p className="text-3xl font-bold mt-2">{stats.success_rate?.toFixed(1)}%</p>
          </div>
        </div>
      )}

      <div className="bg-slate-800 rounded-lg shadow border border-slate-700 overflow-hidden flex-1 flex flex-col">
        <table className="w-full text-left">
          <thead className="bg-slate-900 border-b border-slate-700">
            <tr>
              <th className="p-3 font-semibold text-slate-300">Jira Key</th>
              <th className="p-3 font-semibold text-slate-300">Status</th>
              <th className="p-3 font-semibold text-slate-300">Target Platform</th>
              <th className="p-3 font-semibold text-slate-300">Created At</th>
              <th className="p-3 font-semibold text-slate-300 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700 overflow-y-auto">
            {loading ? (
              <tr><td colSpan="5" className="p-4 text-center">Loading runs...</td></tr>
            ) : runs.length === 0 ? (
              <tr><td colSpan="5" className="p-4 text-center text-slate-500">No runs found.</td></tr>
            ) : (
              runs.map(run => (
                <tr key={run.id} className="hover:bg-slate-750 transition-colors">
                  <td className="p-3 font-mono">{run.jira_key || 'N/A'}</td>
                  <td className="p-3">
                    <span className={`px-2 py-1 text-xs rounded-full ${
                      run.status === 'COMPLETED' ? 'bg-green-900/50 text-green-400' :
                      run.status === 'FAILED' ? 'bg-red-900/50 text-red-400' :
                      run.status === 'QUEUED' ? 'bg-slate-700 text-slate-300' :
                      'bg-blue-900/50 text-blue-400'
                    }`}>
                      {run.status}
                    </span>
                  </td>
                  <td className="p-3">{run.target_platform || 'N/A'}</td>
                  <td className="p-3 text-sm text-slate-400">{new Date(run.created_at).toLocaleString()}</td>
                  <td className="p-3 text-right">
                    <button
                      onClick={() => setSelectedRunId(run.id)}
                      className="text-blue-400 hover:text-blue-300 text-sm font-medium"
                    >
                      View Details &rarr;
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
