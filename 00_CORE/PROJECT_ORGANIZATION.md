# Project & Folder Organization

The authoritative map of where a project lives and what every project-related
folder is for. Short version: **every Paperclip project has exactly one home —
`business_units/<company>/<unit>/` — and nothing is duplicated.**

## The model: one home per project

A Paperclip **project** *is* a **business unit** (a channel within a company).
Each one maps 1:1 to a single folder:

```
business_units/<company>/<unit>/
├── BRIEF.md       # the unit's charter
├── knowledge/     # curriculum, research, reference ("what to know")
├── production/    # runs / outputs ("what's made")
└── assets/        # media
```

The bridge auto-provision poller (`runtime/agents/paperclip_bridge.py`) creates
this folder for every registered Paperclip project. **This is the single source
of truth** — a project deliberately appears in *one* folder, not several. The
registry `00_CORE/business_units.yaml` maps each Paperclip `project_id → unit →
folder`.

> When you create a project in Paperclip and it "only shows up in one folder,"
> that is correct and by design. `business_units/` is that folder.

## The other project-related folders (and why they are NOT duplicates)

| Folder | Role | Duplicate data? |
|--------|------|-----------------|
| `business_units/<co>/<unit>/` | **Source of truth** per project: knowledge/ + production/ + assets/ + BRIEF.md | — (the real storage) |
| `02_CURRICULUM/` | **Curriculum layer.** `01_SOLOCORN_EDTECH`, `02_AP_STATS_MOVIE`, `03_DEVOPS_CONTROL` are **symlink aliases** into the matching `business_units/.../knowledge` (they give the skills library stable curriculum paths — referenced by ~271 skill files). `compiled_wiki/` + `raw_sources/` are the curriculum **ingest/compile pipeline** working dirs (cross-unit). | No — symlinks point at the real storage |
| `05_PROJECTS/` | `_templates/` = run-scaffolding templates. Legacy run location; real runs now land in `business_units/<unit>/production/`. | No — templates + legacy only |
| `projects/`, `teams/` | **Not repo folders.** Paperclip's *internal* per-project workspace lives at `~/.paperclip/instances/default/projects/<company>/<project>/` (by UUID); "Teams" are a Paperclip database concept (the registry maps each unit → a team). | N/A — internal to Paperclip |

Because `02_CURRICULUM/01–03` are symlinks (not copies), there is **no real data
duplication** anywhere in this structure.

## Creating a new project (clean flow)

1. Create the project in Paperclip — it becomes a business unit.
2. The bridge poller scaffolds `business_units/<company>/<unit>/` automatically
   (or run `01_SKILLS/provision_business_unit.py provision <company> <unit>`).
3. For a production run: `01_SKILLS/init_project.py --company <c> --unit <u>` →
   lands in that unit's `production/<run>/`.
4. *(Curriculum channels only)* optionally add a symlink alias under
   `02_CURRICULUM/` pointing at the unit's `knowledge/`.

## Per-project knowledge bases

Every project has its **own isolated knowledge base** at
`business_units/<company>/<unit>/knowledge/`, managed by
`01_SKILLS/knowledge_base.py`:

```
knowledge/
├── README.md       # manifest (auto-generated)
├── sources/        # inbox — drop raw files, then `ingest`  (sources/_done after)
├── notes/          # curated KB documents (markdown + frontmatter; searchable)
└── .kb/index.json  # machine manifest of documents
```

- **Isolated:** each unit's KB is searched and managed independently — content in
  one project's KB never leaks into another's.
- **Auto-created:** `provision_business_unit.py` scaffolds the KB for every unit,
  so new Paperclip projects get one automatically (via the bridge poller). No
  manual setup.
- **Managed via CLI:**
  ```bash
  python3 01_SKILLS/knowledge_base.py add    <company> <unit> file.md --tags a,b
  python3 01_SKILLS/knowledge_base.py ingest <company> <unit>          # process sources/
  python3 01_SKILLS/knowledge_base.py search <company> <unit> "query" [--semantic]
  python3 01_SKILLS/knowledge_base.py list   <company> <unit>
  python3 01_SKILLS/knowledge_base.py reindex <company> <unit>         # rebuild index from disk
  python3 01_SKILLS/knowledge_base.py status                           # all KBs at a glance
  ```
- **oMLX-aware:** `--raw`/`ingest` clean documents through the local MLX server
  (`:8000`); if it's offline, content is stored as-is (the KB still works).

This is distinct from the **global** cross-unit vault at
`02_CURRICULUM/compiled_wiki/` (managed by `skills.py`), which remains a shared
reference vault. Per-project KBs are the isolated, default home for a project's
own knowledge.

## Maintenance notes

- **Do not rename or delete the `02_CURRICULUM/01–03` aliases casually** — they
  are referenced by ~271 skill/doc files. Renaming requires a coordinated
  reference sweep (the stale "SOLOCORN" naming is cosmetic and not worth the
  blast radius unless deliberately undertaken).
- Stop the bridge before any `business_units.yaml` registry migration (the
  auto-provision poller races registry/layout edits).
