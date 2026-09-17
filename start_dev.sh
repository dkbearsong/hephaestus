#!/bin/bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "=========================================================="
echo "   STARTING HEPHAESTUS IN DEVELOPMENT MODE               "
echo "=========================================================="

export PYTHONPATH="$DIR"
.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload &
PYTHON_PID=$!

cd frontend && npm run dev &
FRONTEND_PID=$!

cleanup() {
    echo "Shutting down dev services..."
    kill $PYTHON_PID $FRONTEND_PID 2>/dev/null || true
}
trap cleanup EXIT INT TERM

wait
