import express from 'express';
import { pool } from '../db.js';

const router = express.Router();

// 5 Most Recent Actions (for top of left column)
router.get('/recent', async (req, res) => {
  try {
    const query = `
      SELECT 
        w.id,
        w.ticket_id,
        w.project_id,
        w.timestamp,
        w.status,
        w.summary_changes,
        w.prompt_processed,
        t.jira_key,
        t.title as ticket_title,
        p.name as project_name,
        p.key as project_key,
        p.color as project_color
      FROM work_logs w
      JOIN tickets t ON w.ticket_id = t.id
      JOIN projects p ON w.project_id = p.id
      ORDER BY w.timestamp DESC
      LIMIT 5;
    `;
    const { rows } = await pool.query(query);
    res.json(rows);
  } catch (err) {
    console.error('Error fetching recent actions:', err);
    res.status(500).json({ error: err.message });
  }
});

// Entire Queue History grouped in 5-minute chronological windows under their project
router.get('/queue-history', async (req, res) => {
  try {
    const query = `
      SELECT 
        w.id,
        w.ticket_id,
        w.project_id,
        w.timestamp,
        w.status,
        w.summary_changes,
        w.what_was_wrong,
        w.what_was_done,
        w.prompt_processed,
        t.jira_key,
        t.title as ticket_title,
        t.branch_name,
        p.name as project_name,
        p.key as project_key,
        p.color as project_color
      FROM work_logs w
      JOIN tickets t ON w.ticket_id = t.id
      JOIN projects p ON w.project_id = p.id
      ORDER BY w.timestamp DESC;
    `;
    const { rows } = await pool.query(query);

    // Grouping algorithm: 5-minute chronological windows
    const WINDOW_MS = 5 * 60 * 1000;
    const windows = [];
    let currentWindow = null;

    for (const log of rows) {
      const logTime = new Date(log.timestamp).getTime();
      
      // Calculate bucket start (rounded down to 5-minute interval)
      const windowStart = new Date(Math.floor(logTime / WINDOW_MS) * WINDOW_MS);
      const windowEnd = new Date(windowStart.getTime() + WINDOW_MS);
      const windowKey = windowStart.toISOString();

      if (!currentWindow || currentWindow.key !== windowKey) {
        currentWindow = {
          key: windowKey,
          window_start: windowStart.toISOString(),
          window_end: windowEnd.toISOString(),
          projects: {} // grouped under their project
        };
        windows.push(currentWindow);
      }

      const pKey = log.project_key;
      if (!currentWindow.projects[pKey]) {
        currentWindow.projects[pKey] = {
          project_id: log.project_id,
          project_name: log.project_name,
          project_key: log.project_key,
          project_color: log.project_color || '#3B82F6',
          items: []
        };
      }

      currentWindow.projects[pKey].items.push(log);
    }

    // Convert projects map to array for easy frontend consumption
    const formattedWindows = windows.map(w => ({
      key: w.key,
      window_start: w.window_start,
      window_end: w.window_end,
      projects: Object.values(w.projects)
    }));

    res.json(formattedWindows);
  } catch (err) {
    console.error('Error calculating queue history:', err);
    res.status(500).json({ error: err.message });
  }
});

// Full Work Log Entry by ID (with git diff, AI specifics, and checklist)
router.get('/:id', async (req, res) => {
  try {
    const { id } = req.params;
    const query = `
      SELECT 
        w.*,
        t.jira_key,
        t.title as ticket_title,
        t.branch_name,
        t.container_id,
        t.status as ticket_status,
        p.name as project_name,
        p.key as project_key,
        p.color as project_color,
        p.system_prompt_additions
      FROM work_logs w
      JOIN tickets t ON w.ticket_id = t.id
      JOIN projects p ON w.project_id = p.id
      WHERE w.id = $1;
    `;
    const { rows } = await pool.query(query, [id]);
    if (rows.length === 0) return res.status(404).json({ error: 'Work log not found' });
    res.json(rows[0]);
  } catch (err) {
    console.error('Error fetching work log:', err);
    res.status(500).json({ error: err.message });
  }
});

export default router;
