# Local stack as services (always-on)

The autonomous scheduler needs the local stack up. These run as **launchd user agents** that start
at login and (with the watchdog) stay up — so cron content generation is truly unattended.

## The services
| launchd label | port | what |
|---|---|---|
| `com.deparadigm.mlx-smart` | 8000 | Qwen2.5-32B — `smart` tier (scriptwriting, directing) |
| `com.deparadigm.mlx-code`  | 8001 | Qwen2.5-Coder-7B — `code` tier |
| `com.deparadigm.mlx-fast`  | 8002 | Qwen2.5-7B — `fast` tier (extraction, captions) |
| `com.deparadigm.comfyui`   | 8188 | ComfyUI — B-roll image generation |

Plists live in `~/Library/LaunchAgents/com.deparadigm.*.plist` (RunAtLoad + KeepAlive). Logs:
`content_engine/logs/{mlx-smart,mlx-code,mlx-fast,comfyui}.log`.

## The watchdog (the reliable bit)
launchd's KeepAlive can be flaky for agents bootstrapped while already logged in. So
`content_engine/ensure_stack.sh` (cron **every 10 min**, and run before each scheduler batch)
health-checks each port and `launchctl kickstart`s any that are down. This is what actually
guarantees the stack stays up. Log: `content_engine/logs/ensure_stack.log`.

## Managing them
```sh
# status
launchctl list | grep deparadigm
# start now / restart one
launchctl kickstart -k gui/$(id -u)/com.deparadigm.mlx-smart
# bring the whole stack up right now
zsh content_engine/ensure_stack.sh
# stop one until next login
launchctl bootout gui/$(id -u)/com.deparadigm.comfyui
# reinstall a plist after editing
launchctl bootout gui/$(id -u)/com.deparadigm.mlx-fast 2>/dev/null
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.deparadigm.mlx-fast.plist
```

## Gotchas (learned the hard way)
- `mlx_lm.server /v1/models` lists ALL cached models, not the loaded one — to see what a port
  actually serves, check `ps -p <pid> -o command=` (the `--model` flag).
- `01_SKILLS/start_services.py` has `:8000`/`:8001` **swapped** vs reality (it puts Coder on 8000).
  Don't use it to (re)start the stack — use the launchd agents / `ensure_stack.sh`, which match
  `llm.py` (smart=:8000=32B). Reconcile start_services.py if you ever rely on it.
