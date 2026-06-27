# AI_PRODUCER — Complete Project Documentation

> **Purpose of this document.** A single, honest, top-to-bottom map of the entire project so
> you can understand what it *is*, what's a reusable **system** vs. one-off **content**, what's
> actually running vs. aspirational scaffold, and where the recent 3D work fits. Written
> 2026-06-25.

---

## ⭐ CURRENT DIRECTION (2026-06-25) — General "Content Engine"

**The project has been refocused from an *educational studio* into a general, user-friendly
`idea → content` engine.** You give it an idea + a spec (format: 2D/3D · talking-head/movie ·
social post · combo; platform; channel); it writes a **script you vet/edit**; then it produces
the content with your local tools, using **local LLMs as the brain** (no cloud). Goal:
effortless new channels, full transparency, a self-improving memory — toward **$6k/month in 6
months**.

- **The new home is [`content_engine/`](content_engine/SYSTEM_MAP.md)** — start at its
  `SYSTEM_MAP.md` for the live, transparent picture (flow, agents, tools, brain, roadmap).
- **Clean slate done:** ~91 GB of produced content purged (the obsolete 2D experiments + the
  AP-Stats "Significant" show). The system, tools, skills, and asset library were kept.
- **Status:** Phase 0 (purge) ✓ · Phase 1 (engine home, system map, LLM client, scriptwriter
  agent) ✓ · Phases 2–6 (tools+MCP, director agent, idea→content orchestrator, memory, channel
  factory) ✓ — tracked in `content_engine/SYSTEM_MAP.md`.
- **Social pipeline shipped (2026-06):** native 9:16, no title card, burned sound-off **karaoke
  captions** + fact-based hook overlay + vertical thumbnail (`content_engine/finish.py`), per-shot
  punch-in motion, **topical B-roll** image cutaways on alternating lines (`02-pipeline/broll_images.py`,
  **ComfyUI local-gen** (dreamshaper_8, ~9s/img, always on-topic) + Openverse/Wikimedia stock
  fallback — `BROLL_BACKEND`=comfyui|stock|auto), even-spread gender-consistent
  presenter-pool casting variety, a **final-output quality gate** (`content_engine/qa.py`), and a
  posting-ready `publish.json` (caption + hashtags) per run (`content_engine/publish.py`) surfaced to
  Paperclip (one canonical project per channel). Proven by a 10-piece `daily-curiosities` batch.
  One command: `engine.py make --format social`.
- **Distribution + self-improvement:** `content_engine/poster.py` posts shorts (DRY-RUN default;
  `--live` + `config/credentials.json` for real TikTok/YouTube upload — setup in `POSTING_SETUP.md`,
  one-time OAuth via `auth_youtube.py`). `content_engine/analytics.py` ingests per-post metrics →
  aggregates by voice/avatar/hook/length/B-roll → writes data-driven learnings back to the
  scriptwriter + director, closing the self-improvement loop.
- **Autonomous scheduler:** `content_engine/scheduler.py` (cron: daily 10:00, `SCHEDULER.md`) rotates
  channels, draws hand-verified `idea_seeds.txt` (LLM overflow), and produces a batch hands-free —
  auto-GENERATE, manual-POST (finished shorts queue for review). **2 channels live**
  (daily-curiosities, Buried History) + midnight-tales; new channels = `new_channel.py` + a batch.
- **Always-on stack:** the mlx LLM servers (:8000 32B/:8001 Coder/:8002 7B) + ComfyUI (:8188) run as
  **launchd agents** (`~/Library/LaunchAgents/com.deparadigm.*`, RunAtLoad+KeepAlive) with a
  `ensure_stack.sh` **watchdog** (cron every 10 min) that kickstarts any down service — so the daily
  scheduler runs unattended. Details + gotchas in `content_engine/SERVICES.md`.
- **Sections 1–11 below** document the **underlying platform** (mlx brain, business-unit/channel
  plumbing, Blender/Manim/Kokoro producers, the integrated 3D pipeline) that the Content Engine
  builds on. They remain accurate for the infrastructure; only the *framing/identity* changed
  from "educational" to "general content."
>
> **Read this first if you feel the project has "drifted."** You're right — see
> [§2 The System-vs-Content Reckoning](#2-the-system-vs-content-reckoning). This doc names the
> drift explicitly and shows how to re-converge.

---

## 1. What this project is

**AI_PRODUCER** (brand: **DeParadigm Media**) is a **local-first, solo-operated AI media
production studio** that turns curriculum/scripts into finished educational videos across
several YouTube-style channels. It is designed as an **orchestrated agent mesh + media
pipelines**, not a single app.

- **Owner/operator:** a former AP Statistics / Calculus teacher (Security+ background), in China.
- **Host:** Apple-Silicon macOS, 128 GB RAM. Local LLM inference via `mlx-lm` (no cloud by default).
- **The four original channels (business units):**
  1. **Dev & Cloud** — serverless GCP/AWS, Security+ EdTech
  2. **AP Stats** — story-driven, multi-episode AP Statistics seasons (← *the show this session worked on*)
  3. **Translation** — automated Spanish/Mandarin dubbing
  4. **Ambient** — 10-hour deep-focus coding loops
- **Canonical platform briefing:** [`AGENTS.md`](AGENTS.md) (read it for infra detail).
- **Folder/registry source of truth:** [`00_CORE/business_units.yaml`](00_CORE/business_units.yaml)
  + [`00_CORE/PROJECT_ORGANIZATION.md`](00_CORE/PROJECT_ORGANIZATION.md).

There are **two distinct production pipelines** in this repo (this is the crux of the drift):

| | **2D pipeline** (original platform) | **3D pipeline** (built this session) |
|---|---|---|
| Entry point | `01_SKILLS/pipeline_orchestrator.py` | `02-pipeline/produce.py` |
| Look | 2D composited (ComfyUI art + PIL) | 3D Blender (VRoid characters, anime outline) |
| Integration | wired into Paperclip / business units / gateway | **standalone** — not yet wired into the platform |
| Status | full 14-step DAG exists; output parked as "obsolete experiments" | working; produced *Significant* Ep1 |

---

## 2. The System-vs-Content Reckoning

**Your concern is correct and worth stating plainly:** over this session the work shifted from
*building/extending the system* to *producing one piece of content* (AP Stats Episode 1,
"The Whale"). Both a system and content were built — but it's important to see which is which.

### What is genuinely a reusable SYSTEM
- **`02-pipeline/` + the `01-scripts/bl_*` engine** — a real *script → video* pipeline:
  parser → coverage planner → Kokoro VO → one generic Blender engine + set registry +
  motion/acting library → Manim B-roll registry → ffmpeg assembler → stitch → captions →
  distribution. Driven by a per-show config (`show_bible.json`). **This is a system.** It can
  produce *any* screenplay in the supported format, given registry entries for its
  locations/B-rolls. (Full detail in [§6](#6-the-3d-pipeline-what-was-built-this-session).)
- **The pre-existing platform** — `01_SKILLS/pipeline_orchestrator.py` (14-step 2D/3D DAG),
  the Paperclip company/agent model, OpenClaw gateway, mlx inference, Postgres ledgers,
  governance, knowledge graph, ~80 Python bridge modules + ~250 skill `.md` files. **This is a
  (large) system too** — and it's *running* (see [§8](#8-operational-state-whats-actually-running)).

### What is CONTENT (one-offs, not systems)
- **`Significant` Episode 1** — the polished, **hand-built** 2.5-min episode
  (`business_units/deparadigm-media/ap-stats/production/S01E01/09-deliver/S01E01_FULL.mp4`).
  Much of it was authored shot-by-shot before the pipeline existed. It is the *reference
  artifact*, not the system.
- **The Manim B-roll scenes** (`manim_ep1_broll1/2/3.py`), the season-seed corkboard, the tag
  phone graphic — **bespoke to Ep1**. Reusable *as a pattern*, not as content.
- **The parked 2D experiments** in `05_PROJECTS/` — earlier batch outputs, now obsolete.

### The drift, named
1. **A second pipeline was built parallel to the first, not integrated.** The new 3D pipeline
   (`02-pipeline/`) does **not** use `pipeline_orchestrator.py`, the Paperclip projects, the
   business-unit `production/<run>/01-scripts…09-deliver` tree, the gateway, or the Postgres
   ledgers. It writes to `/tmp` and to the ap-stats `09-deliver/` folder directly.
2. **Effort concentrated on one show's content** (Significant Ep1) rather than on the
   cross-channel system or the agent mesh.
3. **Two of the four channels** (Translation, Ambient) and the Dev&Cloud channel got no
   system work this session.

### How to re-converge on system-building (recommendation)
- **Integrate the 3D pipeline into the platform** instead of running it standalone:
  - Make `produce.py` write into `business_units/<company>/<unit>/production/<run>/` using the
    `01-scripts…09-deliver` convention (so it matches every other unit).
  - Register it as **mode `3d`** under `pipeline_orchestrator.py` (which already advertises a 3D
    mode) so there is *one* command surface, dependency tracking, dry-run, and resume.
  - Log runs to the Postgres production ledger and surface them in the dashboard like the rest.
- **Generalize beyond one show:** the `show_bible.json` pattern already supports new shows —
  prove it by driving a *different* channel's script through it.
- **Decide the canonical look** (2D vs 3D). Right now both exist; the studio should pick one as
  the default channel pipeline (or map look→channel) so they stop diverging.

Everything below is the map you need to act on that.

---

## 3. Architecture — the layers

```
┌───────────────────────────────────────────────────────────────────────────┐
│ L5  CONTENT          Significant Ep1 (hand-built) · parked 2D experiments    │
├───────────────────────────────────────────────────────────────────────────┤
│ L4  PRODUCTION       2D pipeline (pipeline_orchestrator.py, 14-step DAG)     │
│     PIPELINES        3D pipeline (02-pipeline/produce.py)  ← NEW, standalone │
├───────────────────────────────────────────────────────────────────────────┤
│ L3  MEDIA ENGINES    Blender 5.1 · Manim · FFmpeg · Kokoro/OpenVoice ·       │
│                      ComfyUI · MediaPipe/ARKit mocap · ONNX upscale          │
├───────────────────────────────────────────────────────────────────────────┤
│ L2  AGENT MESH       ~250 skill .md defs + ~80 Python bridges (01_SKILLS) ·  │
│                      library/ personas · understand_anything · graphify      │
├───────────────────────────────────────────────────────────────────────────┤
│ L1  PLATFORM/INFRA   Paperclip companies/agents (:3100) + bridge (:3101) ·   │
│                      OpenClaw gateway (54 actions) · mlx-lm (:8000-8002) ·   │
│                      Postgres ×2 (:5432 production, :5433 governance) ·      │
│                      Docker peripheral stack · business_units registry       │
└───────────────────────────────────────────────────────────────────────────┘
```

- **L1–L2** are the **platform**: how work is organized (companies → business units),
  dispatched (gateway/bridge), reasoned (local LLMs), and tracked (Postgres, governance).
- **L3** are the **media engines** — the actual renderers/synths.
- **L4** are the **two pipelines** that wire engines into a script→video flow.
- **L5** is **content**.

The recent 3D work added a new L4 pipeline and a lot of L5 content; it largely did **not**
touch L1–L2.

---

## 4. Repository map (every top-level entry)

| Path | Role | System / Content / Scaffold |
|---|---|---|
| `AGENTS.md` | Canonical platform briefing (read first for infra) | **System docs** |
| `00_CORE/` | Identity, monetization blueprint, **business_units.yaml registry**, PROJECT_ORGANIZATION | **System docs** |
| `01_SKILLS/` | ~80 Python bridge modules + ~250 skill `.md` defs (the agent mesh + 2D pipeline) | **System** |
| `01-scripts/` | **The 3D Blender engine + sets + motion/acting lib + Manim B-rolls** (built this session) | **System** |
| `02-pipeline/` | **The 3D script→video orchestrator** (produce.py, show_bible.json, distribute.py, README) | **System** |
| `02_CURRICULUM/` | Curriculum content (symlink aliases into business_units `knowledge/`) | Content/aliases |
| `03_ASSETS/` | Rendered media, FCPXML handoffs, ComfyUI layouts, vendor repos | Content/assets |
| `04_PHYSICAL/` | `openclaw/` robotic-claw hardware abstraction | System (niche) |
| `05_GOVERNANCE/` | `paperclip/` corporate governance, cap tables, expense ledger (port 5433) | **System** |
| `05_PROJECTS/` | **Parked 2D experiment outputs** per channel (obsolete) | Content (obsolete) |
| `06_SHARED_ASSETS/` | **VRoid characters, environments, Kokoro models, music/sfx stems** (the 3D asset library) | **System assets** |
| `06_SPATIAL/` | `vtuber_twin/` UDP spatial streaming + pyglet IK viewport | System (niche) |
| `07_PAPERCLIP/` | The Paperclip company package (`companies/deparadigm-media/`) + sync scripts | **System** |
| `08_RENDER_FARM/` | Render-farm dispatch config | System |
| `business_units/` | **SOURCE OF TRUTH for projects.** `<company>/<unit>/{knowledge,production,assets,BRIEF}` | **System + content** |
| `runtime/` | Agent runtimes + **paperclip_bridge.py** (the :3101 bridge) | **System** |
| `library/` | Agent personas (`agents/<role>/AGENTS.md`) + skill library | **System** |
| `ComfyUI/`, `OpenVoice/`, `env/`, `node_modules/` | Vendored tools + Python venv | Vendor |
| `MCP`, `Makefile`, `studio`, `LAUNCH_STUDIO.command`, `HEARTBEAT.md` | Launchers / studio entry points | System |
| `.docker/` | Docker Compose for OpenClaw, Playwright, Open WebUI, Postgres | System |

> **Where the show lives:** `business_units/deparadigm-media/ap-stats/`
> — `knowledge/` (notes), `SHOW_BIBLE.md`/`SEASON_01_OUTLINE.md`/`CAST.md` (writers' room),
> `production/S01E01/` (the run: `01-scripts/screenplay.md` … `06-audio/` … `07-render/` …
> `09-deliver/`).

---

## 5. The platform (L1–L2): the original system

**This is what already exists and is running.** Most of it predates this session.

- **Companies → Business Units (channels).** A *company* = a Paperclip company + a package in
  `07_PAPERCLIP/companies/<company>/`. A *business unit* = a Paperclip Project + a same-named
  Team + a folder `business_units/<company>/<unit>/`. Registry: `00_CORE/business_units.yaml`
  (company `deparadigm-media` with units: dev-cloud, ap-stats, translation, ambient,
  sarcastic-me, book-review, sarcastic-commentary, …).
- **Paperclip** (`:3100`) is the agent/company manager; the **bridge** `runtime/agents/paperclip_bridge.py`
  (`:3101`) connects it to the filesystem and auto-provisions unit folders.
- **OpenClaw gateway** — a 54-action router (`~/.openclaw/skills/media_production_gateway/`)
  exposing `pipeline`, `init_project`, `generate_storyboard`, `auto_dub`, `body_mocap`,
  `composite_2d`, `parallel_render`, `distribute`, `dashboard`, etc.
- **Local inference** — `mlx-lm` on `:8000` (Llama4 Scout), `:8001` (Qwen 32B), `:8002` (Qwen 7B).
  All bridge modules call `http://127.0.0.1:8000/v1`; cloud APIs are off by default.
- **Postgres ×2** — `:5432` production tracking (`production_tracks`, `media_assets`),
  `:5433` governance/knowledge-graph.
- **Agent mesh (`01_SKILLS/`)** — ~250 skill `.md` files (each a narrowly-scoped agent persona
  with a 5-line briefing header) + ~80 Python bridge modules. Key system modules:
  `skills.py` (vault/LLM), `orchestrator.py` (curriculum daemon), `pipeline_orchestrator.py`
  (the 2D/3D DAG runner), `solocorn_media_bridge.py` (FCPXML/FFmpeg master), `init_project.py`,
  `storyboard_generator.py`, `auto_dubbing_pipeline.py`, `body_mocap.py`, `distribution_formatter.py`,
  `episode_manager.py`, `error_recovery.py`, `test_suite.py` (121 tests),
  `graphify/knowledge_graph.py`, `understand_anything/` (ingest + autonomous Manim codegen).

### The 2D pipeline (the original L4)
`01_SKILLS/pipeline_orchestrator.py` runs a **14-step DAG**:
`init → storyboard → characters → backgrounds → dubbing → music → sfx → composite → color →
subtitles → thumbnails → assemble → distribute`, with dependency tracking, dry-run, parallel
jobs, and resume-from-failure. It supports `--mode 2d` and advertises `--mode 3d`. Its 2D
outputs are the parked experiments in `05_PROJECTS/`.

---

## 6. The 3D pipeline (what was built this session)

A **new, standalone** script→video system, focused on the AP Stats show. It is genuinely a
system — but currently parallel to the platform (see the drift note in §2).

### Command surface
```bash
# one scene
env/bin/python3 02-pipeline/produce.py --script <screenplay.md> --scene "KITCHENETTE" --out OUT/
# whole episode (all mapped scenes in order + title card → EPISODE.mp4 + EPISODE.srt)
env/bin/python3 02-pipeline/produce.py --script <screenplay.md> --out OUT/ --episode S01E01
# platform deliverables (9:16 vertical, thumbnail, burned captions)
env/bin/python3 02-pipeline/distribute.py OUT/S01E01.mp4 --srt OUT/S01E01.srt --title "…"
```
Full usage + extension docs: [`02-pipeline/README.md`](02-pipeline/README.md).

### Flow
```
screenplay.md ─▶ parse ─▶ scenes+beats ─▶ coverage planner ─▶ shot list
                                                                  │
   show_bible.json (cast→avatar/voice/gesture, location→set,      │
                    broll→manim, blocking, coverage templates)    ▼
                              ┌── Kokoro VO per line (neural TTS, local)
                              ├── bl_scene_engine.py  (ONE generic Blender renderer)
                              │      ├─ bl_sets.py        (set registry: office/kitchenette/
                              │      │                     cafe/conference/whiteboard/studio)
                              │      └─ bl_anim_lib.py    (motion + ACTING standard)
                              ├── manim_ep1_broll*.py  (stat-insert B-rolls)
                              └── ffmpeg assemble (cut + music + fades) ─▶ scene.mp4
                                          └─▶ stitch episode + captions ─▶ distribute
```

### Components (`01-scripts/` + `02-pipeline/`)
| File | Role |
|---|---|
| `02-pipeline/produce.py` | Orchestrator: parse → plan → VO → render → assemble → stitch → captions |
| `02-pipeline/show_bible.json` | Per-show config (cast, locations→sets, B-rolls, blocking, coverage) |
| `02-pipeline/distribute.py` | Reach: 9:16 vertical, thumbnail, caption burn-in |
| `02-pipeline/README.md` | Pipeline usage + how to extend |
| `01-scripts/bl_scene_engine.py` | ONE generic Blender renderer (JSON-config driven) |
| `01-scripts/bl_sets.py` | Set registry — location id → 3D set builder |
| `01-scripts/bl_anim_lib.py` | The look/motion/**acting** standard (see below) |
| `01-scripts/tts_kokoro.py` | Kokoro neural-TTS helper |
| `01-scripts/manim_ep1_broll1/2/3.py` | The three stat-insert B-rolls (Ep1-specific) |
| `01-scripts/bl_*_scene.py` | The 5 original **bespoke** scene scripts (superseded by the engine; kept as reference) |

### What it does automatically
Parse a screenplay → stage characters → plan **shot/reverse-shot** coverage → **emotional
performance** (parentheticals → VRoid brow/eye blendshapes) + **eye-lines** → **Kokoro VO** per
line → **lip-sync + procedural body motion** (breathing, weight-shift, speech gestures;
per-character gesture scale) → 3-point lighting → **graphic beats** (title/season-seed/tag) →
cut + music + fades → **stitch the episode** → **captions (SRT)** → **vertical + thumbnail**.
With a **render cache** (skip unchanged shots) and a **black-frame quality gate** (retry).

### The animation/acting standard (`bl_anim_lib.py`)
- `apply_body_motion(...)` — breathing, weight-shift, organic head, speech-driven forearm
  gestures, relaxed hands; `gesture=` scales per character (Maya 1.0, Nina 0.9, Okafor 0.5,
  Investor 0.4). Tuning the whole show's physicality is a one-file change.
- `apply_emotion(kb, emotion)` + `emotion_from_paren()` — parenthetical → brow/eye expression
  (mouth left free for lip-sync).
- `head_yaw_to()` + `head_yaw=` — eye-lines toward the scene partner.
- **Rig facts learned:** invoke Blender via the `.app` binary, not the symlink; elbow bends on
  the LowerArm **local Y** axis; keep head pitch small so faces don't drop behind bangs.

### Extending the 3D pipeline
- **New character** → add to `show_bible.characters` (`vrm`, `voice`, `gesture`).
- **New location** → add a builder to `bl_sets.SETS` + map `"LOCATION|TIME"` in the bible.
- **New B-roll** → add a `manim_*.py` Scene + register it.
- **New show** → a new `show_bible.json` (engine/sets/motion/assembler are shared).

### Honest limits of the 3D pipeline
- Coverage is template-based (establish + shot/reverse for ≤2 speakers; 3+ uses first two).
- Action lines aren't auto-staged (only dialogue/B-roll/graphic beats drive coverage).
- Special framings (desk / over-the-shoulder / inserts) still benefit from per-scene tuning.
- **Arbitrary B-roll** (a new concept's stat-viz) needs a hand-authored Manim module.
- **Outfit/character design** is a hard limit — VRoid garments are texture/MToon-locked;
  runtime recolor has no visible effect; real wardrobe change needs VRoid Studio re-export.
- **Stand-in cast** — Okafor/Investor are stylized young avatars, not their scripted ages.
- **Not integrated** into the platform (see §2).

---

## 7. The content: *Significant* — AP Stats S01E01 "The Whale"

The show is a **character-driven serialized drama that teaches one AP Stats unit per episode**
(not explainer videos). Writers'-room is locked: `SHOW_BIBLE.md`, `SEASON_01_OUTLINE.md`,
`CAST.md`, and the Ep1 screenplay (`production/S01E01/01-scripts/screenplay.md`).

**Ep1 teaches Unit 1 (mean vs. median)** through the drama: Maya's startup pitches a "$92k
average user"; her journalist friend Nina pokes the number; the whale outliers surface; Prof.
Okafor teaches the median; Maya wins an investor with the honest $38k. Three Manim stat-inserts
fire at the "aha" beats.

**Key deliverables** (`…/ap-stats/production/S01E01/09-deliver/`):
- `S01E01_FULL.mp4` (≈2:38) — the polished, hand-built reference episode (Kokoro voices,
  per-character motion).
- `S01E01_kitchenette_PIPELINE.mp4` — the same scene produced **by the 3D pipeline** from the
  script (the proof the system works).
- Per-scene files: `S01E01_cold_open / kitchenette / desk_whale / median / bridge / pitch /
  seed / tag`.

Cast/voices (in `show_bible.json`): Maya (purple VRoid, `af_heart`), Nina (red hoodie,
`af_bella`), Okafor (`bm_george`), Investor (`am_onyx`).

---

## 8. Operational state (what's actually running)

Checked 2026-06-25 — **the platform is live**, not dormant scaffold:

| Service | Port | State |
|---|---|---|
| mlx-lm (Llama4 Scout / Qwen 32B / Qwen 7B) | 8000 / 8001 / 8002 | **UP** |
| Postgres — production tracking | 5432 | **UP** |
| Postgres — governance / graphify | 5433 | **UP** |
| Paperclip company manager | 3100 | **UP** |
| Paperclip ↔ filesystem bridge | 3101 | **UP** |
| ComfyUI | 8188 | **UP** |
| OpenClaw core watcher | 18789 | **UP** |

Media engines verified working this session: **Blender 5.1.2**, **Manim 0.20.1**,
**FFmpeg**, **Kokoro** (model files in `06_SHARED_ASSETS/ai-models/kokoro/`).

---

## 9. How to run things (quick reference)

```bash
# ── 3D pipeline (the new system) ───────────────────────────────────────────
env/bin/python3 02-pipeline/produce.py --script <screenplay.md> --out OUT/ --episode S01E01
env/bin/python3 02-pipeline/distribute.py OUT/S01E01.mp4 --srt OUT/S01E01.srt --title "…"

# ── 2D pipeline (the original platform) ────────────────────────────────────
python3 01_SKILLS/pipeline_orchestrator.py dry-run <project_slug> --mode 2d
python3 01_SKILLS/pipeline_orchestrator.py run <project_slug> --mode 2d --title "…"

# ── platform ops ───────────────────────────────────────────────────────────
python3 01_SKILLS/test_suite.py run                 # 121 syntax/import/functional tests
python3 01_SKILLS/provision_business_unit.py list    # companies/units
python3 01_SKILLS/init_project.py create <run> --company deparadigm-media --unit ap-stats --title "…"
# Blender (always via the .app binary, not the symlink):
/Applications/Blender.app/Contents/MacOS/Blender -b --python 01-scripts/bl_scene_engine.py -- <cfg.json>
```

---

## 10. Honest assessment & next moves

**What's strong**
- The platform (L1–L2) is real, running, and well-organized (companies → units, registry,
  ledgers, gateway, local inference).
- The new 3D pipeline (L4) genuinely turns a screenplay into a finished, captioned, distributable
  episode — with acting, motion, B-rolls, and per-show config. That's a system, not a one-off.

**What drifted (and the fix)**
- The session over-indexed on **one show's content** and built a **second, unintegrated
  pipeline**. To get back to system-building:
  1. **Integrate** `produce.py` into the platform: write into
     `business_units/<company>/<unit>/production/<run>/` (the `01-scripts…09-deliver` tree),
     register as `pipeline_orchestrator.py --mode 3d`, log to the Postgres ledger, surface in
     the dashboard.
  2. **Pick the canonical look** (2D vs 3D) per channel so the two pipelines stop diverging.
  3. **Prove generality** by driving a *non-AP-Stats* channel's script through the 3D system.
  4. **Address the hard limits deliberately** (cast design via VRoid Studio; a small library of
     reusable B-roll templates; OTS/insert coverage in the planner).

**Bottom line.** You have (a) a running studio platform, (b) a working 3D script→video system,
and (c) one finished episode that proves the look. The remaining work to feel like "a system,
not content" is **integration and generalization**, not more bespoke episodes.

---

## 11. Pointers

- Platform infra & conventions → [`AGENTS.md`](AGENTS.md)
- Folder/registry truth → [`00_CORE/PROJECT_ORGANIZATION.md`](00_CORE/PROJECT_ORGANIZATION.md),
  [`00_CORE/business_units.yaml`](00_CORE/business_units.yaml)
- 3D pipeline usage/extension → [`02-pipeline/README.md`](02-pipeline/README.md)
- The show's writers' room → `business_units/deparadigm-media/ap-stats/` (`SHOW_BIBLE.md`,
  `SEASON_01_OUTLINE.md`, `CAST.md`, `production/S01E01/01-scripts/screenplay.md`)
- Session memory (the build journey + gotchas) →
  `.claude/projects/-Users-nazeera-Documents-AI-PRODUCER/memory/` (`MEMORY.md` index)
