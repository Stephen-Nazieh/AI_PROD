# CONTENT ENGINE — System Map

> One page to understand the whole system. Everything is local, transparent, and editable.
> The brain is your local LLMs (mlx). Built for **idea → content**, any niche, any format.

## The flow
```
   YOU: an idea  +  spec (format · platform · channel · length)
        │
        ▼  ┌─────────────────────────────────────────────────────────────┐
   [1] SCRIPTWRITER agent   craft: agents/scriptwriter.skill.md (edit to improve)
        │                   brain: local Qwen-32B (:8000)
        ▼
     DRAFT SCRIPT  ──▶  ★ YOU VET / EDIT / APPROVE ★   (the human gate — you stay in control)
        │
        ▼
   [2] DIRECTOR agent       craft: agents/director.skill.md   [Phase 3]
        │                   → shot list / coverage / format plan + a show-bible config
        ▼
   [3] PRODUCERS  (your installed tools, format-routed)
        │   3d     → Blender engine (01-scripts/bl_scene_engine.py) + 02-pipeline
        │   2d     → PIL/ffmpeg compositor
        │   manim  → math/data inserts
        │   talking_head / social → framing presets
        │   voice  → Kokoro TTS (local) · music/sfx stems
        ▼
   [4] DISTRIBUTE  per platform (16:9 / 9:16 / 1:1 · thumbnail · captions)
        │
        ▼
   [5] MEMORY  logs every run's outcome + learnings → agents self-improve   [Phase 5]
```

## Where things live
| Path | What |
|---|---|
| `content_engine/engine.py` | the idea→content orchestrator (CLI) — [Phase 4] |
| `content_engine/llm.py` | local-LLM client (the brain): tiers `smart`/`fast`/`code` |
| `content_engine/agents/scriptwriter.{py,skill.md}` | writes the script · craft is the `.md` |
| `content_engine/agents/director.{py,skill.md}` | plans shots/coverage — [Phase 3] |
| `content_engine/producers/` | format → tool adapters (reuse the Blender/2D/Manim tools) |
| `content_engine/channels/<name>/channel.json` | per-channel brand/voice/format defaults |
| `content_engine/memory/` | self-improving memory store — [Phase 5] |
| `01-scripts/` | the Blender render engine + set/motion/acting libs (producers) |
| `02-pipeline/` | the screenplay→video pipeline (a 3D producer) |
| `06_SHARED_ASSETS/` | input assets: VRoid characters, Kokoro models, music/sfx stems |
| local mlx (:8000/:8002/:8001) | the brain (Qwen-32B / Qwen-7B / Coder) |

## The brain (local, no cloud)
| Tier | Port | Model | Use |
|---|---|---|---|
| smart | 8000 | Qwen2.5-32B | scriptwriting, directing, reasoning |
| fast | 8002 | Qwen2.5-7B | summaries, extraction, quick passes |
| code | 8001 | Qwen-Coder-7B | config/JSON generation |

`env/bin/python3 content_engine/llm.py` → prints brain health.

## How to run (current)
```bash
# 1. write a script from an idea (then you vet/edit the output)
env/bin/python3 content_engine/agents/scriptwriter.py \
    --idea "…" --format movie|talking_head|social|explainer --channel <name> --length "2 min"
# 2. produce video from an (approved) screenplay  [today via the 3D pipeline]
env/bin/python3 02-pipeline/produce.py --script <approved.md> --out OUT/
```
Full one-command `idea → content` (engine.py) and `new-channel` land in Phases 4 & 6.

## Design principles
- **Local-first** — the brain and all tools run on this machine; no cloud by default.
- **Human-in-the-loop** — you always vet the script before any render burns time.
- **Transparent** — every agent's craft is a readable `.skill.md` you can edit; every run is logged.
- **Format-agnostic** — 2D / 3D / talking-head / movie / social / combos via producer adapters.
- **Self-improving** — memory captures what worked/failed and feeds it back to the agents.
- **Channel factory** — spin up a new channel (brand, voice, defaults) in one command.

## Roadmap (transparent status)
- [x] Phase 0 — clean slate (purged produced content)
- [x] Phase 1 — Content Engine home + this map + LLM client + scriptwriter
- [x] Phase 3 — director agent (casting/staging) + scriptwriter skills
- [x] Phase 4 — `engine.py` (idea → script → vet gate → produce → distribute)
- [x] Phase 5 — self-improving memory (`memory/`: runs log + learnings → injected into agents)
- [x] Phase 6 — channel factory (`new_channel.py`)
- [x] Phase 2 — MCP server (`mcp_server.py`, 7 tools) + mcpo bridge (:8900) for Open WebUI; also ✔ in this CLI. See `MCP_SETUP.md`
- [x] Refinements (2026-06-25) — shared music beds (`06_SHARED_ASSETS/music-beds/`) · **local intent-router** (`engine.py chat "…"` + the single `assistant` MCP tool → reliable NL control on local models w/o native tool-calling) · format-aware render (social → native 9:16) · idea→video demo proven
- [x] Per-format producers (2026-06-25) — director picks blocking/coverage by format: **social → native 9:16** (closer, longer-lens vertical framing) · talking-head single-presenter · movie/explainer 16:9. `distribute` skips reframe when already vertical.
- [x] Paperclip oversight (2026-06-25) — channels register as **Paperclip projects** (`paperclip_sync.py`); produced runs update the project. Two channels live: midnight-tales, daily-curiosities.
- [x] Batch + 2nd channel — `engine.py batch --channel X --file ideas.txt`; channel `daily-curiosities` (social) added.
- [ ] Larger future — a true 2D producer (ComfyUI/PIL) · vertical-framing tuning pass · stronger casting · multi-shot variety

## Talk to it (reliable on local models)
```bash
env/bin/python3 content_engine/engine.py chat "make a 1-min horror short for midnight-tales about a haunted elevator"
```
In Open WebUI: enable the single **`assistant`** tool and type the same thing — the local router maps it to an action (no native tool-calling needed).

## Quick start (the system, today)
```bash
env/bin/python3 content_engine/engine.py health                 # brain + tools
env/bin/python3 content_engine/new_channel.py <slug> --name "…" --niche "…"
env/bin/python3 content_engine/engine.py write   --run r1 --idea "…" --format movie --channel <slug>
#   → review/edit content_engine/runs/r1/script.md
env/bin/python3 content_engine/engine.py produce --run r1       # cast → render → distribute
#   or one-shot:  engine.py make --run r1 --idea "…" --format movie
```
