-- Hephaestus PostgreSQL Schema
-- Supports projects, branch-isolated tickets/containers, work logs, diffs, chat, notifications, and full-text search via tsvector.

-- Enable pg_trgm for fuzzy search if needed
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Projects Table
CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    key VARCHAR(50) NOT NULL UNIQUE,
    jira_key VARCHAR(50),
    jira_ticket_key VARCHAR(50),
    repo_url TEXT,
    base_image VARCHAR(255) DEFAULT 'python:3.12-slim',
    system_prompt_additions TEXT DEFAULT '',
    color VARCHAR(30) DEFAULT '#3B82F6',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tickets Table (Mapped to Jira Tickets & Git Branches)
CREATE TABLE IF NOT EXISTS tickets (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    jira_key VARCHAR(50) NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    branch_name VARCHAR(255),
    container_id VARCHAR(255),
    image_id VARCHAR(255),
    status VARCHAR(50) DEFAULT 'pending', -- pending, in_progress, paused_waiting_input, review_ready, merged, failed
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_ticket_project_jira UNIQUE(project_id, jira_key)
);

-- Work Logs Table (Tracks prompt execution, changes, git diff, and review)
CREATE TABLE IF NOT EXISTS work_logs (
    id SERIAL PRIMARY KEY,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    prompt_raw TEXT NOT NULL,
    prompt_processed TEXT NOT NULL,
    staged_files JSONB DEFAULT '[]'::jsonb,
    status VARCHAR(50) DEFAULT 'completed', -- in_progress, paused_waiting_input, completed, failed
    summary_changes TEXT,
    what_was_wrong TEXT,
    what_was_done TEXT,
    user_check_items JSONB DEFAULT '[]'::jsonb,
    git_diff TEXT,
    full_log TEXT,
    tsv TSVECTOR
);

-- Chat Messages Table (Human-in-the-loop Q&A and approvals)
CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    sender VARCHAR(50) NOT NULL, -- user, agent, system
    message_type VARCHAR(50) DEFAULT 'question', -- question, answer, notification, approval_request, log
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    status VARCHAR(50) DEFAULT 'pending', -- pending, answered, acknowledged
    created_at TIMESTAMPTZ DEFAULT NOW(),
    tsv TSVECTOR
);

-- Agent Notifications Table (Red shaking icon for input required, Yellow for completion)
CREATE TABLE IF NOT EXISTS agent_notifications (
    id SERIAL PRIMARY KEY,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL, -- needs_input (red), completed (yellow), failed (dispatch aborted), info
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    status VARCHAR(50) DEFAULT 'pending', -- pending, approved, denied, resolved
    action_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

-- TSVector Update Trigger Function for work_logs
CREATE OR REPLACE FUNCTION work_logs_tsv_trigger() RETURNS trigger AS $$
BEGIN
  NEW.tsv :=
    setweight(to_tsvector('english', coalesce(NEW.summary_changes, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(NEW.what_was_done, '')), 'B') ||
    setweight(to_tsvector('english', coalesce(NEW.what_was_wrong, '')), 'B') ||
    setweight(to_tsvector('english', coalesce(NEW.prompt_processed, '')), 'C') ||
    setweight(to_tsvector('english', coalesce(NEW.git_diff, '')), 'D');
  RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_work_logs_tsv ON work_logs;
CREATE TRIGGER trg_work_logs_tsv
BEFORE INSERT OR UPDATE ON work_logs
FOR EACH ROW EXECUTE FUNCTION work_logs_tsv_trigger();

-- TSVector Update Trigger Function for chat_messages
CREATE OR REPLACE FUNCTION chat_messages_tsv_trigger() RETURNS trigger AS $$
BEGIN
  NEW.tsv :=
    setweight(to_tsvector('english', coalesce(NEW.content, '')), 'A');
  RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_chat_messages_tsv ON chat_messages;
CREATE TRIGGER trg_chat_messages_tsv
BEFORE INSERT OR UPDATE ON chat_messages
FOR EACH ROW EXECUTE FUNCTION chat_messages_tsv_trigger();

-- GIN Indexes for Fast Full-Text Search
CREATE INDEX IF NOT EXISTS idx_work_logs_tsv ON work_logs USING GIN(tsv);
CREATE INDEX IF NOT EXISTS idx_chat_messages_tsv ON chat_messages USING GIN(tsv);
CREATE INDEX IF NOT EXISTS idx_work_logs_timestamp ON work_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_agent_notifs_status ON agent_notifications(status, type);
