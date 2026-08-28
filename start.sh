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

# 2. Start Express Gateway
echo "Starting Express Gateway on http://localhost:3001..."
node server/index.js &
EXPRESS_PID=$!

cleanup() {
    echo "Shutting down Hephaestus services..."
    kill $PYTHON_PID $EXPRESS_PID 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo ""
echo "🔥 System Ready!"
echo "➡️  Express & Frontend Web App: http://localhost:3001"
echo "➡️  Python Harness API:          http://localhost:8000"
echo ""

wait
