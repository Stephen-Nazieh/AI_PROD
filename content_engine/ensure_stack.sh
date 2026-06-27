#!/bin/zsh
# ensure_stack.sh — guarantee the local stack is up. Kickstarts any down launchd service.
# Watchdog (cron every 10 min) + called by run_scheduler.sh before a batch. Belt-and-suspenders
# for launchd KeepAlive, which can be flaky for bootstrap-while-logged-in jobs.
export PATH=/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin
U=$(id -u)
LOG=/Users/nazeera/Documents/AI_PRODUCER/content_engine/logs/ensure_stack.log

ensure() {  # $1=launchd label  $2=port  $3=health path
  if ! curl -sf -m4 "http://127.0.0.1:$2$3" >/dev/null 2>&1; then
    echo "[$(date '+%F %T')] $1 (:$2) down -> kickstart" >> "$LOG"
    launchctl kickstart "gui/$U/com.deparadigm.$1" >/dev/null 2>&1
  fi
}

ensure mlx-smart 8000 /v1/models
ensure mlx-code  8001 /v1/models
ensure mlx-fast  8002 /v1/models
ensure comfyui   8188 /system_stats
