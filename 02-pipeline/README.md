# SIGNIFICANT — Script→Video Pipeline

Feed it a screenplay + a show bible, it produces the video. No bespoke per-scene scripts.

## Run

### Integrated into the platform (recommended)
The 3D pipeline is **mode `3d`** of the studio orchestrator. The run slug maps to
`business_units/<company>/<unit>/production/<slug>/` (canonical `01-scripts…09-deliver` tree),
with logging, dry-run, resume, and a Postgres production-ledger entry.
```bash
python3 01_SKILLS/pipeline_orchestrator.py dry-run S01E01 --mode 3d --company deparadigm-media --unit ap-stats
python3 01_SKILLS/pipeline_orchestrator.py run     S01E01 --mode 3d --company deparadigm-media --unit ap-stats --title "The Whale"
#   init → produce → distribute   (reads 01-scripts/screenplay.md; writes 06-audio, 07-editing, 08-subtitles, 09-deliver)
python3 01_SKILLS/pipeline_orchestrator.py run     S01E01 --mode 3d --company deparadigm-media --unit ap-stats --resume-from produce
```

### Standalone (direct)
```bash
# business-unit run (writes into the canonical production tree)
env/bin/python3 02-pipeline/produce.py --company deparadigm-media --unit ap-stats --run S01E01
# one scene (heading substring match)
env/bin/python3 02-pipeline/produce.py --script path/to/screenplay.md --scene "KITCHENETTE" --out OUT/

# whole episode: every mapped scene in order, title card, stitched EPISODE.mp4 + EPISODE.srt
env/bin/python3 02-pipeline/produce.py --script path/to/screenplay.md --out OUT/ --episode S01E01

# platform deliverables from a finished episode
env/bin/python3 02-pipeline/distribute.py OUT/S01E01.mp4 --srt OUT/S01E01.srt --title "SIGNIFICANT · The Whale"
#   -> *_vertical.mp4 (9:16 Shorts), *_thumb.jpg, *_captioned.mp4
```

## Built-in features
- **Acting:** parentheticals → emotion (brow/eye blendshapes); eye-lines (head turns toward partner). Automatic.
- **Coverage:** establish + shot/reverse for dialogue; graphic beats (title/season-seed/tag) via images; B-roll inserts.
- **Robustness:** config-hash render cache (skip unchanged shots) + black-frame quality gate with retry.
- **Captions:** `EPISODE.srt` auto-built from dialogue timing.
- **Reach:** vertical reframe, thumbnail, optional burned-in captions (`distribute.py`).

## How it flows
```
screenplay.md ─▶ parse() ─▶ scenes+beats ─▶ coverage planner ─▶ shot list
                                                                    │
   show_bible.json (cast→avatar/voice/gesture, location→set,        │
                    broll→manim, blocking, coverage templates)      ▼
                                          ┌── Kokoro VO per line
                                          ├── bl_scene_engine.py (1 generic renderer)
                                          │      └─ bl_sets.py (set registry)
                                          │      └─ bl_anim_lib.py (motion standard)
                                          ├── manim B-roll registry
                                          └── ffmpeg assemble (cut + music + fades) ─▶ scene.mp4
```

## The pieces (all reusable)
| File | Role |
|---|---|
| `02-pipeline/produce.py` | orchestrator: parse → plan → VO → render → assemble → stitch |
| `02-pipeline/show_bible.json` | the per-show config (authored once) |
| `01-scripts/bl_scene_engine.py` | ONE generic Blender renderer (config-driven) |
| `01-scripts/bl_sets.py` | set registry — location id → 3D set builder |
| `01-scripts/bl_anim_lib.py` | the motion/look standard (breathing, gesture, hands) |
| `01-scripts/manim_ep1_broll*.py` | the stat-insert B-rolls |

## Extending to a new script / show
- **New character** → add to `show_bible.characters` (`vrm`, `voice`, `gesture`). Aliases supported.
- **New location** → add a builder to `bl_sets.SETS` + map `"LOCATION|TIME"` in `show_bible.locations`. Unmapped scenes are skipped (and reported); they fall back to `studio` if you map them there.
- **New B-roll** → add a `manim_*.py` Scene + register it in `show_bible.brolls`.
- **New show** → a new `show_bible.json`. The engine, sets, motion, and assembler are shared.

## What's automatic vs. authored
- **Automatic:** parsing, character staging, shot/reverse coverage, VO, lip-sync, body motion, lighting, cutting, music, fades, stitching.
- **Authored once per show (the bible):** which avatar/voice per character, which set per location, which Manim module per B-roll, blocking + coverage templates.
- **Per new asset:** a set builder for a brand-new location; a Manim module for a brand-new stat insert. Everything else is config.

## Known limits (honest)
- Coverage is template-based (establish + shot/reverse-shot for ≤2 speakers); 3+ speaker scenes use the first two.
- Each shot re-imports VRMs + rebuilds the set (simple, not yet cached).
- Action lines (non-dialogue staging) aren't auto-blocked — only dialogue + B-roll beats drive coverage.
- Desk/insert/over-the-shoulder special framings still benefit from per-scene tuning.
