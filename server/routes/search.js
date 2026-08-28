import express from 'express';
import { pool } from '../db.js';

const router = express.Router();

/**
 * Full-Text Search via PostgreSQL tsvector and GIN indexes
 * Searches across work logs, diffs, AI changes, and chat history.
 */
router.get('/', async (req, res) => {
  try {
    const { q, project_id } = req.query;

    if (!q || !q.trim()) {
      return res.json({ work_logs: [], chat_messages: [], total_matches: 0 });
    }

    const queryStr = q.trim();
    const projectIdFilter = project_id ? parseInt(project_id) : null;

    // Search Work Logs
    const workLogsSql = `
      SELECT 
        w.id,
        w.ticket_id,
        w.project_id,
        p.name as project_name,
        p.color as project_color,
        t.jira_key,
        t.title as ticket_title,
        w.timestamp,
        w.status,
        w.summary_changes,
        w.what_was_done,
        w.what_was_wrong,
        ts_rank_cd(w.tsv, plainto_tsquery('english', $1)) as rank,
        ts_headline('english', coalesce(w.what_was_done, '') || ' ' || coalesce(w.summary_changes, ''), plainto_tsquery('english', $1), 'StartSel=<mark>, StopSel=</mark>, MaxWords=35, MinWords=15') as headline
      FROM work_logs w
      JOIN projects p ON w.project_id = p.id
      JOIN tickets t ON w.ticket_id = t.id
      WHERE w.tsv @@ plainto_tsquery('english', $1)
      ${projectIdFilter ? 'AND w.project_id = $2' : ''}
      ORDER BY rank DESC, w.timestamp DESC
      LIMIT 25;
    `;

    const logParams = projectIdFilter ? [queryStr, projectIdFilter] : [queryStr];
    const logRes = await pool.query(workLogsSql, logParams);

    // Search Chat Messages
    const chatSql = `
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
        ts_rank_cd(c.tsv, plainto_tsquery('english', $1)) as rank,
        ts_headline('english', c.content, plainto_tsquery('english', $1), 'StartSel=<mark>, StopSel=</mark>, MaxWords=35, MinWords=15') as headline
      FROM chat_messages c
      JOIN projects p ON c.project_id = p.id
      JOIN tickets t ON c.ticket_id = t.id
      WHERE c.tsv @@ plainto_tsquery('english', $1)
      ${projectIdFilter ? 'AND c.project_id = $2' : ''}
      ORDER BY rank DESC, c.created_at DESC
      LIMIT 25;
    `;

    const chatParams = projectIdFilter ? [queryStr, projectIdFilter] : [queryStr];
    const chatRes = await pool.query(chatSql, chatParams);

    res.json({
      query: queryStr,
      total_matches: logRes.rows.length + chatRes.rows.length,
      work_logs: logRes.rows,
      chat_messages: chatRes.rows
    });
  } catch (err) {
    console.error('Error executing full-text search:', err);
    res.status(500).json({ error: err.message });
  }
});

export default router;
