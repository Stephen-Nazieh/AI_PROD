#!/bin/bash
# LAUNCH_STUDIO.command — One-click startup for the full DeParadigm Media AI Producer stack.
#
# Double-click this file in Finder (or drag it to the Dock) to bring up:
#   - MLX inference servers (Llama 4 Scout :8000, Qwen2.5-32B :8001, Qwen2.5-Coder-7B :8002)
#   - ComfyUI (:8188) and the render queue worker pool
#   - The .docker peripheral stack (Postgres, etc.)
#   - Paperclip governor (:3100) and the Python bridge server (:3101)
#
# The bridge runs a background poller that auto-scaffolds a 05_PROJECTS/<slug>/
# folder for every Paperclip project (every 30s). It queries :3100, so the
# Paperclip governor is brought up and confirmed ready before the bridge starts.
#
# Safe to double-click again later — every step checks whether its service
# is already healthy before starting a new one.

cd "$(dirname "$0")" || exit 1

echo "============================================================"
echo "🎬 DeParadigm Media AI Producer — One-Click Studio Launch"
echo "============================================================"

if [ ! -d "env/bin" ]; then
    echo "❌ Python venv not found at env/. Run setup first (see 01_SKILLS/quickstart.md)."
    read -r -p "Press Enter to close..."
    exit 1
fi

source env/bin/activate

# Poll a /health-style endpoint until it reports "status":"ok" or timeout (seconds).
# Returns 0 as soon as it's healthy, 1 if the timeout elapses. The per-request
# timeout is 10s — the bridge's /health runs live subchecks and can take ~5s.
wait_for_health() {
    local url="$1" timeout="${2:-60}" elapsed=0
    while [ "$elapsed" -lt "$timeout" ]; do
        if curl -s -m 10 "$url" 2>/dev/null | grep -q '"status": *"ok"'; then
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    return 1
}

# ── Core stack: MLX inference, ComfyUI, render worker, Docker peripherals ──
python3 01_SKILLS/start_services.py

# ── Paperclip governor (executive dashboard, :3100) ────────────────────────
echo ""
echo "📎 Paperclip governor"
if wait_for_health http://127.0.0.1:3100/api/health 2; then
    echo "  ✅ already running on :3100"
else
    PAPERCLIP_TELEMETRY_DISABLED=1 nohup npx paperclipai run > /tmp/paperclip.log 2>&1 &
    echo "  🚀 starting (pid $!)... log: /tmp/paperclip.log"
    echo "  ⏳ waiting for :3100 (embedded Postgres boot can take a while)..."
    if wait_for_health http://127.0.0.1:3100/api/health 90; then
        echo "  ✅ online"
    else
        echo "  ⚠️  not healthy after 90s — check /tmp/paperclip.log"
    fi
fi

# ── Python bridge server (Paperclip <-> DeParadigm Media adapter, :3101) ───────────
echo ""
echo "🌉 Bridge server"
if wait_for_health http://127.0.0.1:3101/health 2; then
    echo "  ✅ already running on :3101"
else
    nohup env/bin/python3 runtime/agents/paperclip_bridge.py > /tmp/bridge.log 2>&1 &
    echo "  🚀 starting (pid $!)... log: /tmp/bridge.log"
    if wait_for_health http://127.0.0.1:3101/health 45; then
        echo "  ✅ online (auto-scaffold poller active)"
    else
        echo "  ⚠️  not healthy after 45s — check /tmp/bridge.log"
    fi
fi

echo ""
echo "============================================================"
echo "🎉 Studio is up."
echo ""

# Open the Paperclip dashboard in the browser (it's a headless web server, not an
# app — without this you'd just have the URL). Set STUDIO_NO_OPEN=1 to skip.
if [ "${STUDIO_NO_OPEN:-0}" != "1" ] && command -v open >/dev/null 2>&1; then
    if curl -s -m5 http://127.0.0.1:3100/api/health >/dev/null 2>&1; then
        echo "   🌐 Opening Paperclip dashboard in your browser..."
        open "http://localhost:3100" 2>/dev/null || true
    fi
fi
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
