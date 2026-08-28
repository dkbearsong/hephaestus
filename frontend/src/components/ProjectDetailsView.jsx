import React, { useEffect, useState } from 'react';
import { FolderGit2, Save, RefreshCw, CheckCircle2, GitBranch, Terminal, Shield, Palette } from 'lucide-react';
import { api } from '../services/api';

export default function ProjectDetailsView({ projectId, onProjectUpdated }) {
  const [project, setProject] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Form State
  const [name, setName] = useState('');
  const [repoUrl, setRepoUrl] = useState('');
  const [jiraTicketKey, setJiraTicketKey] = useState('');
  const [systemPromptAdditions, setSystemPromptAdditions] = useState('');
  const [color, setColor] = useState('#3B82F6');

  const loadProject = () => {
    if (!projectId) return;
    setLoading(true);
    api.getProject(projectId)
      .then((data) => {
        setProject(data);
        setName(data.name || '');
        setRepoUrl(data.repo_url || '');
        setJiraTicketKey(data.jira_ticket_key || '');
        setSystemPromptAdditions(data.system_prompt_additions || '');
        setColor(data.color || '#3B82F6');
      })
      .catch((err) => console.error('Failed to load project:', err))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadProject();
  }, [projectId]);

  const handleSave = async (e) => {
    e.preventDefault();
    setIsSaving(true);
    setSaveSuccess(false);
    try {
      const updated = await api.updateProject(projectId, {
        name,
        repo_url: repoUrl,
        jira_ticket_key: jiraTicketKey,
        system_prompt_additions: systemPromptAdditions,
        color
      });
      setProject((prev) => ({ ...prev, ...updated }));
      setSaveSuccess(true);
      if (onProjectUpdated) onProjectUpdated();
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      console.error('Failed to save project:', err);
    } finally {
      setIsSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center text-slate-400 text-sm animate-pulse">
        Loading project details and synchronizing with Jira...
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex-1 flex items-center justify-center text-rose-400 text-sm">
        Project not found.
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col overflow-y-auto p-8 max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b border-slate-800">
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center shadow-lg"
            style={{ backgroundColor: `${color}25`, color: color, border: `1px solid ${color}55` }}
          >
            <FolderGit2 className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-bold text-slate-100">{project.name}</h2>
              <span className="font-mono text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                {project.key}
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Configured Docker Sandbox & Jira Synchronization
            </p>
          </div>
        </div>

        <button
          onClick={loadProject}
          title="Reload & Sync from Jira"
          className="p-2 rounded-lg bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-700 transition"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {/* Jira Live Sync Banner */}
      {project.jira_details && (
        <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 flex items-start justify-between gap-4 text-xs">
          <div>
            <span className="text-[10px] uppercase font-bold text-slate-500 block mb-1">
              Synchronized Jira Ticket Details
            </span>
            <div className="font-semibold text-slate-200 mb-0.5">
              [{project.jira_details.key}] {project.jira_details.summary}
            </div>
            <p className="text-slate-400 text-[11px] line-clamp-2">
              {project.jira_details.description || 'No description provided in Jira.'}
            </p>
          </div>
          <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-cyan-950 text-cyan-300 border border-cyan-800 shrink-0">
            Jira Status: {project.jira_details.status || 'Linked'}
          </span>
        </div>
      )}

      {/* Project Configuration Form */}
      <form onSubmit={handleSave} className="space-y-6">
        <div className="p-6 rounded-2xl bg-slate-900/70 border border-slate-800 space-y-4">
          <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider">
            General & Repository Settings
          </h3>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
            <div>
              <label className="block text-slate-400 font-semibold mb-1">Project Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-orange-500"
                required
              />
            </div>

            <div>
              <label className="block text-slate-400 font-semibold mb-1">
                Linked Jira Ticket Key (for sync)
              </label>
              <input
                type="text"
                value={jiraTicketKey}
                onChange={(e) => setJiraTicketKey(e.target.value)}
                placeholder="e.g. PAY-1"
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-orange-500 font-mono"
              />
            </div>

            <div className="md:col-span-2">
              <label className="block text-slate-400 font-semibold mb-1">Repository URL</label>
              <input
                type="text"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                placeholder="https://github.com/org/repo.git"
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-orange-500 font-mono"
              />
            </div>

            <div>
              <label className="block text-slate-400 font-semibold mb-1 flex items-center gap-1.5">
                <Palette className="w-3.5 h-3.5" />
                Project Font Color (for 5-min queue history)
              </label>
              <div className="flex items-center gap-3">
                <input
                  type="color"
                  value={color}
                  onChange={(e) => setColor(e.target.value)}
                  className="w-9 h-9 rounded-lg bg-transparent border-0 cursor-pointer"
                />
                <input
                  type="text"
                  value={color}
                  onChange={(e) => setColor(e.target.value)}
                  className="w-32 bg-slate-950 border border-slate-800 rounded-lg p-2 text-slate-200 font-mono text-xs uppercase"
                />
                <span className="text-xs font-bold font-mono" style={{ color }}>
                  Sample Text
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Per-Project Additional System Prompt */}
        <div className="p-6 rounded-2xl bg-slate-900/70 border border-slate-800 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
              <Terminal className="w-4 h-4 text-orange-400" />
              Per-Project System Prompt Instructions
            </h3>
          </div>

          <p className="text-xs text-slate-400 leading-relaxed">
            Specify additional system prompt instructions for this project. Use this so the AI coding
            agent tailors its output logs with specific information (e.g. security audits, formatting
            checklists, or regression requirements) when a request is completed.
          </p>

          <textarea
            rows={4}
            value={systemPromptAdditions}
            onChange={(e) => setSystemPromptAdditions(e.target.value)}
            placeholder="e.g. Ensure all payment tokens are masked. Always output a completion summary containing a PCI-DSS compliance verification checklist..."
            className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-xs text-slate-200 font-mono focus:outline-none focus:border-orange-500 leading-relaxed"
          />
        </div>

        {/* Save Actions */}
        <div className="flex items-center justify-between pt-2">
          {saveSuccess ? (
            <span className="text-xs font-semibold text-emerald-400 flex items-center gap-1.5 animate-in fade-in">
              <CheckCircle2 className="w-4 h-4" />
              Changes saved and pushed to Jira successfully!
            </span>
          ) : (
            <span className="text-xs text-slate-500">
              Saving pushes project updates directly to Jira Cloud.
            </span>
          )}

          <button
            type="submit"
            disabled={isSaving}
            className="px-6 py-2.5 rounded-xl text-xs font-bold bg-orange-600 hover:bg-orange-500 disabled:bg-slate-800 text-white shadow-lg shadow-orange-600/30 flex items-center gap-2 transition cursor-pointer"
          >
            <Save className="w-4 h-4" />
            {isSaving ? 'Saving & Pushing to Jira...' : 'Save & Push to Jira'}
          </button>
        </div>
      </form>
    </div>
  );
}
