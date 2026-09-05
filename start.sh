#!/bin/bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "=========================================================="
echo "   STARTING HEPHAESTUS CODING AGENT HARNESS SERVICES      "
echo "=========================================================="

# 1. Start Python FastAPI Core & LangGraph Engine
echo "Starting Python Core Service on http://localhost:8000..."
export PYTHONPATH="$DIR"
.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
PYTHON_PID=$!

# 2. Cleanup hook
cleanup() {
    echo "Shutting down Hephaestus services..."
    kill $PYTHON_PID 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo ""
echo "🔥 System Ready!"
echo "➡️  Python Harness API & Webhook Listener: http://localhost:8000"
echo "➡️  Jira Webhook Endpoint:                 http://localhost:8000/api/webhooks/jira"
echo ""

wait
