import axios from 'axios';

const API_BASE = '/api';

export const api = {

  // Run Dashboards
  getRuns: () => axios.get(`${API_BASE}/runs`).then(r => r.data),
  getRun: (id) => axios.get(`${API_BASE}/runs/${id}`).then(r => r.data),
  getRunEvents: (id) => axios.get(`${API_BASE}/runs/${id}/events`).then(r => r.data),
  getStats: () => axios.get(`${API_BASE}/stats`).then(r => r.data),

  // Projects
  getProjects: () => axios.get(`${API_BASE}/projects`).then(r => r.data),
  getProject: (id) => axios.get(`${API_BASE}/projects/${id}`).then(r => r.data),
  updateProject: (id, data) => axios.put(`${API_BASE}/projects/${id}`, data).then(r => r.data),

  // Tickets
  getTicketsByProject: (projectId) => axios.get(`${API_BASE}/tickets/by-project/${projectId}`).then(r => r.data),
  getTicket: (id) => axios.get(`${API_BASE}/tickets/${id}`).then(r => r.data),
  submitPromptUpdate: (id, prompt) => axios.post(`${API_BASE}/tickets/${id}/prompt`, { prompt }).then(r => r.data),
  mergeBranch: (id) => axios.post(`${API_BASE}/tickets/${id}/merge`).then(r => r.data),

  // Chat
  getChatMessages: (ticketId) => axios.get(`${API_BASE}/tickets/${ticketId}/chat`).then(r => r.data),
  sendChatMessage: (ticketId, content, approveExternal = false) => 
    axios.post(`${API_BASE}/tickets/${ticketId}/chat`, { content, approve_external_access: approveExternal }).then(r => r.data),

  // Work Logs & Queues
  getRecentActions: () => axios.get(`${API_BASE}/logs/recent`).then(r => r.data),
  getQueueHistory: () => axios.get(`${API_BASE}/logs/queue-history`).then(r => r.data),
  getWorkLog: (id) => axios.get(`${API_BASE}/logs/${id}`).then(r => r.data),

  // Notifications
  getNotifications: () => axios.get(`${API_BASE}/notifications`).then(r => r.data),
  respondNotification: (id, action) => axios.post(`${API_BASE}/notifications/${id}/respond`, { action }).then(r => r.data),

  // Full-Text Search
  searchFullText: (query, projectId = null) => {
    let url = `${API_BASE}/search?q=${encodeURIComponent(query)}`;
    if (projectId) url += `&project_id=${projectId}`;
    return axios.get(url).then(r => r.data);
  },

  // Simulated Webhook Trigger for rapid testing
  triggerWebhook: (payload) => axios.post(`${API_BASE}/webhooks/jira`, payload).then(r => r.data)
};

export function connectWebSocket(onMessage) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws`;
  let socket = null;

  try {
    socket = new WebSocket(wsUrl);
    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage(data);
      } catch (e) {
        console.warn('WS message parse error:', e);
      }
    };
    socket.onerror = (err) => console.warn('WS connection error:', err);
  } catch (e) {
    console.warn('WS setup failed:', e);
  }

  return socket;
}
