# runtime

## normalize_skills.py

Converts all `.md` files in `01_SKILLS/` into Paperclip-compatible `SKILL.md` format.

**Input**: `01_SKILLS/*.md` (258 files, mix of YAML frontmatter and 5-line briefing headers)
**Output**: `library/skills/<slug>/SKILL.md`
**Manifest**: `runtime/skills_manifest.json`

```bash
python3 runtime/normalize_skills.py
```

## create_org_chart.py

Generates the full Paperclip company package from the skills manifest.

**Input**: `runtime/skills_manifest.json`
**Output**:
- `library/agents/<slug>/AGENTS.md` (245 agents)
- `07_PAPERCLIP/companies/solocorn-studios/COMPANY.md`
- `07_PAPERCLIP/companies/solocorn-studios/.paperclip.yaml`
- `07_PAPERCLIP/companies/solocorn-studios/teams/<team>/TEAM.md`

```bash
python3 runtime/create_org_chart.py
```

**Reporting heuristics**:
- `01_SOLOCORN_EDTECH/` → reports to `edtech-lead`
- `02_AP_STATS_MOVIE/` → reports to `apstats-lead`
- `03_DEVOPS_CONTROL/` → reports to `edtech-lead`
- `engineering-*` → reports to `cto`
- `marketing-*`, `sales-*`, `design-*` → reports to `coo`
- `finance-*` → reports to `cfo`

## paperclip_bridge.py

HTTP server that exposes the existing Solocorn Python bridges as REST endpoints,
with bidirectional Paperclip sync (Phase 8).

**Default URL**: `http://127.0.0.1:3101`

### HTTP Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | MLX, Postgres, Manim, FFmpeg status |
| `/ingest` | POST | Trigger `orchestrator.process_incoming_vault_stream()` |
| `/compile-lesson` | POST | Generate blueprint JSON for a topic |
| `/run-curriculum` | POST | Run AP Stats batch curriculum |
| `/process-manifest` | POST | Execute render/manifest task |
| `/generate-timeline` | POST | Build FCPXML from asset list |
| `/voiceover` | POST | Synthesize WAV via macOS `say` |
| `/process-script` | POST | Parse markdown → scene manifests |
| `/vault/search` | POST | Query compiled wiki |
| `/vault/create` | POST | Create wiki note |

### CLI Mode (for Paperclip process adapter)

```bash
python3 runtime/paperclip_bridge.py --execute '<json_task>'
```

Example:
```bash
python3 runtime/paperclip_bridge.py --execute \
  '{"endpoint":"/health","method":"GET"}'
```

### Worker Mode (Paperclip Process Adapter)

When invoked by Paperclip's process adapter (e.g., via `npx paperclipai heartbeat run`),
the bridge enters **worker mode** automatically:

1. Queries Paperclip for issues assigned to `bridge-operator`
2. Claims the first `backlog` task
3. Parses the issue title/description to determine the endpoint
4. Executes the endpoint
5. Updates the issue status (`done` on success, `backlog` on error)
6. Exits cleanly so Paperclip captures the result

Keyword routing:
- "vault search" / "search wiki" → `/vault/search`
- "vault create" / "create note" → `/vault/create`
- "ingest" / "raw source" → `/ingest`
- "compile lesson" / "blueprint" → `/compile-lesson`
- "process manifest" / "render" → `/process-manifest`
- "generate timeline" / "FCPXML" → `/generate-timeline`
- "voiceover" / "synthesize" → `/voiceover`
- "process script" / "scene manifest" → `/process-script`

### Cost Estimation

Every bridge execution reports a symbolic cost event to Paperclip's budget system:

| Endpoint | Estimated Cost | Basis |
|----------|---------------|-------|
| `/health` | 0¢ | No compute |
| `/vault/search` | 0.1¢ | Local query |
| `/vault/create` | 0.1¢ | Local write |
| `/process-script` | 1¢ | Parsing |
| `/voiceover` | 2¢ | ~24s audio @ 5¢/min |
| `/compile-lesson` | 2¢ | MLX inference |
| `/generate-timeline` | 5¢ | FFmpeg mux |
| `/process-manifest` | 10¢ | Render |
| `/ingest` | 15¢ | MLX + Manim + FFmpeg + voice |
| `/run-curriculum` | 50¢ | Batch |

**Time surcharge**: +2¢ if >10s, +5¢ if >30s (runaway loop protection)

Costs are posted to `POST /api/companies/{id}/cost-events` and tracked against the agent's monthly budget.

### Bidirectional Sync

Every successful endpoint execution automatically:
1. Creates a Paperclip issue documenting the work
2. Assigns it to the correct project (EdTech, AP Stats, etc.)
3. Resolves the issue when work completes successfully
4. Leaves it open if an error occurs

This gives you a full audit trail of every bridge invocation in the Paperclip dashboard.

## test_bridge.py

Smoke tests for the bridge server.

```bash
# Start bridge first
python3 runtime/paperclip_bridge.py &

# Run tests
python3 runtime/test_bridge.py
```

Tests: MLX direct, /health, /vault/search, /vault/create
