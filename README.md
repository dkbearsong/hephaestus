# 🔥 Hephaestus: Automated Coding Agent Harness

Hephaestus is an autonomous coding agent harness and workflow system designed for pairing Jira Cloud issue tracking with branch-isolated Docker container sandboxes. It automatically listens for webhook comments containing `<|prompt|>` or `<|prompt-new|>`, extracts instructions and `<|files|>`, manages container workspaces, executes coding harnesses (Antigravity Headless Daemon + Remote Control or LangGraph), generates unified git diffs and review logs, and allows real-time user supervision through a React dashboard.

---

## 🚀 Key Features

1. **Jira Webhook Automation**:
   - Fires on tickets with label `ai-code` and comment prefix `<|prompt|>` or `<|prompt-new|>`.
   - Automatically removes the trigger label immediately to prevent re-triggering loops.
   - Updates Jira with completion label `ai-merged` and moves the ticket to Complete when merged.
2. **Prompt & File Preprocessor**:
   - Strips `<|prompt|>` and writes prompt to a persistent markdown file (`staging/{task_id}/prompt.md`).
   - Identifies `<|files|>` tag, stages local files, and rewrites the prompt markdown so references map to `/workspace/staged_files/...` inside the container.
3. **Branch-Isolated Docker Sandboxes**:
   - Inspects project and branch: re-attaches to existing branch container or initializes from parent base image.
   - Automatically initializes `git`, virtual environments (`.venv`), and installs dependencies.
   - Checkpoints containers into commit images (`hephaestus-checkpoint:...`) and spins them down when idle.
   - Complete teardown on merge: removes container and images permanently.
4. **Pluggable Coding Harness**:
   - Customizable via `user_preferences.yaml`.
   - **Antigravity Headless Daemon + Remote Control Harness**:
     - Autonomous execution within container sandbox.
     - Security boundary: pauses and alerts user if external network access outside allowlisted domains is required.
     - Pauses and asks user for clarification when needed.
   - **LangGraph Harness**:
     - Graph-based state machine with native human-in-the-loop checkpoints.
5. **Model Context Protocol (MCP) Support**:
   - Custom tools placed in `mcp_tools/` are dynamically registered and enabled via `user_preferences.yaml`.
   - Built-in tools: `postgres_inspector` and `test_runner`.
6. **PostgreSQL with Full-Text TSVector Search**:
   - Persistent storage for projects, branch tickets, work logs, unified diffs, chat messages, and notifications.
   - Automated triggers maintaining `tsvector` weighted documents with GIN indexes and ranked snippet search.
7. **Modern React 19 Dashboard (ExpressJS + WebSocket)**:
   - **Left Collapsible Sidebar**: Top 5 most recent actions, link to 5-minute windowed queue history, projects list with expand/collapse ticket history.
   - **Header**: Instant full-text search and **Agent Notifications Link**:
     - Periodically shaking **RED** icon if any requests are waiting on user approval.
     - **YELLOW** icon when review tasks are completed.
     - Click opens a scrollable popup to jump directly to the relevant ticket or chat.
   - **Review Queue**: Short change summaries, full log modal with unified git diff viewer, "Direct Agent Further" prompt updates, and "Merge to Main" confirmation modal.
   - **Queue History**: Chronological audit log grouped in 5-minute intervals under each project with dedicated font colors.
   - **Project Details**: Synchronized with Jira tickets, editable, with per-project system prompt additions.
   - **Interactive Chat**: Real-time channel to answer agent questions or approve external access requests.

---

## 🛠 Tech Stack

- **Python 3.12+**: `prefect` (3.x), `langgraph`, `fastapi`, `docker`, `jira`, `sqlalchemy`, `fastmcp`, `pydantic`.
- **PostgreSQL 16**: `tsvector` full-text search, GIN indexes, ranking, headline highlighting.
- **ExpressJS**: REST API Gateway, WebSocket server, Jira webhook intake.
- **React 19**: Vite, Tailwind CSS v4, Lucide React, unified diff viewer.

---

## 📦 Quickstart

### 1. Configure Environment
```bash
cp .env.example .env
# Edit .env with your PostgreSQL and Jira Cloud credentials
```

### 2. Configure Preferences
Edit `user_preferences.yaml` to specify the active harness, Docker images, and enabled MCP tools:
```yaml
harness:
  active: "antigravity_daemon"
jira:
  trigger_label: "ai-code"
mcp_tools:
  enabled:
    - "postgres_inspector"
    - "test_runner"
```

### 3. Initialize Database
```bash
createdb hephaestus
psql -d hephaestus -f backend/database/schema.sql
# Populate realistic seed data
PYTHONPATH=. .venv/bin/python backend/database/seed.py
```

### 4. Launch Services
```bash
./start.sh
```
- Open Dashboard: [http://localhost:3001](http://localhost:3001)
- Python Core API: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 🧪 Automated Testing
Run the complete end-to-end verification suite:
```bash
PYTHONPATH=. .venv/bin/python test_system.py
```
