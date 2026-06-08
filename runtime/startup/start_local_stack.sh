#!/bin/bash
# start_local_stack.sh — Start the complete DeParadigm Media Local LLM Stack
#
# This script starts:
#   1. MLX model servers (Llama 4 Scout, Qwen32B, Qwen7B)
#   2. Paperclip bridge server
#   3. All services needed for local agent execution
#
# Usage:
#   cd /Users/nazeera/Documents/AI_PRODUCER
#   ./runtime/start_local_stack.sh

set -e

cd /Users/nazeera/Documents/AI_PRODUCER
source env/bin/activate

echo "🚀 Starting DeParadigm Media Local LLM Stack"
echo ""

# ── 1. Model Servers ────────────────────────────────────────────────────────
echo "📡 Starting Model Servers..."

# Kill existing servers
pkill -f "mlx_lm.server" 2>/dev/null || true
sleep 1

# Executive: Llama 4 Scout (port 8000)
if [ -f "/Users/nazeera/.cache/huggingface/hub/Llama-4-Scout-17B-16E-Instruct-4bit/model.safetensors.index.json" ]; then
    echo "  Starting Llama 4 Scout on :8000..."
    nohup python3 -m mlx_lm.server \
        --model /Users/nazeera/.cache/huggingface/hub/Llama-4-Scout-17B-16E-Instruct-4bit \
        --port 8000 > /tmp/mlx_scout.log 2>&1 &
    echo $! > /tmp/mlx_scout.pid
else
    echo "  ⏭ Llama 4 Scout not ready yet"
fi

# Standard: Qwen2.5-32B (port 8001)
if [ -f "/Users/nazeera/.cache/huggingface/hub/Qwen2.5-32B-Instruct-4bit/model.safetensors.index.json" ]; then
    echo "  Starting Qwen2.5-32B on :8001..."
    nohup python3 -m mlx_lm.server \
        --model /Users/nazeera/.cache/huggingface/hub/Qwen2.5-32B-Instruct-4bit \
        --port 8001 > /tmp/mlx_qwen32b.log 2>&1 &
    echo $! > /tmp/mlx_qwen32b.pid
else
    echo "  ⏭ Qwen2.5-32B not ready yet"
fi

# Fast: Qwen2.5-Coder-7B (port 8002)
echo "  Starting Qwen2.5-Coder-7B on :8002..."
nohup python3 -m mlx_lm.server \
    --model mlx-community/Qwen2.5-Coder-7B-Instruct-4bit \
    --port 8002 > /tmp/mlx_qwen7b.log 2>&1 &
echo $! > /tmp/mlx_qwen7b.pid

# Wait for servers to start
sleep 3

# Verify
for port in 8000 8001 8002; do
    if curl -s http://localhost:$port/v1/models > /dev/null 2>&1; then
        model=$(curl -s http://localhost:$port/v1/models | python3 -c "import sys,json; print(json.load(sys.stdin)['data'][0]['id'].split('/')[-1])" 2>/dev/null)
        echo "    ✅ :$port — $model"
    else
        echo "    ❌ :$port — not responding"
    fi
done

# ── 2. Bridge Server ────────────────────────────────────────────────────────
echo ""
echo "🌉 Starting Bridge Server..."

# Kill existing bridge
pkill -f "paperclip_bridge.py" 2>/dev/null || true
sleep 1

nohup /Users/nazeera/Documents/AI_PRODUCER/env/bin/python3 \
    runtime/agents/paperclip_bridge.py > /tmp/bridge.log 2>&1 &
echo $! > /tmp/bridge.pid
sleep 2

if curl -s http://localhost:3101/health > /dev/null 2>&1; then
    echo "    ✅ Bridge on :3101"
else
    echo "    ❌ Bridge not responding"
fi

# ── 3. Status ───────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  DeParadigm Media Local LLM Stack Ready"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "  MLX Servers:"
echo "    Primary (Executive) : http://127.0.0.1:8000/v1"
echo "    Standard (Skills)   : http://127.0.0.1:8001/v1"
echo "    Fast (Quick)        : http://127.0.0.1:8002/v1"
echo ""
echo "  Bridge Server        : http://127.0.0.1:3101"
echo "  Paperclip Server     : http://127.0.0.1:3100"
echo ""
echo "  Agents: 244 on local MLX + 1 on OpenClaw"
echo "  Cloud Fallback: Kimi 2.6 (configured)"
echo ""
echo "  To stop: pkill -f 'mlx_lm.server' && pkill -f 'paperclip_bridge.py'"
echo "═══════════════════════════════════════════════════════"
