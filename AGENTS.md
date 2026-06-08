# AGENTS.md — Solocorn AI Producer Workspace

> This file is the canonical briefing for any AI coding agent working inside this repository. Read it in full before modifying code, generating files, or dispatching pipelines. When instructions here conflict with generic assumptions, this file wins.

---

## Project Overview

This repository is **Solocorn**, a local-first, solo-operated AI media production studio. The owner is a former high-school mathematics educator (AP Statistics, Calculus AB, Pre-Calculus) and CompTIA Security+ professional based in China, producing educational video content across four monetization channels:

1. **Developer/Cloud EdTech** — Serverless GCP architectures, AWS transitions, Security+ compliance.
2. **AP Statistics Movie Series** — Cinematic, story-driven multi-episode seasons mapped to the official College Board AP Stats syllabus.
3. **Multi-Language Translation Factory** — Automated Spanish and Mandarin dubbing via XTTS v2 voice cloning.
4. **Passive Deep-Focus Atmospheric Loops** — 10-hour coding ambience channels.

The workspace is **not** a traditional monolithic application. It is an **orchestrated agent mesh**: ~250 Markdown skill definitions, Python bridge modules, Docker containers, PostgreSQL ledgers, and headless media renderers (Manim, FFmpeg, Blender, Godot, 3ds Max) that cooperate to turn raw curriculum notes into finished video assets and FCPXML timelines.

**Host Platform**: Apple Silicon macOS (128 GB unified RAM). All local LLM inference runs through a native `mlx-lm` server on `http://127.0.0.1:8000/v1`. Docker is used for peripheral services only; inference deliberately bypasses containers to exploit full hardware memory speeds.

---

## Repository Layout

```
AI_PRODUCER/
├── 00_CORE/                    # Identity, monetization blueprint, student learner profiles
├── 01_SKILLS/                  # Agent skill definitions (.md) + Python bridge modules
│   ├── graphify/               # Knowledge-graph engine (PostgreSQL-backed nodes/edges)
│   ├── understand_anything/    # Document ingestion + autonomous Manim code generation
│   ├── skills.py               # Vault CRUD, frontmatter parser, Zotero bridge, oMLX wrapper
│   ├── solocorn_media_bridge.py# Media pipeline dispatcher, FCPXML builder, audio mastering
│   ├── orchestrator.py         # Sovereign curriculum engine (ingest → voice → render → mux)
│   ├── lesson_compiler.py      # LLM-driven lesson-blueprint generator
│   ├── script_processor.py     # Markdown script → JSON manifest compiler
│   ├── curriculum_runner.py    # Batch executor for multi-lesson queues
│   ├── init_database.py        # PostgreSQL schema bootstrap for production tracking
│   ├── openclaw_bridge.py      # OpenClaw daemon JSONL watcher / normalization bridge
│   ├── render_scenes.py        # Manim scene registry (classes appended by code generator)
│   ├── test_omlx.py            # Inference health check
│   ├── test_ingestion.py       # Raw-source pipeline test
│   ├── test_timeline.py        # FCPXML compilation test
│   └── setup_env.sh            # Bootstrap script for local Python venv + dependencies
├── 02_CURRICULUM/              # Curriculum content segmented by business track
│   ├── 01_SOLOCORN_EDTECH/
│   ├── 02_AP_STATS_MOVIE/
│   ├── 03_DEVOPS_CONTROL/
│   ├── 04_VERTICAL_FARMING/
│   ├── compiled_wiki/          # Canonical processed markdown vault (Obsidian-compatible)
│   └── raw_sources/            # Drop-zone for unprocessed ingest (web, YouTube)
├── 03_ASSETS/                  # Rendered media, handoffs, ComfyUI layouts, vendor repos
│   ├── _HANDOFF_FCP_CAPCUT/    # Final Cut Pro XML timelines and project stubs
│   ├── comfyui_layouts/        # JSON layout definitions for ComfyUI
│   ├── vendor_repos/           # Git submodules (obsidian-skills, agency-agents, etc.)
│   └── visuals_manifest.json   # Schema-tracked scene asset manifest
├── 04_PHYSICAL/
│   └── openclaw/               # Robotic claw hardware abstraction layer
├── 05_GOVERNANCE/
│   └── paperclip/              # Corporate governance / expense tracking / cap tables
├── 06_SPATIAL/
│   └── vtuber_twin/            # UDP spatial streaming, IK viewport, telemetry canvas
├── 07_PAPERCLIP/               # Paperclip company package + bridge adapter
│   ├── companies/
│   │   └── solocorn-studios/   # agentcompanies/v1 company (agents, skills, projects, teams)
│   └── scripts/                # normalize_skills.py, create_org_chart.py, paperclip_bridge.py
├── .docker/                    # Docker Compose + gateway routing + nginx staging configs
├── env/                        # Python 3.14 virtual environment (committed historically)
├── media/                      # Manim cache output target (videos, images, audio, Tex)
└── .manim_cache/               # Secondary Manim render cache
```

### Path Constants Used Across Python Modules

Nearly every Python bridge file derives these paths from `Path(__file__).resolve().parent.parent`:

- `WORKSPACE_ROOT` — repository root
- `CORE_VAULT` — `00_CORE/`
- `SKILLS_DIR` — `01_SKILLS/`
- `WIKI_DIR` — `02_CURRICULUM/compiled_wiki/`
- `RAW_SOURCES_DIR` — `02_CURRICULUM/raw_sources/`
- `HANDOFF_DIR` — `03_ASSETS/_HANDOFF_FCP_CAPCUT/`

**Do not hard-code absolute user paths** (e.g., `/Users/nazeera/...`) in reusable modules. Use the relative resolution pattern above.

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| Language | Python 3.14 | Primary automation and bridge logic |
| Local LLM | `mlx` + `mlx-lm` | Three native inference servers: `:8000` Llama4 Scout, `:8001` Qwen 32B, `:8002` Qwen 7B |
| Container Runtime | Docker Compose | OpenClaw daemon, Playwright scouter, Open WebUI, Postgres |
| Database | PostgreSQL 15 | Two instances: port 5432 (production tracking), port 5433 (governance) |
| Math Animation | Manim (Community) | Vector math/science video generation |
| Video/Audio | FFmpeg | Transcoding, muxing, loudnorm, color grading (lut3d/eq/curves) |
| Voice Synthesis | Kokoro TTS (23 voices) + OpenVoice (cloned) | Local neural TTS; XTTS v2 for Mandarin/Spanish |
| Image Generation | ComfyUI (`:8188`) | SDXL Base + Flux-dev for storyboards, characters, backgrounds |
| 3D/Spatial | Blender 5.1.2, pyglet, UDP sockets | Character import, animation, Cycles rendering, VTuber twin |
| Motion Capture | MediaPipe Pose Landmarker (33 landmarks) + ARKit iFacialMocap | Body joint angles → Blender armature; 52 blend shapes via UDP |
| AI Upscale | ONNX Runtime (CoreML) | Real-time super-resolution for rendered frames |
| Research | Zotero Desktop + SQLite | Direct SQLite read-only queries for bibliography export |
| Agent Orchestration | Paperclip + OpenClaw gateway | 54-action gateway router (`~/.openclaw/skills/media_production_gateway/index.js`) |
| NLE Integration | Final Cut Pro XML (FCPXML v1.9–1.11) + EDL | Timeline assembly and project interchange; DaVinci via EDL fallback |

### Key Python Dependencies

- `mlx`, `mlx-lm` — Local model serving (3 concurrent servers)
- `psycopg2` — PostgreSQL connectivity
- `urllib3` — HTTP client (no `requests` in venv; all HTTP uses `urllib`)
- `beautifulsoup4`, `html5lib` — Web ingestion
- `PyYAML` — Frontmatter parsing
- `kokoro` — Local neural TTS
- `onnxruntime` — CoreML-accelerated inference
- `mediapipe` — Pose landmarker and Tasks API
- `PIL`, `numpy` — Image analysis (no `cv2` in venv)
- `pyglet` — Spatial viewport rendering

There is **no `pyproject.toml`, `setup.py`, `package.json`, or `Makefile`**. Dependency installation is handled by `01_SKILLS/setup_env.sh`, which creates a `.venv`, installs packages, and freezes to `requirements.txt`.

---

## Build and Run Commands

### One-Time Environment Setup

```bash
cd /Users/nazeera/Documents/AI_PRODUCER
bash 01_SKILLS/setup_env.sh
source .venv/bin/activate
```

### Start Local Inference Server (Required Before Most Operations)

```bash
# Example using mlx_lm.server with a local 4-bit model
mlx_lm.server --model mlx-community/Qwen2.5-Coder-7B-Instruct-4bit --port 8000
```

All bridge modules assume this endpoint is live at `http://127.0.0.1:8000/v1`. Fallback servers on ports 8001 and 8002 are available for load distribution.

### Start Docker Peripheral Stack

```bash
cd .docker
docker compose up -d
```

Services brought up:
- `openclaw_core_watcher` — port 18789
- `scouter_browser_sandbox` — port 30005 (Playwright)
- `open_webui_cockpit` — port 3000
- `paperclip_studio_database` — port 5433

### Initialize / Reset PostgreSQL Tracking Schema

```bash
python3 01_SKILLS/init_database.py
```

This creates `production_tracks` and `media_assets` tables on **port 5432** (localhost, user `postgres` / `postgres`).

### Run Full 2D Pipeline (One Command)

```bash
# Dry-run to preview what would execute
python3 01_SKILLS/pipeline_orchestrator.py dry-run <project_slug> --mode 2d

# Execute the full 14-step pipeline
python3 01_SKILLS/pipeline_orchestrator.py run <project_slug> --mode 2d --title "My Episode"

# Resume from a specific step after failure
python3 01_SKILLS/pipeline_orchestrator.py run <project_slug> --mode 2d --resume-from composite
```

Pipeline steps (2D): `init` → `storyboard` → `characters` → `backgrounds` → `dubbing` → `music` → `sound_design` → `composite` → `interpolate` → `color_grade` → `subtitles` → `thumbnails` → `assemble` → `distribute`.

### Gateway Actions (OpenClaw)

The gateway at `~/.openclaw/skills/media_production_gateway/index.js` exposes 54 actions. Key ones:

| Action | Purpose |
|--------|---------|
| `pipeline` | Run `pipeline_orchestrator.py` via gateway |
| `init_project` | Scaffold new project directories |
| `generate_storyboard` | ComfyUI-powered shot frame generation |
| `auto_dub` | Kokoro/OpenVoice dialogue generation |
| `body_mocap` | MediaPipe pose → Blender keyframes |
| `composite_2d` | PIL-based 2D animation compositing |
| `parallel_render` | Multi-core frame rendering |
| `distribute` | Auto-export YouTube/TikTok/Instagram/LinkedIn versions |
| `dashboard` | Web UI for shot status and pipeline stages |
| `preview` | Generate HTML review page for a project |
| `run_tests` | Execute automated test suite |

### Initialize Governance Schema (Port 5433)

```python
from paperclip.governance_core import PaperclipEnterpriseGovernor
g = PaperclipEnterpriseGovernor()
g.initialize_governance_ledger()
```

### Initialize Knowledge Graph Schema (Port 5433)

```python
from graphify.knowledge_graph import GraphifyEngine
e = GraphifyEngine()
e.initialize_graph_tables()
```

### Run Full Curriculum Pipeline (Daemon Mode)

```bash
python3 01_SKILLS/orchestrator.py
```

Loops forever, watching `02_CURRICULUM/raw_sources/` for new `.md`/`.txt` files, splitting syllabi into chapters, generating voice tracks, rendering Manim scenes, muxing with FFmpeg, and streaming spatial twin data.

### Run Automated Test Suite

```bash
# Full suite: syntax + import + functional tests for all 60+ modules
python3 01_SKILLS/test_suite.py run

# Specific category
python3 01_SKILLS/test_suite.py run --category 2d
python3 01_SKILLS/test_suite.py run --category integration

# Single script
python3 01_SKILLS/test_suite.py run --script pipeline_orchestrator
```

Current coverage: **121 tests** (118 syntax/import + 3 functional: init_project, orchestrator dry-run, error_recovery state tracking).

### Run Batch Lesson Factory

```bash
python3 01_SKILLS/curriculum_runner.py
```

Executes a hard-coded queue (`AP_STATS_SYLLABUS`) through `lesson_compiler.py` → orchestrator flow with timeout guards.

### Generate FCPXML Timeline from Assets

```bash
python3 01_SKILLS/solocorn_media_bridge.py
```

With no arguments, runs a standalone verification pass using test assets in `03_ASSETS/`.

### Start Paperclip Server & Bridge

```bash
# Start Paperclip (if not already running)
npx paperclipai run

# Start the Python bridge server (in another terminal)
cd /Users/nazeera/Documents/AI_PRODUCER
source env/bin/activate
python3 runtime/agents/paperclip_bridge.py
```

Paperclip UI: `http://localhost:3100`  
Bridge API: `http://localhost:3101`

### Re-import Company Package (after agent/skill changes)

The package's `agents/` and `skills/` folders are **not** stored on disk —
they are regenerated from the canonical `library/` via `sync_company.py`
(this avoids a 4.3MB duplicate). Always sync **before** importing:

```bash
# 1. Regenerate agents/ and skills/ from library/ into the package
python3 07_PAPERCLIP/scripts/sync_company.py --company solocorn-studios --all

# 2. Import the freshly-synced package into Paperclip
npx paperclipai company import --yes /Users/nazeera/Documents/AI_PRODUCER/07_PAPERCLIP/companies/solocorn-studios
```

---

## Testing Instructions

There are three small smoke tests in `01_SKILLS/`:

| Test File | What It Verifies | How to Run |
|-----------|------------------|------------|
| `test_omlx.py` | Local LLM server handshake on port 8000 | `python3 01_SKILLS/test_omlx.py` |
| `test_ingestion.py` | Raw-source sweep → compiled_wiki ingestion | `python3 01_SKILLS/test_ingestion.py` |
| `test_timeline.py` | FCPXML generation from hard-coded movie paths | `python3 01_SKILLS/test_timeline.py` |
| `test_bridge.py` | Paperclip bridge server health + vault ops | `python3 runtime/agents/test_bridge.py` |

**Automated test suite** (`test_suite.py`) provides syntax validation, import checks, and functional tests for all 60+ Python modules across 9 categories. No pytest/unittest required. Run `python3 01_SKILLS/test_suite.py run` before committing new bridge logic and verify `failed: 0`.

### Manual Integration Checklist

1. `mlx_lm.server` responding on port 8000 (`test_omlx.py`)
2. PostgreSQL accepting connections on ports 5432 and 5433
3. `manim` binary available on `$PATH` (check with `which manim`)
4. `ffmpeg` binary available on `$PATH` (check with `which ffmpeg`)
5. Docker Compose stack healthy (`docker compose ps`)
6. Paperclip server responding on port 3100 (`curl http://127.0.0.1:3100/api/health`)
7. Bridge server responding on port 3101 (`curl http://127.0.0.1:3101/health`)

---

## Code Style Guidelines

### Python

- **Python 3.14** syntax is assumed. Use modern type hints (`list[str]`, `dict[str, Any]`, `Path | None`).
- **Docstrings**: Every public function gets a triple-quote docstring explaining purpose, args, and return value.
- **Comments**: Use inline `# 🛡️ FIX:` or `# 🔗` tags to flag defensive guards and structural links. This convention is used heavily across the codebase.
- **String formatting**: Prefer f-strings. Use `json.dumps(..., indent=2, ensure_ascii=False)` for all JSON serialization to preserve Unicode.
- **Path handling**: Use `pathlib.Path` exclusively; no `os.path.join` in new code.
- **Error handling**: Wrap external I/O (HTTP, DB, subprocess) in try/except blocks that return actionable strings (e.g., `"ERROR: Direct local connection to native oMLX server failed. Details: ..."`).
- **Subprocess calls**: Always use `subprocess.run(..., check=False)` or `capture_output=True` with explicit `text=True`. Never use `os.system`.
- **Global paths**: Resolve via `Path(__file__).resolve().parent.parent` pattern; never embed `/Users/nazeera/...` in reusable modules.

### Markdown (Skill Files)

Every `.md` file under `01_SKILLS/` **must** contain a 5-line briefing header immediately below its title:

1. **Narrow specialty** — single domain this agent owns
2. **Exact target output directory** — repo-relative path for all deliverables
3. **Explicit stylistic tone constraints** — voice, register, forbidden phrases
4. **Prioritized asset folder paths** — ordered input directories
5. **Strict pause-and-confirm parameters** — values the agent must never guess

Example:

```markdown
> **Briefing Header**
> 1. Specialty: Infrastructure automation, CI/CD, SRE, DevOps tooling
> 2. Target output directory: `02_CURRICULUM/03_DEVOPS_CONTROL/`
> 3. Stylistic tone: Professional, precise, local-first engineering register
> 4. Prioritized asset paths: `03_ASSETS/` → `02_CURRICULUM/03_DEVOPS_CONTROL/`
> 5. Pause-and-confirm parameters: External storage mount point, frame resolution, codec bitrates
```

- Preserve all YAML frontmatter blocks (`agent_id`, `model_target`, `type`, `output_path`) when editing skill files.
- Use `##` for major sections and `###` for subsections.

### JSON / Manifests

- Pretty-print with 2-space indentation.
- Use `.json` extension for task manifests; name convention: `task_{track_name}_scene_{i}_{asset_name}.json`.

### SQL

- Use parameterized queries (`%s` placeholders) with `psycopg2`.
- Prefer `INSERT ... ON CONFLICT DO NOTHING/UPDATE` for idempotent schema bootstrapping.

---

## Security Considerations

### Credentials in Source Code

The **port 5433 governance/graphify credentials** are sourced from the environment, not hard-coded. They are read via `os.environ.get(...)` in `graphify/knowledge_graph.py`, `paperclip/governance_core.py`, and `health_check.py`, with values defined in the gitignored repo-root `.env`:

```
PAPERCLIP_DB_NAME=paperclip_governance
PAPERCLIP_DB_USER=paperclip_admin
PAPERCLIP_DB_PASSWORD=...        # set locally; never committed
PAPERCLIP_DB_HOST=127.0.0.1
PAPERCLIP_DB_PORT=5433
```

`docker-compose.yml` consumes the same values via `${PAPERCLIP_DB_*}` substitution from a gitignored `.docker/.env`. Both `.env` files are loaded at module import via `python-dotenv` (optional; falls back to the exported shell environment). To run any of these modules standalone, ensure `.env` exists or the variables are exported.

The **port 5432 production-tracking DB** is likewise env-sourced via `PRODUCTION_DB_*` (defaults `postgres`/`postgres`, a well-known local default), read in `init_database.py`, `solocorn_media_bridge.py` (`production_db_params()` helper), and `health_check.py`:

```
PRODUCTION_DB_NAME=postgres
PRODUCTION_DB_USER=postgres
PRODUCTION_DB_PASSWORD=postgres
PRODUCTION_DB_HOST=127.0.0.1
PRODUCTION_DB_PORT=5432
```

> **History note:** `***REMOVED***` was committed in earlier history. Moving it to `.env` removes it going forward but does **not** scrub it from past commits. If the GitHub remote (`Stephen-Nazieh/AI_PROD`) is or ever was public, treat that password as compromised: rotate it on the running container and scrub history with `git filter-repo`.

### API Keys

- `OPENAI_API_KEY=local_omlx_key_override` is a dummy string used only to satisfy OpenAI-compatible client libraries talking to the local `mlx-lm` server. It has no cloud value.
- `OPENCLAW_GATEWAY_TOKEN=***REMOVED-ROTATED-SEE-.docker/.env***` is a local Docker environment variable.

### Network Exposure

- The `mlx-lm` server on port 8000 binds to `127.0.0.1` by design. **Do not** expose it to `0.0.0.0` on untrusted networks.
- Docker containers use `host.docker.internal` to reach the host inference endpoint; this is acceptable on a single-user workstation but should be reviewed if the host firewall changes.
- PostgreSQL ports 5432 and 5433 are bound to localhost. Confirm `pg_hba.conf` rejects non-local connections if the containers are reconfigured.

### File System Guards

- `skills.py` skips hidden macOS files (`.DS_Store`, etc.) during raw-source processing.
- `.gitignore` excludes `env/`, `.env`, media binaries, and Docker Postgres data.
- **Never** commit raw video, audio, or model weights to Git.

### Inference Safety

- The `clean_raw_content()` function in `skills.py` dispatches raw text to a local LLM with a strict system instruction to preserve factual claims and not add commentary. When modifying this prompt, maintain the explicit prohibition against hallucinating new content.
- `ClaudeCodeAutomationBridge` generates executable Python code (Manim scenes) from LLM output. The bridge performs aggressive sanitization (dynamic indentation fixes, dangling parenthesis sealing, loose-word filtering). Any changes to the sanitizer logic must be tested against at least three generated scene classes before acceptance.

---

## Agent Handoff & Automation Conventions

### Handoff Metadata Block

When one agent passes authority to another inside a Markdown file, append this exact HTML-comment block:

```html
<!-- ::: AGENT_HANDOFF_METADATA_BLOCK :::
    "origin_agent": "agent_name",
    "target_agent": "next_agent",
    "execution_phase": "phase_status",
    "hardware_allocation": "128GB_RAM_MLX_NATIVE"
::: -->
```

The OpenClaw daemon treats modifications to `01_SKILLS/*.md` or `solocorn_media_bridge.py` as event triggers and may launch the Python media bridge loop automatically.

### QA Verdict Documents

QA agents generate PASS/FAIL verdicts as Markdown files in `03_ASSETS/_HANDOFF_FCP_CAPCUT/projects/`. A FAIL verdict includes:
- Enumerated issues with category, severity, description, and fix instruction
- Retry counter (max 3 attempts)
- Escalation clause if attempts are exhausted

---

## External Storage Topology

The local SSD is **not** the canonical write target for heavy I/O. The external RAID mount is:

```
/Volumes/SolocornRAID/03_ASSETS
```

All rendered frames, intermediate textures, geometry caches, and final delivery packages for 3D pipelines should target this path. The `pae_da_vinci` agent and all 3D format processors must bypass internal caches and write directly to the RAID.

---

## Common Pitfalls for Agents

1. **Guessing business tracks**: If you cannot determine which of the four curriculum tracks a file belongs to (`01_SOLOCORN_EDTECH`, `02_AP_STATS_MOVIE`, `03_DEVOPS_CONTROL`, `04_VERTICAL_FARMING`), **pause and ask the user**.
2. **Forgetting the local inference endpoint**: All LLM calls must route to `http://127.0.0.1:8000/v1`. Cloud APIs (OpenAI, Claude, etc.) are forbidden unless the user explicitly overrides.
3. **Hard-coding user paths**: Use `Path(__file__).resolve().parent.parent` resolution; do not embed `/Users/nazeera/...`.
4. **Dumping files in root**: Operational assets, logs, and screenplays must never be placed in the repository root. Use the numbered directories.
5. **Modifying render_scenes.py blindly**: This file is an append-only registry. New Manim classes are added at the end; never delete existing classes unless the user confirms.
6. **Missing briefing headers**: New skill `.md` files without the 5-line briefing header are considered unbriefed and must not be committed.

---

## Key File Reference

| File | Responsibility |
|------|----------------|
| `01_SKILLS/skills.py` | Vault CRUD, frontmatter parser, tag/backlink search, Zotero bridge, oMLX inference wrapper |
| `01_SKILLS/solocorn_media_bridge.py` | Master media dispatcher: FCPXML builder, FFmpeg mastering, Manim/Blender triggers, asset ledger sync |
| `01_SKILLS/orchestrator.py` | Main production daemon: syllabus ingestion → chapter split → voice → Manim render → FFmpeg mux → spatial twin |
| `01_SKILLS/pipeline_orchestrator.py` | **One-command 2D/3D pipeline runner** with dependency tracking, dry-run, and resume-from |
| `01_SKILLS/init_project.py` | Scaffolds new project with shot-list template, config files, and full directory tree |
| `01_SKILLS/storyboard_generator.py` | Autonomous storyboard generation via ComfyUI (SDXL/Flux) from parsed shot list |
| `01_SKILLS/character_2d_generator.py` | 2D character sprite generation and mouth-shape sheet creation |
| `01_SKILLS/background_2d_generator.py` | 2D scene background generation via ComfyUI |
| `01_SKILLS/animation_2d_compositor.py` | PIL-based 2D frame compositor (background + character + mouth overlay) |
| `01_SKILLS/auto_dubbing_pipeline.py` | Kokoro/OpenVoice dialogue synthesis for all shots |
| `01_SKILLS/body_mocap.py` | MediaPipe Pose Landmarker → 33 landmarks → joint angles → Blender armature keyframes |
| `01_SKILLS/arkit_mocap_bridge.py` | UDP iFacialMocap listener (52 blend shapes + eye rotation) → Blender shape keys |
| `01_SKILLS/neural_upscaler.py` | ONNX Runtime super-resolution for rendered frames |
| `01_SKILLS/advanced_color_grader.py` | ffmpeg color grading with 6 LUT presets + procedural adjustments |
| `01_SKILLS/parallel_renderer.py` | Multi-core CPU frame rendering with worker pool |
| `01_SKILLS/frame_interpolator.py` | Smooth tweening between keyframes for 48→60fps output |
| `01_SKILLS/episode_manager.py` | Auto-splits shot lists into ~15-min episodes with per-episode manifests |
| `01_SKILLS/distribution_formatter.py` | Auto-exports YouTube/TikTok/Instagram/Twitter/LinkedIn versions |
| `01_SKILLS/project_dashboard.py` | Web UI server for shot status and pipeline stage monitoring |
| `01_SKILLS/error_recovery.py` | 14-step pipeline state tracking with retry-from-failure |
| `01_SKILLS/test_suite.py` | Automated syntax/import/functional validation for all 60+ modules |
| `01_SKILLS/lesson_compiler.py` | Queries local LLM to produce `compiled_lesson_blueprint.json` |
| `01_SKILLS/script_processor.py` | Parses markdown lesson scripts into per-scene JSON manifests |
| `01_SKILLS/curriculum_runner.py` | Batch executor with timeout polling for blueprint consumption |
| `01_SKILLS/init_database.py` | Bootstraps `production_tracks` and `media_assets` on port 5432 |
| `01_SKILLS/render_scenes.py` | Manim scene registry (append-only) |
| `01_SKILLS/openclaw_bridge.py` | Watches `~/.openclaw/agents/main/sessions/*.jsonl` and normalizes streaming output |
| `05_GOVERNANCE/paperclip/governance_core.py` | Corporate entity registry, cap tables, operational expense ledger, runway auditing |
| `01_SKILLS/graphify/knowledge_graph.py` | Postgres-backed node/edge knowledge graph |
| `01_SKILLS/understand_anything/parser_core.py` | Universal text ingestion → structured JSON manifest via local LLM |
| `01_SKILLS/understand_anything/claude_interface.py` | Autonomous Manim scene code generation + aggressive indent sanitization |
| `06_SPATIAL/vtuber_twin/twin_bridge.py` | UDP spatial state streaming to Warudo/VNyan |
| `06_SPATIAL/vtuber_twin/spatial_viewport.py` | pyglet-based IK viewport (60 FPS) |
| `04_PHYSICAL/openclaw/claw_interface.py` | Serial hardware abstraction for robotic claw |
| `.docker/docker-compose.yml` | Container orchestration for OpenClaw, Playwright, Open WebUI, Postgres |
| `01_SKILLS/CLAUDE.md` | Extended runtime standards, third-party integration notes, automation dispatch boundaries |
