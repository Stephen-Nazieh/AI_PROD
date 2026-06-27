#!/bin/zsh
# Cron entrypoint for the autonomous content scheduler.
# Generates a batch for the next channel (rotating). Skips safely if the local LLM servers are down.
# Prereq: mlx LLM servers (:8000/:8002) + ComfyUI (:8188) running; Blender installed.
cd /Users/nazeera/Documents/AI_PRODUCER || exit 1
mkdir -p content_engine/logs
# make sure the local stack is up, then give heavy models a moment to load before producing
zsh content_engine/ensure_stack.sh
sleep 60
exec env/bin/python3 content_engine/scheduler.py --count 2 >> content_engine/logs/cron.log 2>&1
