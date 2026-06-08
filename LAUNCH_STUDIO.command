#!/bin/bash
# LAUNCH_STUDIO.command — One-click startup for the full Solocorn AI Producer stack.
#
# Double-click this file in Finder (or drag it to the Dock) to bring up:
#   - MLX inference servers (Llama 4 Scout :8000, Qwen2.5-32B :8001, Qwen2.5-Coder-7B :8002)
#   - ComfyUI (:8188) and the render queue worker pool
#   - The .docker peripheral stack (Postgres, etc.)
#   - Paperclip governor (:3100) and the Python bridge server (:3101)
#
# Safe to double-click again later — every step checks whether its service
# is already healthy before starting a new one.

cd "$(dirname "$0")" || exit 1

echo "============================================================"
echo "🎬 Solocorn AI Producer — One-Click Studio Launch"
echo "============================================================"

if [ ! -d "env/bin" ]; then
    echo "❌ Python venv not found at env/. Run setup first (see 01_SKILLS/quickstart.md)."
    read -r -p "Press Enter to close..."
    exit 1
fi

source env/bin/activate

# ── Core stack: MLX inference, ComfyUI, render worker, Docker peripherals ──
python3 01_SKILLS/start_services.py

# ── Paperclip governor (executive dashboard, :3100) ────────────────────────
echo ""
echo "📎 Paperclip governor"
if curl -s http://127.0.0.1:3100/api/health | grep -q '"status": *"ok"'; then
    echo "  ✅ already running on :3100"
else
    PAPERCLIP_TELEMETRY_DISABLED=1 nohup npx paperclipai run > /tmp/paperclip.log 2>&1 &
    echo "  🚀 starting (pid $!)... log: /tmp/paperclip.log"
    sleep 5
    if curl -s http://127.0.0.1:3100/api/health | grep -q '"status": *"ok"'; then
        echo "  ✅ online"
    else
        echo "  ⚠️  still starting — check /tmp/paperclip.log if it doesn't come up"
    fi
fi

# ── Python bridge server (Paperclip <-> Solocorn adapter, :3101) ───────────
echo ""
echo "🌉 Bridge server"
if curl -s http://127.0.0.1:3101/health | grep -q '"status": *"ok"'; then
    echo "  ✅ already running on :3101"
else
    nohup env/bin/python3 runtime/agents/paperclip_bridge.py > /tmp/bridge.log 2>&1 &
    echo "  🚀 starting (pid $!)... log: /tmp/bridge.log"
    sleep 3
    if curl -s http://127.0.0.1:3101/health | grep -q '"status": *"ok"'; then
        echo "  ✅ online"
    else
        echo "  ⚠️  still starting — check /tmp/bridge.log if it doesn't come up"
    fi
fi

echo ""
echo "============================================================"
echo "🎉 Studio is up."
echo ""
echo "   Paperclip UI:    http://localhost:3100"
echo "   Bridge API:      http://localhost:3101"
echo "   MLX Inference:   http://localhost:8000/v1"
echo "   ComfyUI:         http://localhost:8188"
echo ""
echo "   Check status:    python3 01_SKILLS/start_services.py --status"
echo "   Stop everything: python3 01_SKILLS/start_services.py --stop"
echo "                    (Paperclip/bridge: pkill -f paperclipai; pkill -f paperclip_bridge.py)"
echo "============================================================"
read -r -p "Press Enter to close this window..."
