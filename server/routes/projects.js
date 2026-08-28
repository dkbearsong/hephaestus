import express from 'express';
import { pool } from '../db.js';
import axios from 'axios';

const router = express.Router();
const PYTHON_SERVICE = process.env.PYTHON_SERVICE_URL || 'http://localhost:8000';

// List all projects with active ticket summary
router.get('/', async (req, res) => {
  try {
    const query = `
      SELECT 
        p.*,
        COUNT(t.id) as ticket_count,
        COUNT(CASE WHEN t.status = 'paused_waiting_input' THEN 1 END) as paused_count,
        COUNT(CASE WHEN t.status = 'review_ready' THEN 1 END) as review_ready_count
      FROM projects p
      LEFT JOIN tickets t ON p.id = t.project_id
      GROUP BY p.id
      ORDER BY p.name ASC;
    `;
    const { rows } = await pool.query(query);
    res.json(rows);
  } catch (err) {
    console.error('Error fetching projects:', err);
    res.status(500).json({ error: err.message });
  }
});

// Get single project details (synchronizes with Jira issue if linked)
router.get('/:id', async (req, res) => {
  try {
    const { id } = req.params;
    const { rows } = await pool.query('SELECT * FROM projects WHERE id = $1', [id]);
    if (rows.length === 0) {
      return res.status(404).json({ error: 'Project not found' });
    }

    const project = rows[0];

    // Attempt to pull latest Jira details if linked
    let jiraDetails = null;
    if (project.jira_ticket_key) {
      try {
        const resp = await axios.get(`${PYTHON_SERVICE}/api/jira/issue/${project.jira_ticket_key}`, { timeout: 3000 });
        jiraDetails = resp.data;
      } catch (jiraErr) {
        console.warn(`Could not sync with Jira for ticket ${project.jira_ticket_key}:`, jiraErr.message);
      }
    }

    res.json({
      ...project,
      jira_details: jiraDetails
    });
  } catch (err) {
    console.error('Error fetching project:', err);
    res.status(500).json({ error: err.message });
  }
});

// Update project details and per-project system prompt additions
router.put('/:id', async (req, res) => {
  try {
    const { id } = req.params;
    const { name, repo_url, system_prompt_additions, color, jira_ticket_key, description } = req.body;

    const query = `
      UPDATE projects 
      SET 
        name = COALESCE($1, name),
        repo_url = COALESCE($2, repo_url),
        system_prompt_additions = COALESCE($3, system_prompt_additions),
        color = COALESCE($4, color),
        jira_ticket_key = COALESCE($5, jira_ticket_key),
        updated_at = NOW()
      WHERE id = $6
      RETURNING *;
    `;
    const { rows } = await pool.query(query, [name, repo_url, system_prompt_additions, color, jira_ticket_key, id]);
    if (rows.length === 0) {
      return res.status(404).json({ error: 'Project not found' });
    }

    const updatedProject = rows[0];

    // Push update back to Jira if linked
    if (updatedProject.jira_ticket_key && (name || description)) {
      try {
        // Asynchronous fire-and-forget push to Jira
        axios.post(`${PYTHON_SERVICE}/api/jira/update`, {
          issue_key: updatedProject.jira_ticket_key,
          summary: name,
          description: description
        }, { timeout: 3000 }).catch(e => console.warn('Jira push update failed:', e.message));
      } catch (e) {
        // ignore
      }
    }

    res.json(updatedProject);
  } catch (err) {
    console.error('Error updating project:', err);
    res.status(500).json({ error: err.message });
  }
});

export default router;
