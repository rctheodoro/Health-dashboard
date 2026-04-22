#!/bin/bash
# Alfred Health Dashboard — Startup Script
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DASHBOARD_DIR="$SCRIPT_DIR/dashboard"
SCRIPTS_DIR="$SCRIPT_DIR/scripts"

echo "🤵 Alfred Health Dashboard"
echo "================================"

# Install dependencies
echo "📦 Setting up Python environment..."
VENV_DIR="$SCRIPT_DIR/.venv"

# Create venv if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
  echo "   Created venv at $VENV_DIR"
fi

# Install dependencies into venv
"$VENV_DIR/bin/pip" install -q -r "$SCRIPTS_DIR/requirements.txt"
echo "   Dependencies ready."

# Kill any existing instance on port 8888
echo "🔍 Checking port 8888..."
lsof -ti:8888 | xargs kill -9 2>/dev/null || true

# Start Flask server in background
echo "🚀 Starting server..."
cd "$SCRIPT_DIR"
PYTHONPATH="$SCRIPTS_DIR" "$VENV_DIR/bin/python" "$DASHBOARD_DIR/server.py" &
SERVER_PID=$!
echo $SERVER_PID > /tmp/alfred-health-dashboard.pid

# Wait for server to be ready
echo "⏳ Waiting for server to start..."
for i in $(seq 1 10); do
  sleep 1
  if curl -s http://localhost:8888 > /dev/null 2>&1; then
    break
  fi
done

# Open browser
echo "🌐 Opening browser..."
open http://localhost:8888 2>/dev/null || xdg-open http://localhost:8888 2>/dev/null || true

echo ""
echo "✅ Alfred Health Dashboard running at http://localhost:8888"
echo "   Server PID: $SERVER_PID"
echo "   To stop: kill \$(cat /tmp/alfred-health-dashboard.pid)"
echo ""
