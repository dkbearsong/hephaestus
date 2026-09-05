# 🔥 Hephaestus: Automated Coding Agent Orchestrator

Hephaestus is an autonomous coding agent harness and workflow system designed for pairing Jira Cloud issue tracking with specialized containerized coding agent environments. It automatically listens for webhook comments containing `<|prompt|>` or `<|prompt-new|>`, extracts instructions and `<|files|>`, runs multi-provider Preparations (via LangGraph with MCP tools), dispatches tasks to pluggable **Coding Agent Orchestrators** (Google Jules, Grok Build, OpenAI Codex Cloud, Docker Sandbox Claude/Codex, Devin AI, OpenHands Agent Canvas, Cursor), generates unified git diffs and review logs, and enables real-time user supervision through a React dashboard.

---

## 🚀 Key Features

1. **Jira Webhook Automation**:
   - Fires on tickets with label `run_ai_orchestrator` and comment prefix `<|prompt|>` or `<|prompt-new|>`.
   - Automatically removes the trigger label immediately to prevent re-triggering loops.
   - Updates Jira with completion label `ai-merged` and moves the ticket to Complete when merged.
2. **Prompt & File Preprocessor**:
   - Strips `<|prompt|>` and writes prompt to a persistent markdown file (`staging/{task_id}/prompt.md`).
   - Identifies `<|files|>` tag, stages local files, and rewrites the prompt markdown so references map to `/workspace/staged_files/...` inside the container.
3. **Multi-Platform Coding Agent Orchestrator**:
   - **Google Jules**: Asynchronous coding agent with Google Cloud Workspace containers.
   - **Grok Build**: xAI autonomous build agent with isolated containerized build environments.
   - **OpenAI Codex (Cloud)**: OpenAI cloud-sandboxed execution container with multi-turn code generation.
   - **Docker Sandbox with Claude Code or OpenAI Codex**: Isolated Docker container sandbox running Claude Code CLI / Codex.
   - **Devin AI**: Cognition Devin AI autonomous engineer cloud sandbox session container.
   - **OpenHands with Agent Canvas**: OpenHands container runtime with visual Agent Canvas flow.
   - **Cursor (Cloud Agents & Dev Containers)**: Cursor Cloud background agents and containerized execution using the Cursor Dev Containers extension with `.devcontainer/devcontainer.json`.
4. **LangGraph Preparations Step with MCP Support**:
   - Executes immediately before coding agent dispatch across 10 LLM providers.
   - Dynamic MCP tool integration: `datetime_tool`, `postgres_inspector`, and `test_runner`.
   - Confirms completion with End-of-Token before handing off to the coding agent.
5. **PostgreSQL with Full-Text TSVector Search**:
   - Persistent storage for projects, branch tickets, work logs, unified diffs, chat messages, and notifications.
   - Automated triggers maintaining `tsvector` weighted documents with GIN indexes and ranked snippet search.
6. **Modern React 19 Dashboard (ExpressJS + WebSocket)**:
   - **Left Collapsible Sidebar**: Top 5 most recent actions, link to 5-minute windowed queue history, projects list with expand/collapse ticket history.
   - **Header**: Instant full-text search and **Agent Notifications Link** (Red for input, Yellow for review ready).
   - **Review Queue**: Short change summaries, full log modal with unified git diff viewer, and "Merge to Main" confirmation.

---

## 📦 Quickstart

### 1. Configure Preferences
Edit `user_preferences.yaml` to specify the active coding agent platform:
```yaml
harness:
  active: "google_jules" # 'google_jules' | 'grok_build' | 'openai_codex_cloud' | 'docker_sandbox_claude_codex' | 'devin_ai' | 'openhands_canvas' | 'cursor_agent'
```

### 2. Run Automated Verification
Run the complete end-to-end test suite across all 8 subsystems:
```bash
PYTHONPATH=. .venv/bin/python test_system.py
```

### 3. Test Coding Agent Orchestrators
Run mock data tests across all 7 coding agents:
```bash
PYTHONPATH=. .venv/bin/python test_coding_agents.py --all
```

### 4. Run Manual Jira Webhook Test
Trigger a manual test with a simulated or live Jira webhook payload:
```bash
PYTHONPATH=. .venv/bin/python test_coding_agents.py --jira-manual --agent google_jules --key PAY-101
PYTHONPATH=. .venv/bin/python test_coding_agents.py --jira-manual --agent cursor_cloud --key CUR-101
PYTHONPATH=. .venv/bin/python test_coding_agents.py --jira-manual --agent cursor_dev_container --key CUR-202
PYTHONPATH=. .venv/bin/python test_coding_agents.py --jira-manual --agent openhands_canvas --key DEV-303
```
Or launch the interactive test console:
```bash
PYTHONPATH=. .venv/bin/python test_coding_agents.py --interactive
```

---

## 🗂 Legacy Code Archive
The legacy Docker container manager and container injection scripts have been archived in [`old_code/`](old_code/README.md).
