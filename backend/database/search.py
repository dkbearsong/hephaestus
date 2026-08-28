from typing import List, Dict, Any, Optional
from sqlalchemy import text
from backend.database.connection import SessionLocal

def search_full_text(query_str: str, project_id: Optional[int] = None, limit: int = 20) -> Dict[str, Any]:
    """
    Performs full-text search using PostgreSQL tsvector over work_logs and chat_messages.
    Uses ts_rank_cd for relevance and ts_headline for highlighted snippets.
    """
    if not query_str or not query_str.strip():
        return {"work_logs": [], "chat_messages": []}

    cleaned_query = query_str.strip()
    session = SessionLocal()
    try:
        # Search work logs
        log_filter = "AND w.project_id = :project_id" if project_id else ""
        work_logs_sql = text(f"""
            SELECT 
                w.id,
                w.ticket_id,
                w.project_id,
                p.name as project_name,
                p.color as project_color,
                t.jira_key,
                w.timestamp,
                w.status,
                w.summary_changes,
                w.what_was_done,
                w.what_was_wrong,
                ts_rank_cd(w.tsv, plainto_tsquery('english', :query)) as rank,
                ts_headline('english', coalesce(w.what_was_done, '') || ' ' || coalesce(w.summary_changes, ''), plainto_tsquery('english', :query), 'StartSel=<mark>, StopSel=</mark>, MaxWords=35, MinWords=15') as headline
            FROM work_logs w
            JOIN projects p ON w.project_id = p.id
            JOIN tickets t ON w.ticket_id = t.id
            WHERE w.tsv @@ plainto_tsquery('english', :query) {log_filter}
            ORDER BY rank DESC, w.timestamp DESC
            LIMIT :limit;
        """)

        params = {"query": cleaned_query, "limit": limit}
        if project_id:
            params["project_id"] = project_id

        log_rows = session.execute(work_logs_sql, params).mappings().all()
        work_logs = [dict(row) for row in log_rows]

        # Search chat messages
        chat_filter = "AND c.project_id = :project_id" if project_id else ""
        chat_sql = text(f"""
            SELECT 
                c.id,
                c.ticket_id,
                c.project_id,
                p.name as project_name,
                p.color as project_color,
                t.jira_key,
                c.sender,
                c.message_type,
                c.content,
                c.created_at,
                ts_rank_cd(c.tsv, plainto_tsquery('english', :query)) as rank,
                ts_headline('english', c.content, plainto_tsquery('english', :query), 'StartSel=<mark>, StopSel=</mark>, MaxWords=35, MinWords=15') as headline
            FROM chat_messages c
            JOIN projects p ON c.project_id = p.id
            JOIN tickets t ON c.ticket_id = t.id
            WHERE c.tsv @@ plainto_tsquery('english', :query) {chat_filter}
            ORDER BY rank DESC, c.created_at DESC
            LIMIT :limit;
        """)

        chat_rows = session.execute(chat_sql, params).mappings().all()
        chat_messages = [dict(row) for row in chat_rows]

        return {
            "query": cleaned_query,
            "total_matches": len(work_logs) + len(chat_messages),
            "work_logs": work_logs,
            "chat_messages": chat_messages
        }
    finally:
        session.close()
