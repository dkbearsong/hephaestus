import express from 'express';
import http from 'http';
import cors from 'cors';
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';

import { initWebSocketServer } from './socket.js';
import projectsRouter from './routes/projects.js';
import ticketsRouter from './routes/tickets.js';
import logsRouter from './routes/logs.js';
import notificationsRouter from './routes/notifications.js';
import webhooksRouter from './routes/webhooks.js';
import searchRouter from './routes/search.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
dotenv.config({ path: path.resolve(__dirname, '../.env') });

const app = express();
const server = http.createServer(app);

// Initialize WebSockets
initWebSocketServer(server);

// Middleware
app.use(cors());
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true }));

// Request Logging
app.use((req, res, next) => {
  if (!req.url.startsWith('/health')) {
    console.log(`[API] ${req.method} ${req.url}`);
  }
  next();
});

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'hephaestus_express_gateway' });
});

// Mount Routes
app.use('/api/projects', projectsRouter);
app.use('/api/tickets', ticketsRouter);
app.use('/api/logs', logsRouter);
app.use('/api/notifications', notificationsRouter);
app.use('/api/webhooks', webhooksRouter);
app.use('/api/search', searchRouter);

// Serve Frontend in production if built
const frontendDist = path.resolve(__dirname, '../frontend/dist');
app.use(express.static(frontendDist));
app.get('*', (req, res, next) => {
  if (req.url.startsWith('/api')) return next();
  res.sendFile(path.join(frontendDist, 'index.html'), (err) => {
    if (err) res.status(404).send('Frontend not built yet. Run vite dev server or build frontend.');
  });
});

const PORT = process.env.PORT || 3001;
server.listen(PORT, () => {
  console.log(`=======================================================`);
  console.log(`🔥 Hephaestus Express Gateway running on http://localhost:${PORT}`);
  console.log(`📡 WebSocket server active on ws://localhost:${PORT}`);
  console.log(`=======================================================`);
});
