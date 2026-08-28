import express from 'express';
import { pool } from '../db.js';
import { broadcastEvent } from '../socket.js';

const router = express.Router();

// Get active and recent notifications with counts
router.get('/', async (req, res) => {
  try {
    const query = `
      SELECT 
        n.*,
        t.jira_key,
        t.title as ticket_title,
        p.name as project_name,
        p.color as project_color
      FROM agent_notifications n
      JOIN tickets t ON n.ticket_id = t.id
      JOIN projects p ON n.project_id = p.id
      WHERE n.status = 'pending'
      ORDER BY 
        CASE WHEN n.type = 'needs_input' THEN 1 ELSE 2 END,
        n.created_at DESC;
    `;
    const { rows } = await pool.query(query);

    // Calculate live counts
    const needsInputCount = rows.filter(r => r.type === 'needs_input').length;
    const completedCount = rows.filter(r => r.type === 'completed').length;

    // Overall link icon status:
    // If ANY live request needs input -> 'red'
    // Else if completed notifications exist -> 'yellow'
    // Else -> 'normal'
    let iconStatus = 'normal';
    if (needsInputCount > 0) {
      iconStatus = 'red';
    } else if (completedCount > 0) {
      iconStatus = 'yellow';
    }

    res.json({
      icon_status: iconStatus,
      needs_input_count: needsInputCount,
      completed_count: completedCount,
      total_pending: rows.length,
      notifications: rows
    });
  } catch (err) {
    console.error('Error fetching notifications:', err);
    res.status(500).json({ error: err.message });
  }
});

// Respond to / approve / deny / dismiss notification
router.post('/:id/respond', async (req, res) => {
  try {
    const { id } = req.params;
    const { action } = req.body; // 'approve' | 'deny' | 'dismiss' | 'resolve'

    const statusVal = (action === 'approve') ? 'approved' : (action === 'deny' ? 'denied' : 'resolved');

    const query = `
      UPDATE agent_notifications
      SET status = $1, resolved_at = NOW()
      WHERE id = $2
      RETURNING *;
    `;
    const { rows } = await pool.query(query, [statusVal, id]);
    if (rows.length === 0) return res.status(404).json({ error: 'Notification not found' });

    broadcastEvent('NOTIFICATION_RESOLVED', { id, status: statusVal });
    res.json(rows[0]);
  } catch (err) {
    console.error('Error updating notification:', err);
    res.status(500).json({ error: err.message });
  }
});

export default router;
