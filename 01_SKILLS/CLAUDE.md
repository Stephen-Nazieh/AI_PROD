# SOLOCORN RUNTIME STANDARDS & CONSTRAINTS

## System Profile
- Host Engine: Apple Silicon macOS Native Binary Shell (128GB RAM Budget)
- Master Orchestrator: Python 3.x System Daemon Platform
- Core Inference Engine: Native oMLX Server (Bypassing Docker for Inference Optimization)
- Core API Endpoint: http://127.0.0.1:8000/v1 (Local loopback mapping only)

## Repository Rules
1. Never place heavy model weight frameworks, uncompressed raw footage, or data caches inside internal folders. All asset offloading must target the `/Volumes/YOUR_SSD_NAME/` USB4/Thunderbolt 4 external storage partition path.
2. Preserve all structured Markdown frontmatter blocks (`agent_id`, `model_target`, `type`) across all codebase optimization runs.
3. Force all programmatically generated post-production video timelines to output in strict compliance with the Apple Final Cut Pro XML (FCPXML v1.11+) schema standard. Do not fallback to non-native video formats.

## Third-Party Integrations

### obsidian-skills (GitHub: Stephen-Nazieh/obsidian-skills)
- **Status**: Fully integrated, adapted for local oMLX execution on port 8000.
- **Adaptations**: All cloud dependencies stripped (npm, external Obsidian CLI, web URLs). Core logic rewritten to route through `http://127.0.0.1:8000/v1`. All file operations map relatively to `02_CURRICULUM/compiled_wiki/`.
- **Skill Files**: `obsidian_power_user.md` (superset replacing 3 fragmented skills), `vault_scraper_skill.md`, `obsidian_vault_manager.md` now live in `01_SKILLS/.
- **Bridge Script**: `skills.py` provides the Python integration layer — vault CRUD, frontmatter parsing, tag/backlink queries, batch transforms, and raw source processing via local oMLX inference.
- **Tracking**: Actively monitoring internal vault data lanes (`compiled_wiki/`, `raw_sources/`).

### Skills-Pipeline (GitHub: Stephen-Nazieh/Skills-Pipeline)
- **Status**: Fully evaluated, filtered for redundancies, and integrated into the local 128GB production workspace.
- **Deduplication**: Obsidian markdown/bases/canvas skills from `obsidian-skills` were superseded by the superior `obsidian-power-user` skill; 3 duplicate files removed.
- **New Integrations**:
  - **SaaS Stack**: `nextjs_developer.md` (Next.js v16.2.1), `stripe_developer.md` (payments), `supabase_developer.md` (database/auth), `vercel_developer.md` (deployment) — all adapted with local oMLX frontmatter.
  - **YouTube Production Pipeline**: 6-agent pipeline (`youtube_research_agent.md`, `youtube_script_agent.md`, `youtube_seo_agent.md`, `youtube_visual_director.md`, `youtube_editor_brief.md`, `youtube_thumbnail_agent.md`) adapted for DeParadigm Media's 4-channel monetization blueprint with channel-specific voice, visual identity, and output paths mapped to `03_ASSETS/_HANDOFF_FCP_CAPCUT/projects/`.
- **Adaptations**: All `[Channel]`/`[Creator]` placeholders replaced with DeParadigm Media identity. Blockchain/AI-generic language replaced with DeParadigm Media domains (GCP, AP Statistics, XTTS v2, ambient loops). All file output paths mapped to local workspace lanes.
- **Bridge Impact**: No Python utilities to merge (repo is markdown-only), but `skills.py` remains the active integration layer for all vault and pipeline operations.

### zotero-mcp-skill (GitHub: Stephen-Nazieh/zotero-mcp-skill)
- **Status**: Deployed natively as a local research tool, giving the scriptwriting roster direct, context-aware access to personal research libraries and academic source material.
- **Adaptations**: Logseq output format replaced with direct `02_CURRICULUM/compiled_wiki/bibliographies/` ingestion. Claude Desktop/Code environment detection replaced with unified local oMLX routing via `http://127.0.0.1:8000/v1`. File save paths remapped from `/Users/niyaro/Desktop/` to local workspace lanes.
- **Skill File**: `zotero_research_scout.md` lives in `01_SKILLS/`, teaching multi-strategy search (semantic via oMLX, keyword via SQLite, author, tag, annotation) with Chinese-English bilingual support.
- **Bridge Integration**: `skills.py` now includes 10 Zotero functions: `search_zotero_semantic`, `search_zotero_keyword`, `search_zotero_author`, `search_zotero_by_tag`, `search_zotero_annotations`, `get_zotero_tags`, `get_zotero_collections`, `export_zotero_bibliography`, `translate_zotero_text`, plus auto-detection of the macOS Zotero SQLite database at `~/Library/Application Support/Zotero/Profiles/*/zotero.sqlite`.
- **Tracking**: Actively indexing local Zotero library into the compiled wiki knowledge graph.

### agency-agents (GitHub: Stephen-Nazieh/agency-agents)
- **Status**: Select high-velocity assets and structural playbook runbooks natively adapted, filtered for redundancies, and fully integrated into the studio environment.
- **Deduplication**: Discarded all enterprise, financial, academic, game-development, paid-media, product, project-management, sales, support, testing, and specialized/generic support roles. Retained only engineering and China-market marketing assets.
- **New Integrations**:
  - **Engineering**: `engineering_devops_automator.md` (local CI/CD for content pipelines, Apple Silicon optimization), `engineering_sre.md` (SLOs for oMLX inference, 128GB memory monitoring, FCPXML validity tracking).
  - **China Marketing**: `marketing_bilibili_strategist.md` (danmaku engagement, 科技区/知识区 optimization), `marketing_xiaohongshu_specialist.md` (lifestyle brand building, study setup aesthetic), `marketing_china_localization.md` (7-platform trend intelligence, GTM phase gates), `marketing_short_video_coach.md` (CapCut/FCP/DaVinci/Motion pipeline for educational content).
- **Handoff Template Integration**: Extracted NEXUS handoff metadata syntax from `strategy/coordination/handoff-templates.md` and merged generation logic into `solocorn_media_bridge.py` as two functions: `generate_agent_handoff()` (standard agent-to-agent handoff with metadata tables) and `generate_qa_verdict()` (PASS/FAIL verdict documents with retry tracking and escalation logic).
- **Studio Launch Playbook**: Created `studio_launch_playbook.md` synthesizing all 7 NEXUS phase playbooks (0-6) into a DeParadigm Media-specific production methodology governing how scriptwriter and asset generator agents validate curriculum data (`02_CURRICULUM/compiled_wiki/`) before initiating FCPXML compilation lines. Features the Script→Edit→Review loop, parallel build tracks, and 6 phase gates with GO/NO-GO/PIVOT decisions.
- **Adaptations**: All generic cloud references replaced with local paths. All external model endpoints routed to `http://127.0.0.1:8000/v1`. All file operations mapped to `02_CURRICULUM/compiled_wiki/` and `03_ASSETS/_HANDOFF_FCP_CAPCUT/`.
- **Tracking**: Engineering agents monitor oMLX server health and pipeline reliability. Marketing agents track China-platform engagement metrics and trend signals.

## Playbook & Regional Execution Rules

- **Playbook Validation Mandate**: Before executing or optimizing any scriptwriting agent, verify that its internal logic conforms to the validation gates defined in `01_SKILLS/studio_launch_playbook.md` to ensure data integrity before initiating media compilation lines.
- **Regional Formatting Guardrail**: When updating the Bilibili or Xiaohongshu strategist engines, ensure all visual and aspect ratio configurations explicitly preserve local Chinese mobile media distribution guidelines and algorithmic tagging standards.

## Global Workspace Instructions

### Runtime Environment
- **Local memory ceiling**: 128GB RAM. No single pipeline stage may allocate more than 96GB without explicit swap-to-disk staging.
- **Compute endpoint**: All oMLX inference calls route to `http://localhost:8000`. Fallback to `http://localhost:8001` is permitted only when port 8000 returns HTTP 503 for three consecutive health checks.
- **Production channels**: Four core channels are active — `alpha` (experimental), `beta` (staging validation), `gamma` (production render), `delta` (emergency bypass).

### Asset Storage Topology
- `01_SKILLS/` — Agent skill definitions, bridge modules, and system documentation.
- `03_ASSETS/` — Staging ground for rendered frames, intermediate textures, geometry caches, and final delivery packages.
- External high-speed RAID mount at `/Volumes/SolocornRAID/03_ASSETS` is the canonical write target for all heavy I/O to prevent local disk saturation.

### File Separation Guardrail
Agents must strictly segment work by **company → business unit** (channel). Operational assets, startup logs, and creative screenplays must never be dumped loosely into the root directory. Content for a unit lives under `business_units/<company>/<unit>/` (`knowledge/` for source/curriculum, `production/<run>/` for pipeline output). The registry `00_CORE/business_units.yaml` (a `companies:` map) is the source of truth.

The legacy `02_CURRICULUM/` track paths still work — they are **compatibility symlinks** redirecting into the DeParadigm Media units:

- `02_CURRICULUM/01_SOLOCORN_EDTECH/` → `business_units/deparadigm-media/edtech/knowledge/` (Dev & Cloud)
- `02_CURRICULUM/03_DEVOPS_CONTROL/` → `business_units/deparadigm-media/edtech/knowledge/` (Dev & Cloud infra/ops)
- `02_CURRICULUM/02_AP_STATS_MOVIE/` → `business_units/deparadigm-media/ap-stats/knowledge/`
- `02_CURRICULUM/compiled_wiki/` — shared cross-unit knowledge vault (unchanged)
- (`04_VERTICAL_FARMING` is not a current channel.)

Any agent that cannot determine the correct business unit must pause and confirm with the user before writing.

## Project Briefing Rules

Every specialized agent file (`.md`) under `01_SKILLS/` must contain a dedicated 5-line briefing header immediately below its title, mapping out:

1. **Narrow specialty** — The single domain this agent owns (e.g., "3D pipeline script generation", "browser scraping orchestration", "video timeline compilation").
2. **Exact target output directory** — The absolute or repo-relative path where all deliverables are written (e.g., `03_ASSETS/3d_stage_assets/scenes/`).
3. **Explicit stylistic tone constraints** — The voice, terminology register, and forbidden phrases or patterns the agent must observe.
4. **Prioritized asset folder paths** — An ordered list of directories to check for input assets, from highest to lowest priority.
5. **Strict pause-and-confirm parameters** — A list of values the agent must never guess (e.g., frame dimensions, codec bitrates, external mount points) and must halt to ask the user for explicitly.

Agents missing this header are considered unbriefed and must not be dispatched until the header is added and verified.

## Agent Registry

- `pae_da_vinci` — Principal Agent Engineer modeled after Leonardo da Vinci; translates calculus, statistics, and CS workflows into ZScript, MAXScript, and Maya Python commands.

## Bridge Modules

- `solocorn_media_bridge.py` — Master dispatcher for terminal-level render and compositing jobs. Supports headless 3ds Max, FFmpeg video assembly, and 2D layer export.

## 3D Spatial Pipeline Configurations

The `pae_da_vinci` engine is now online and registered for active duty. All 3D format processing — including ZBrush `.ztl` / `.zsc`, 3ds Max `.max` / `.ms`, and Maya `.ma` / `.py` assets — must bypass internal system caches. Output is to be written directly onto the high-speed external storage drive mounted at `/Volumes/SolocornRAID/03_ASSETS` to prevent local disk saturation during heavy geometry or texture streaming operations.

### Corporate Governance Control Plane
Paperclip is officially deployed as our executive dashboard. It coordinates high-level business missions and enforces token expenditure boundaries across our 4 isolated subfolders, while utilizing a persistent local PostgreSQL cluster for long-term task-ancestry retention.

## Automation Dispatch Boundaries

### Event Routines
OpenClaw daemon pools must treat any modification to `01_SKILLS/*.md` or `solocorn_media_bridge.py` as an immediate event trigger. The instant a handoff metadata block is appended to a skill file, the daemon launches the Python media bridge execution loop without waiting for an explicit user command. The bridge reads the metadata block, resolves the target stage, and dispatches the job to the appropriate channel.

### Scheduled Tasks
Heavy video timeline compilations and asset file optimization sweeps are restricted to sequential time-blocked scripts. Each block receives a dedicated thermal budget: no more than 85% sustained CPU utilization for longer than 10 minutes. If a compilation exceeds its thermal window, it must yield and reschedule to the next available block. This prevents host CPU thermal throttling on our 4-core production hardware.

## Administrative Governance Shell

Paperclip is deployed as the master administrative governance shell for the DeParadigm Media. It operates as a dedicated containerized dashboard (`paperclip_studio_governor`) on host port 3005, providing executive oversight across all active agent operations. Its primary responsibilities are:

- **Mission Tracking**: Monitors high-level company missions and strategic objectives across the four business subfolders (`01_SOLOCORN_EDTECH`, `02_AP_STATS_MOVIE`, `03_DEVOPS_CONTROL`, `04_VERTICAL_FARMING`).
- **Token Expenditure Boundaries**: Enforces hard spending caps on inference tokens routed through the native oMLX endpoint, with alerts triggered when any business track exceeds its allocated budget.
- **Zero-Human Auditing**: Generates automated audit trails for every agent handoff, QA verdict, and media pipeline dispatch without requiring manual review.
- **Governance Endpoint**: Accessible at `http://127.0.0.1:3005/governor` via the local gateway routing table.