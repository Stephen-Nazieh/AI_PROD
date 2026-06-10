#!/bin/bash
# start_model_servers.sh — Start all local LLM model servers
#
# Usage:
#   cd /Users/nazeera/Documents/AI_PRODUCER
#   source env/bin/activate
#   ./runtime/start_model_servers.sh

set -e

echo "🚀 Starting DeParadigm Media Local LLM Servers"
echo ""

# Kill existing servers and proxy
pkill -f "mlx_lm.server" 2>/dev/null || true
pkill -f "anthropic_openai_proxy" 2>/dev/null || true
sleep 1

# Coding/fast: Qwen2.5-Coder-7B (port 8000)
# NOTE: Llama-4-Scout-17B-16E (a 109B-total MoE) was impractically slow on this
# hardware (>100s/token, memory-thrashing alongside the other models). Replaced
# with the cached Qwen-Coder-7B (sub-second). IMPORTANT: clients must send this
# exact model name — mlx_lm.server loads whatever model the request asks for.
echo "Starting Qwen2.5-Coder-7B on :8000..."
nohup python3 -m mlx_lm.server \
    --model mlx-community/Qwen2.5-Coder-7B-Instruct-4bit \
    --port 8000 > "$(dirname "$0")/../../logs/mlx_coder7b.log" 2>&1 &
echo $! > /tmp/mlx_coder7b.pid
sleep 3
curl -s http://localhost:8000/v1/models > /dev/null 2>&1 && echo "  ✅ Coder7B ready" || echo "  ⚠️  Coder7B failed to start"

# Standard: Qwen2.5-32B (port 8001)
if [ -d "/Users/nazeera/.cache/huggingface/hub/Qwen2.5-32B-Instruct-4bit" ]; then
    echo "Starting Qwen2.5-32B on :8001..."
    nohup python3 -m mlx_lm.server \
        --model /Users/nazeera/.cache/huggingface/hub/Qwen2.5-32B-Instruct-4bit \
        --port 8001 > /tmp/mlx_qwen32b.log 2>&1 &
    echo $! > /tmp/mlx_qwen32b.pid
    sleep 3
    curl -s http://localhost:8001/v1/models > /dev/null 2>&1 && echo "  ✅ Qwen32B ready" || echo "  ⚠️  Qwen32B failed to start"
else
    echo "  ⏭ Qwen2.5-32B not downloaded yet (skipping)"
fi

# Fast: Qwen2.5-Coder-7B (port 8002)
echo "Starting Qwen2.5-Coder-7B on :8002..."
nohup python3 -m mlx_lm.server \
    --model mlx-community/Qwen2.5-Coder-7B-Instruct-4bit \
    --port 8002 > /tmp/mlx_qwen7b.log 2>&1 &
echo $! > /tmp/mlx_qwen7b.pid
sleep 3
curl -s http://localhost:8002/v1/models > /dev/null 2>&1 && echo "  ✅ Qwen7B ready" || echo "  ⚠️  Qwen7B failed to start"

# Anthropic↔OpenAI Proxy (port 8003)
echo "Starting Anthropic↔OpenAI Proxy on :8003..."
nohup /Users/nazeera/Documents/AI_PRODUCER/env/bin/python3 \
    /Users/nazeera/Documents/AI_PRODUCER/runtime/proxy/anthropic_openai_proxy.py \
    --port 8003 > /tmp/proxy_anthropic.log 2>&1 &
echo $! > /tmp/proxy_anthropic.pid
sleep 2
curl -s http://localhost:8003/health > /dev/null 2>&1 && echo "  ✅ Proxy ready" || echo "  ⚠️  Proxy failed to start"

echo ""
echo "Done. Stack:"
echo "  Primary (Executive):  http://127.0.0.1:8000/v1"
echo "  Standard (Skills):    http://127.0.0.1:8001/v1"
echo "  Fast (Quick queries): http://127.0.0.1:8002/v1"
echo "  Anthropic Proxy:      http://127.0.0.1:8003"
