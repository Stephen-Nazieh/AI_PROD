#!/usr/bin/env python3
"""
Per-project Knowledge Base manager for DeParadigm Media.

Every business unit (= a Paperclip project) gets its own ISOLATED knowledge base
under `business_units/<company>/<unit>/knowledge/`:

    knowledge/
    ├── README.md        # human-facing manifest (what this KB is, how to manage)
    ├── sources/         # inbox — drop raw files here, then `ingest`
    │   └── _done/       # processed sources are moved here
    ├── notes/           # curated KB documents (markdown + frontmatter)
    └── .kb/index.json   # machine manifest of documents (id, title, tags, ...)

This is distinct from the GLOBAL cross-unit vault at 02_CURRICULUM/compiled_wiki
(managed by skills.py). Each project KB is self-contained and searched in isolation.

CLI:
    knowledge_base.py init    <company> <unit>
    knowledge_base.py add     <company> <unit> <file|-> [--title T] [--tags a,b] [--raw]
    knowledge_base.py ingest  <company> <unit>            # sources/ -> notes/ (oMLX clean)
    knowledge_base.py list    <company> <unit>
    knowledge_base.py search  <company> <unit> <query> [--limit N] [--semantic]
    knowledge_base.py reindex <company> <unit>
    knowledge_base.py status  [--company C]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import yaml

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = WORKSPACE_ROOT / "00_CORE" / "business_units.yaml"

# Reuse the maintained oMLX helpers from the skills bridge when available; degrade
# gracefully (raw copy, substring search) if the inference server is offline.
sys.path.insert(0, str(WORKSPACE_ROOT / "01_SKILLS"))
try:
    from skills import clean_raw_content, run_local_omlx_inference  # type: ignore
    _OMLX = True
except Exception:  # pragma: no cover - skills import is best-effort
    _OMLX = False

    def clean_raw_content(raw_text: str) -> str:  # type: ignore
        return raw_text

    def run_local_omlx_inference(prompt, system_instruction, model=None):  # type: ignore
        return "ERROR: oMLX unavailable"


# ── Registry / path resolution ──────────────────────────────────────────────

def _registry() -> dict:
    if not REGISTRY.exists():
        return {"companies": {}}
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {"companies": {}}


def kb_root(company: str, unit: str) -> Path:
    """Resolve a unit's knowledge-base root from the registry (falls back to convention)."""
    reg = _registry()
    companies = reg.get("companies", {})
    co = companies.get(company)
    if not co:
        raise SystemExit(f"❌ Unknown company '{company}'. Known: {', '.join(companies) or '(none)'}")
    unit_rec = (co.get("units") or {}).get(unit)
    folder = (unit_rec or {}).get("folder", f"business_units/{company}/{unit}")
    return WORKSPACE_ROOT / folder / "knowledge"


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return s[:60] or "untitled"


# ── Index (the machine manifest) ────────────────────────────────────────────

def _index_path(root: Path) -> Path:
    return root / ".kb" / "index.json"


def load_index(root: Path) -> dict:
    p = _index_path(root)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"documents": []}


def save_index(root: Path, index: dict) -> None:
    p = _index_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    index["updated"] = datetime.now().isoformat(timespec="seconds")
    p.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Minimal YAML-ish frontmatter parser (title/tags). Returns (fm, body)."""
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    fm: dict = {}
    key = None
    for line in parts[1].splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("- ") and key:
            fm.setdefault(key, [])
            if isinstance(fm[key], list):
                fm[key].append(s[2:].strip())
        elif ":" in s:
            k, v = s.split(":", 1)
            key = k.strip()
            v = v.strip()
            fm[key] = v if v else []
    return fm, parts[2].lstrip("\n")


# ── Scaffolding (used by provision_business_unit.py too) ─────────────────────

def scaffold(root: Path, company: str = "", unit: str = "") -> Path:
    """Create the KB directory structure + README + empty index. Idempotent."""
    (root / "sources" / "_done").mkdir(parents=True, exist_ok=True)
    (root / "notes").mkdir(parents=True, exist_ok=True)
    (root / ".kb").mkdir(parents=True, exist_ok=True)
    # keep empty dirs in git
    for keep in ("sources/.gitkeep", "notes/.gitkeep"):
        f = root / keep
        if not f.exists():
            f.write_text("", encoding="utf-8")
    readme = root / "README.md"
    if not readme.exists():
        label = f"{company}/{unit}".strip("/") or root.parent.name
        readme.write_text(
            f"# Knowledge Base — {label}\n\n"
            "Isolated knowledge base for this project/business unit. Managed via\n"
            "`01_SKILLS/knowledge_base.py`.\n\n"
            "## Layout\n"
            "- `sources/` — inbox; drop raw files (notes, transcripts, syllabi) here\n"
            "- `notes/` — curated KB documents (markdown; the searchable content)\n"
            "- `.kb/index.json` — machine manifest of documents\n\n"
            "## Manage\n"
            "```bash\n"
            f"python3 01_SKILLS/knowledge_base.py add    {company or '<company>'} {unit or '<unit>'} path/to/file.md\n"
            f"python3 01_SKILLS/knowledge_base.py ingest {company or '<company>'} {unit or '<unit>'}   # process sources/\n"
            f"python3 01_SKILLS/knowledge_base.py search {company or '<company>'} {unit or '<unit>'} \"query\"\n"
            f"python3 01_SKILLS/knowledge_base.py list   {company or '<company>'} {unit or '<unit>'}\n"
            "```\n",
            encoding="utf-8",
        )
    if not _index_path(root).exists():
        save_index(root, {"company": company, "unit": unit, "documents": []})
    return root


# ── Core operations ──────────────────────────────────────────────────────────

def _write_note(root: Path, title: str, body: str, tags: list[str], source: str) -> dict:
    notes = root / "notes"
    notes.mkdir(parents=True, exist_ok=True)
    slug = _slug(title)
    target = notes / f"{slug}.md"
    n = 2
    while target.exists():
        target = notes / f"{slug}-{n}.md"
        n += 1
    date = datetime.now().strftime("%Y-%m-%d")
    fm = ["---", f"title: {title}", f"date: {date}"]
    if tags:
        fm.append("tags:")
        fm += [f"  - {t}" for t in tags]
    fm += [f"source: {source}", "---", ""]
    target.write_text("\n".join(fm) + body.rstrip() + "\n", encoding="utf-8")
    return {
        "id": target.stem,
        "title": title,
        "path": str(target.relative_to(root)),
        "tags": tags,
        "source": source,
        "added": date,
        "bytes": target.stat().st_size,
    }


def add_document(company: str, unit: str, src: str, title: str | None,
                 tags: list[str], raw: bool) -> str:
    root = kb_root(company, unit)
    scaffold(root, company, unit)
    if src == "-":
        content = sys.stdin.read()
        title = title or f"note-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        source = "stdin"
    else:
        sp = Path(src)
        if not sp.exists():
            return f"❌ File not found: {src}"
        content = sp.read_text(encoding="utf-8", errors="ignore")
        title = title or sp.stem
        source = sp.name
    if not content.strip():
        return "❌ Empty content; nothing added."
    if raw:
        if not _OMLX:
            print("⚠️  oMLX unavailable — storing raw (no cleaning).", file=sys.stderr)
        else:
            content = clean_raw_content(content)
    rec = _write_note(root, title, content, tags, source)
    index = load_index(root)
    index["documents"].append(rec)
    save_index(root, index)
    return f"✅ Added '{rec['title']}' → {rec['path']} ({rec['bytes']} bytes)"


def ingest(company: str, unit: str) -> str:
    root = kb_root(company, unit)
    scaffold(root, company, unit)
    sources = root / "sources"
    done = sources / "_done"
    done.mkdir(parents=True, exist_ok=True)
    index = load_index(root)
    processed = 0
    for f in sorted(sources.iterdir()):
        if f.is_dir() or f.name.startswith(".") or f.name == "_done":
            continue
        content = f.read_text(encoding="utf-8", errors="ignore")
        if not content.strip():
            continue
        cleaned = clean_raw_content(content) if _OMLX else content
        rec = _write_note(root, f.stem, cleaned, ["ingested"], f.name)
        index["documents"].append(rec)
        f.rename(done / f.name)
        processed += 1
    save_index(root, index)
    note = "" if _OMLX else " (raw — oMLX offline)"
    return f"✅ Ingested {processed} source file(s) into {company}/{unit} KB{note}."


def list_docs(company: str, unit: str) -> str:
    root = kb_root(company, unit)
    if not root.exists():
        return f"(no KB yet for {company}/{unit} — run: knowledge_base.py init {company} {unit})"
    index = load_index(root)
    docs = index.get("documents", [])
    if not docs:
        return f"{company}/{unit} KB is empty (0 documents)."
    lines = [f"{company}/{unit} KB — {len(docs)} document(s):"]
    for d in docs:
        tags = (" [" + ", ".join(d.get("tags", [])) + "]") if d.get("tags") else ""
        lines.append(f"  • {d.get('title'):40} {d.get('path')}{tags}")
    return "\n".join(lines)


def search(company: str, unit: str, query: str, limit: int, semantic: bool) -> str:
    root = kb_root(company, unit)
    notes = root / "notes"
    if not notes.exists():
        return f"(no KB for {company}/{unit})"
    hits = []
    ql = query.lower()
    for md in sorted(notes.rglob("*.md")):
        content = md.read_text(encoding="utf-8", errors="ignore")
        if ql in content.lower():
            idx = content.lower().find(ql)
            snip = content[max(0, idx - 60): idx + len(query) + 60].replace("\n", " ")
            fm, _ = parse_frontmatter(content)
            hits.append({"path": str(md.relative_to(root)),
                         "title": fm.get("title", md.stem), "snippet": f"...{snip}..."})
            if len(hits) >= max(limit, limit * 3 if semantic else limit):
                break
    if semantic and _OMLX and hits:
        listing = "\n".join(f"{i+1}. {h['title']}: {h['snippet']}" for i, h in enumerate(hits))
        prompt = (f"Query: '{query}'\nRank these {company}/{unit} KB notes by relevance. "
                  f"Return ONLY a JSON array of {{index, score}} (1-based index).\n\n{listing}")
        resp = run_local_omlx_inference(prompt, "You are a retrieval ranker. Output only JSON.")
        try:
            arr = json.loads(resp[resp.find("["): resp.rfind("]") + 1])
            arr.sort(key=lambda x: x.get("score", 0), reverse=True)
            hits = [hits[a["index"] - 1] for a in arr if 0 < a.get("index", 0) <= len(hits)]
        except Exception:
            pass
    hits = hits[:limit]
    if not hits:
        return f"No matches for '{query}' in {company}/{unit} KB."
    out = [f"{len(hits)} match(es) in {company}/{unit} KB:"]
    for h in hits:
        out.append(f"  • {h['title']} ({h['path']})\n      {h['snippet']}")
    return "\n".join(out)


def reindex(company: str, unit: str) -> str:
    """Rebuild .kb/index.json from the notes/ folder on disk (recovery / drift fix)."""
    root = kb_root(company, unit)
    scaffold(root, company, unit)
    docs = []
    for md in sorted((root / "notes").rglob("*.md")):
        content = md.read_text(encoding="utf-8", errors="ignore")
        fm, _ = parse_frontmatter(content)
        tags = fm.get("tags", [])
        docs.append({
            "id": md.stem,
            "title": fm.get("title", md.stem),
            "path": str(md.relative_to(root)),
            "tags": tags if isinstance(tags, list) else [tags],
            "source": fm.get("source", "unknown"),
            "added": fm.get("date", ""),
            "bytes": md.stat().st_size,
        })
    save_index(root, {"company": company, "unit": unit, "documents": docs})
    return f"✅ Reindexed {company}/{unit}: {len(docs)} document(s)."


def status(company_filter: str | None) -> str:
    reg = _registry()
    lines = ["Knowledge bases:"]
    for co, cdata in reg.get("companies", {}).items():
        if company_filter and co != company_filter:
            continue
        units = cdata.get("units") or {}
        if not units:
            lines.append(f"  {co}: (no units)")
        for unit in units:
            root = kb_root(co, unit)
            docs = len(load_index(root).get("documents", [])) if root.exists() else 0
            scaf = "✓" if (root / ".kb" / "index.json").exists() else "—"
            lines.append(f"  {co}/{unit:16} scaffolded={scaf}  documents={docs}")
    return "\n".join(lines)


# ── CLI ──────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Per-project knowledge base manager")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def cu(p):
        p.add_argument("company")
        p.add_argument("unit")

    cu(sub.add_parser("init", help="scaffold a project's KB"))
    p_add = sub.add_parser("add", help="add a document")
    cu(p_add)
    p_add.add_argument("file", help="path to file, or - for stdin")
    p_add.add_argument("--title")
    p_add.add_argument("--tags", default="")
    p_add.add_argument("--raw", action="store_true", help="clean via oMLX before storing")
    cu(sub.add_parser("ingest", help="process sources/ inbox -> notes/"))
    cu(sub.add_parser("list", help="list documents"))
    p_s = sub.add_parser("search", help="search within this project's KB")
    cu(p_s)
    p_s.add_argument("query")
    p_s.add_argument("--limit", type=int, default=10)
    p_s.add_argument("--semantic", action="store_true")
    cu(sub.add_parser("reindex", help="rebuild index.json from notes/"))
    p_st = sub.add_parser("status", help="overview of all KBs")
    p_st.add_argument("--company")

    args = ap.parse_args(argv)
    if args.cmd == "init":
        scaffold(kb_root(args.company, args.unit), args.company, args.unit)
        print(f"✅ KB scaffolded for {args.company}/{args.unit}")
    elif args.cmd == "add":
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
        print(add_document(args.company, args.unit, args.file, args.title, tags, args.raw))
    elif args.cmd == "ingest":
        print(ingest(args.company, args.unit))
    elif args.cmd == "list":
        print(list_docs(args.company, args.unit))
    elif args.cmd == "search":
        print(search(args.company, args.unit, args.query, args.limit, args.semantic))
    elif args.cmd == "reindex":
        print(reindex(args.company, args.unit))
    elif args.cmd == "status":
        print(status(args.company))
    return 0


if __name__ == "__main__":
    sys.exit(main())
