# Autonomous scheduler

`scheduler.py` generates content on a schedule with **no human in the loop for production** — but
content is **auto-generated, not auto-posted**. Each cycle's finished shorts land in the channel's
`PUBLISH_QUEUE.md` for your review; posting stays manual until you wire credentials (see
`POSTING_SETUP.md`) and opt in.

## What one cycle does
1. Picks the **next channel** (round-robin across `channels/`, state in `memory/scheduler_state.json`).
2. Gets **fresh ideas**: hand-verified `channels/<slug>/idea_seeds.txt` first, then the local LLM as
   overflow (the LLM hallucinates "facts", so seeds are the reliable source — keep them stocked).
3. Produces each idea (`engine.py make`): script → cast → render → B-roll → captions → QA → manifest.
4. Refreshes the channel's publish queue + Paperclip summary.
5. Logs to `content_engine/logs/scheduler-YYYYMM.log`; used ideas tracked in `topics_used.txt`.

## The schedule (cron)
Installed in your crontab — **daily at 10:00**, 2 shorts for the next channel:
```
0 10 * * * /Users/nazeera/Documents/AI_PRODUCER/content_engine/run_scheduler.sh
```
- **Change time/frequency:** `crontab -e` (e.g. `0 */12 * * *` = every 12h; `0 10 * * 1` = Mondays).
- **Remove:** `crontab -e` and delete the two AI_PRODUCER lines.
- **Run now / manually:** `env/bin/python3 content_engine/scheduler.py --count 2 [--channel <slug>]`

## Prerequisites (the cycle skips safely if missing)
The render needs the local stack up: **mlx LLM servers** (:8000/:8002), **ComfyUI** (:8188), and
**Blender** installed. If the LLM is unreachable the cycle logs `SKIP` and exits cleanly (no crash).
For true hands-off operation, run those as login/launchd services so they're always up.

## Stocking ideas
Add verified facts to `channels/<slug>/idea_seeds.txt` (one per line). With ~12 seeds per channel and
2/day, that's ~a week of guaranteed-factual content per channel before the LLM overflow kicks in.
