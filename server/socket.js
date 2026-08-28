import { WebSocketServer, WebSocket } from 'ws';

let wss = null;

export function initWebSocketServer(server) {
  wss = new WebSocketServer({ server });

  wss.on('connection', (ws) => {
    console.log('[WebSocket] Client connected.');

    ws.on('message', (msg) => {
      try {
        const data = JSON.parse(msg);
        console.log('[WebSocket] Received message from client:', data.type);
      } catch (e) {
        // ignore
      }
    });

    ws.on('close', () => {
      console.log('[WebSocket] Client disconnected.');
    });

    // Send initial ping/connection confirmation
    ws.send(JSON.stringify({ type: 'CONNECTED', timestamp: new Date().toISOString() }));
  });

  return wss;
}

export function broadcastEvent(eventType, payload) {
  if (!wss) return;
  const message = JSON.stringify({ type: eventType, payload, timestamp: new Date().toISOString() });
  wss.clients.forEach((client) => {
    if (client.readyState === WebSocket.OPEN) {
      client.send(message);
    }
  });
}
