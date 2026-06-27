#!/bin/zsh
# install_services.sh — deploy the launchd agents (mlx + ComfyUI) so the local stack auto-starts.
# Idempotent: re-running reinstalls + restarts. Run after a machine rebuild to restore the stack.
# NOTE: the plists hardcode this repo's absolute path; if you move the repo, update the plists.
set -e
export PATH=/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin
REPO="$(cd "$(dirname "$0")/.." && pwd)"
U=$(id -u)
DEST=~/Library/LaunchAgents
mkdir -p "$DEST" "$REPO/content_engine/logs"

for L in mlx-smart mlx-code mlx-fast comfyui; do
  cp "$REPO/content_engine/services/com.deparadigm.$L.plist" "$DEST/"
  launchctl bootout "gui/$U/com.deparadigm.$L" 2>/dev/null || true
  launchctl enable  "gui/$U/com.deparadigm.$L" 2>/dev/null || true
  launchctl bootstrap "gui/$U" "$DEST/com.deparadigm.$L.plist" 2>/dev/null || true
  launchctl kickstart "gui/$U/com.deparadigm.$L" 2>/dev/null || true
  echo "  installed + started com.deparadigm.$L"
done
echo "done. give the 32B ~60s to load, then: env/bin/python3 content_engine/engine.py status"
