#!/bin/bash
# start_model_servers.sh — compatibility shim.
#
# The MLX inference servers (:8000/:8001/:8002) and the Anthropic→OpenAI proxy
# (:8003) are now defined ONCE in 01_SKILLS/start_services.py (its SERVICES dict is
# the single source of truth). This script used to duplicate that config and drifted
# from it; it now just delegates, so the two launchers can never disagree again.
#
# Behaviour preserved: this restarts the model servers + proxy (kill, then start).
# To merely ensure they're up without restarting, call:
#     env/bin/python3 01_SKILLS/start_services.py --mlx-only
#
# Usage:
#   ./runtime/startup/start_model_servers.sh

set -e
cd "$(dirname "$0")/../.." || exit 1   # repo root (so relative cmds resolve)

echo "🚀 Restarting MLX servers + proxy via start_services.py (single source of truth)…"
pkill -f "mlx_lm.server" 2>/dev/null || true
pkill -f "anthropic_openai_proxy" 2>/dev/null || true
sleep 1

exec env/bin/python3 01_SKILLS/start_services.py --mlx-only "$@"
