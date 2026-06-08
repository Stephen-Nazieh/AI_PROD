#!/bin/bash
# bootstrap_paperclip.sh — One-shot startup for the full Paperclip + Bridge stack.
#
# Usage:
#   cd /Users/nazeera/Documents/AI_PRODUCER
#   bash runtime/bootstrap_paperclip.sh

set -e

echo "🚀 Solocorn Paperclip Bootstrap"
echo "================================"

# ── Verify prerequisites ────────────────────────────────────────────────────

if ! command -v npx &> /dev/null; then
    echo "❌ npx not found. Install Node.js first."
    exit 1
fi

if ! command -v docker &> /dev/null; then
    echo "❌ docker not found. Install Docker Desktop first."
    exit 1
fi

if [ ! -d "env/bin" ]; then
    echo "❌ Python venv not found. Run: bash 01_SKILLS/setup_env.sh"
    exit 1
fi

# ── Start Docker stack ──────────────────────────────────────────────────────
echo ""
echo "🐳 Starting Docker peripheral stack..."
cd .docker
docker compose up -d
cd ..

# ── Activate Python environment ─────────────────────────────────────────────
source env/bin/activate

# ── Verify MLX server ───────────────────────────────────────────────────────
echo ""
echo "🧠 Checking local MLX inference server..."
if ! python3 01_SKILLS/test_omlx.py | grep -q "✅ Status: Online"; then
    echo "⚠️  MLX server not responding on port 8000."
    echo "   Start it with: mlx_lm.server --model mlx-community/Qwen2.5-Coder-7B-Instruct-4bit --port 8000"
    echo "   Continuing anyway..."
else
    echo "   ✅ MLX server online."
fi

# ── Start Paperclip server ──────────────────────────────────────────────────
echo ""
echo "📎 Starting Paperclip server..."
if curl -s http://127.0.0.1:3100/api/health | grep -q '"status": *"ok"'; then
    echo "   ✅ Paperclip already running on port 3100."
else
    PAPERCLIP_TELEMETRY_DISABLED=1 npx paperclipai run > /tmp/paperclip.log 2>&1 &
    PAPERCLIP_PID=$!
    echo "   Paperclip PID: $PAPERCLIP_PID"
    sleep 5
    if curl -s http://127.0.0.1:3100/api/health | grep -q '"status": *"ok"'; then
        echo "   ✅ Paperclip started."
    else
        echo "   ❌ Paperclip failed to start. Check /tmp/paperclip.log"
        exit 1
    fi
fi

# ── Start bridge server ─────────────────────────────────────────────────────
echo ""
echo "🌉 Starting Python bridge server..."
if curl -s http://127.0.0.1:3101/health | grep -q '"status": *"ok"'; then
    echo "   ✅ Bridge already running on port 3101."
else
    python3 runtime/agents/paperclip_bridge.py > /tmp/bridge.log 2>&1 &
    BRIDGE_PID=$!
    echo "   Bridge PID: $BRIDGE_PID"
    sleep 2
    if curl -s http://127.0.0.1:3101/health | grep -q '"status": *"ok"'; then
        echo "   ✅ Bridge started."
    else
        echo "   ❌ Bridge failed to start. Check /tmp/bridge.log"
        exit 1
    fi
fi

# ── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo "================================"
echo "🎉 Solocorn stack is live!"
echo ""
echo "   Paperclip UI:    http://localhost:3100"
echo "   Bridge API:      http://localhost:3101"
echo "   MLX Inference:   http://localhost:8000/v1"
echo "   OpenClaw:        ws://localhost:18789"
echo "   PostgreSQL:      localhost:5432 (production), localhost:5433 (governance)"
echo ""
echo "   Company:         Solocorn Studios (SOL)"
echo "   Agents:          245"
echo "   Projects:        4"
echo "   Skills:          235"
echo ""
echo "   Dashboard:       http://localhost:3100/SOL/dashboard"
echo ""
echo "Press Ctrl+C to stop this script (servers will keep running in background)."
echo "To stop everything: lsof -ti:3100 | xargs kill -9; lsof -ti:3101 | xargs kill -9"

# Keep script alive so user sees the summary
trap "echo ''; echo '🛑 Bootstrap interrupted.'; exit 0" INT
while true; do
    sleep 1
done
