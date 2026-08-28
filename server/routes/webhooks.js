import express from 'express';
import axios from 'axios';
import { broadcastEvent } from '../socket.js';

const router = express.Router();
const PYTHON_SERVICE = process.env.PYTHON_SERVICE_URL || 'http://localhost:8000';

/**
 * Jira Webhook Intake Endpoint
 * Listens for comment_created or issue_updated events.
 * Verifies that the comment has <|prompt|> or <|prompt-new|>.
 * Forwards to Python orchestrator (which immediately strips label and stages files).
 */
router.post('/jira', async (req, res) => {
  try {
    const payload = req.body;
    console.log('[Webhook] Received Jira webhook event:', payload.webhookEvent || 'custom');

    // Extract comment and issue information from standard Jira webhook payload
    let commentBody = '';
    let issueKey = '';
    let issueSummary = '';
    let projectKey = '';
    let labels = [];

    if (payload.comment && payload.comment.body) {
      commentBody = payload.comment.body;
    } else if (payload.issue && payload.issue.fields) {
      const comments = payload.issue.fields.comment?.comments || [];
      if (comments.length > 0) {
        commentBody = comments[comments.length - 1].body;
      }
    }

    if (payload.issue) {
      issueKey = payload.issue.key || '';
      labels = payload.issue.fields?.labels || [];
      issueSummary = payload.issue.fields?.summary || '';
      projectKey = payload.issue.fields?.project?.key || issueKey.split('-')[0] || '';
    }

    // Direct JSON fallback payload support for testing
    if (payload.comment_text) {
      commentBody = payload.comment_text;
      issueKey = payload.jira_issue_key || issueKey || 'TEST-1';
      issueSummary = payload.summary || issueSummary || 'Test Issue';
      projectKey = payload.project_key || projectKey || 'TEST';
    }

    if (!commentBody) {
      return res.status(200).json({ message: 'No comment body detected in webhook event' });
    }

    const trimmed = commentBody.trim();
    if (!trimmed.startsWith('<|prompt|>') && !trimmed.startsWith('<|prompt-new|>')) {
      console.log('[Webhook] Comment does not begin with <|prompt|> or <|prompt-new|>. Ignoring.');
      return res.status(200).json({ message: 'Ignored: No prompt tag' });
    }

    console.log(`[Webhook] Processing AI prompt trigger for Jira ticket ${issueKey}...`);

    // Dispatch to Python orchestrator pipeline
    const orchestratorRes = await axios.post(`${PYTHON_SERVICE}/api/pipeline/webhook`, {
      comment_text: commentBody,
      jira_issue_key: issueKey,
      summary: issueSummary,
      project_key: projectKey
    });

    broadcastEvent('WEBHOOK_PROCESSED', {
      issueKey,
      status: orchestratorRes.data.status,
      ticket_id: orchestratorRes.data.ticket_id
    });

    res.json({
      success: true,
      message: `Trigger received and dispatched for ${issueKey}`,
      pipeline_result: orchestratorRes.data
    });
  } catch (err) {
    console.error('Error processing Jira webhook:', err.message);
    res.status(500).json({ error: err.message });
  }
});

export default router;
