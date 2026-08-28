import express from 'express';
import { pool } from '../db.js';
import axios from 'axios';
import { broadcastEvent } from '../socket.js';

const router = express.Router();
const PYTHON_SERVICE = process.env.PYTHON_SERVICE_URL || 'http://localhost:8000';

// List tickets for a project
router.get('/by-project/:projectId', async (req, res) => {
  try {
    const { projectId } = req.params;
    const query = `
      SELECT 
        t.*,
        (SELECT COUNT(*) FROM chat_messages c WHERE c.ticket_id = t.id AND c.status = 'pending' AND c.sender = 'agent') as pending_agent_questions,
        (SELECT COUNT(*) FROM work_logs w WHERE w.ticket_id = t.id) as log_count,
        (SELECT timestamp FROM work_logs w WHERE w.ticket_id = t.id ORDER BY timestamp DESC LIMIT 1) as last_work_timestamp
      FROM tickets t
      WHERE t.project_id = $1
      ORDER BY t.updated_at DESC;
    `;
    const { rows } = await pool.query(query, [projectId]);
    res.json(rows);
  } catch (err) {
    console.error('Error fetching tickets:', err);
    res.status(500).json({ error: err.message });
  }
});

// Get single ticket details with work logs and chat
router.get('/:id', async (req, res) => {
  try {
    const { id } = req.params;
    const tQuery = `
      SELECT t.*, p.name as project_name, p.key as project_key, p.color as project_color, p.system_prompt_additions
      FROM tickets t
      JOIN projects p ON t.project_id = p.id
      WHERE t.id = $1;
    `;
    const tRes = await pool.query(tQuery, [id]);
    if (tRes.rows.length === 0) return res.status(404).json({ error: 'Ticket not found' });

    const ticket = tRes.rows[0];

    // Fetch work logs
    const lRes = await pool.query(
      'SELECT * FROM work_logs WHERE ticket_id = $1 ORDER BY timestamp DESC',
      [id]
    );

    // Fetch chat history
    const cRes = await pool.query(
      'SELECT * FROM chat_messages WHERE ticket_id = $1 ORDER BY created_at ASC',
      [id]
    );

    // Fetch notifications
    const nRes = await pool.query(
      'SELECT * FROM agent_notifications WHERE ticket_id = $1 ORDER BY created_at DESC',
      [id]
    );

    res.json({
      ticket,
      work_logs: lRes.rows,
      chat_messages: cRes.rows,
      notifications: nRes.rows
    });
  } catch (err) {
    console.error('Error fetching ticket details:', err);
    res.status(500).json({ error: err.message });
  }
});

// Submit a new prompt update to direct AI agent to make further changes
router.post('/:id/prompt', async (req, res) => {
  try {
    const { id } = req.params;
    const { prompt } = req.body;

    if (!prompt) return res.status(400).json({ error: 'Prompt text is required' });

    const tRes = await pool.query(
      'SELECT t.*, p.key as project_key FROM tickets t JOIN projects p ON t.project_id = p.id WHERE t.id = $1',
      [id]
    );
    if (tRes.rows.length === 0) return res.status(404).json({ error: 'Ticket not found' });

    const ticket = tRes.rows[0];

    // Record user chat message
    await pool.query(
      `INSERT INTO chat_messages (ticket_id, project_id, sender, message_type, content, status)
       VALUES ($1, $2, 'user', 'prompt_update', $3, 'answered')`,
      [ticket.id, ticket.project_id, prompt]
    );

    // Dispatch job to Python orchestrator
    const formattedPrompt = prompt.startsWith('<|prompt|>') ? prompt : `<|prompt|> ${prompt}`;
    
    // Call Python pipeline
    const pipelineRes = await axios.post(`${PYTHON_SERVICE}/api/pipeline/webhook`, {
      comment_text: formattedPrompt,
      jira_issue_key: ticket.jira_key,
      summary: ticket.title,
      project_key: ticket.project_key
    });

    broadcastEvent('TICKET_UPDATED', { ticket_id: ticket.id, result: pipelineRes.data });
    res.json(pipelineRes.data);
  } catch (err) {
    console.error('Error dispatching prompt update:', err);
    res.status(500).json({ error: err.message });
  }
});

// Finalize branch merge: deletes container & images, transitions Jira ticket
router.post('/:id/merge', async (req, res) => {
  try {
    const { id } = req.params;

    const tRes = await pool.query('SELECT * FROM tickets WHERE id = $1', [id]);
    if (tRes.rows.length === 0) return res.status(404).json({ error: 'Ticket not found' });

    const ticket = tRes.rows[0];

    // Call Python orchestrator to delete container & images and notify Jira
    const mergeRes = await axios.post(`${PYTHON_SERVICE}/api/pipeline/merge`, {
      ticket_id: ticket.id
    });

    broadcastEvent('BRANCH_MERGED', { ticket_id: ticket.id, jira_key: ticket.jira_key });
    res.json({ success: true, message: `Branch ${ticket.branch_name} merged and container pruned successfully.`, details: mergeRes.data });
  } catch (err) {
    console.error('Error executing merge:', err);
    res.status(500).json({ error: err.message });
  }
});

// Get chat messages
router.get('/:id/chat', async (req, res) => {
  try {
    const { id } = req.params;
    const { rows } = await pool.query(
      'SELECT * FROM chat_messages WHERE ticket_id = $1 ORDER BY created_at ASC',
      [id]
    );
    res.json(rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Post a chat message / answer agent question
router.post('/:id/chat', async (req, res) => {
  try {
    const { id } = req.params;
    const { content, approve_external_access } = req.body;

    const tRes = await pool.query(
      'SELECT t.*, p.key as project_key FROM tickets t JOIN projects p ON t.project_id = p.id WHERE t.id = $1',
      [id]
    );
    if (tRes.rows.length === 0) return res.status(404).json({ error: 'Ticket not found' });
    const ticket = tRes.rows[0];

    // Insert user chat message
    const msgRes = await pool.query(
      `INSERT INTO chat_messages (ticket_id, project_id, sender, message_type, content, status)
       VALUES ($1, $2, 'user', 'answer', $3, 'answered')
       RETURNING *`,
      [ticket.id, ticket.project_id, content]
    );

    // Resolve any pending questions or notifications for this ticket
    await pool.query(
      `UPDATE agent_notifications 
       SET status = 'resolved', resolved_at = NOW() 
       WHERE ticket_id = $1 AND status = 'pending'`,
      [ticket.id]
    );
    await pool.query(
      `UPDATE chat_messages 
       SET status = 'answered' 
       WHERE ticket_id = $1 AND sender = 'agent' AND status = 'pending'`,
      [ticket.id]
    );

    // If this was answering a pause / approving access, resume the agent!
    const resumePrompt = `<|prompt|> User responded: "${content}". ${approve_external_access ? 'External network access granted.' : ''} Please proceed with implementing changes.`;
    
    // Call Python pipeline in background to continue task
    axios.post(`${PYTHON_SERVICE}/api/pipeline/webhook`, {
      comment_text: resumePrompt,
      jira_issue_key: ticket.jira_key,
      summary: ticket.title,
      project_key: ticket.project_key
    }).then(res => {
      broadcastEvent('AGENT_RESUMED', { ticket_id: ticket.id, result: res.data });
    }).catch(e => console.error('Error resuming agent:', e.message));

    broadcastEvent('CHAT_MESSAGE', { ticket_id: ticket.id, message: msgRes.rows[0] });
    res.json(msgRes.rows[0]);
  } catch (err) {
    console.error('Error sending chat message:', err);
    res.status(500).json({ error: err.message });
  }
});

export default router;
