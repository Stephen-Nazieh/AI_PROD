#!/usr/bin/env python3
"""
Knowledge-base power tools (Phase 2) — semantic search, web/url auto-ingestion,
project-KB ↔ global-wiki bridge, provenance audit, staleness, and a local
cross-reference graph. Builds on knowledge_base.py; reachable via `studio kb`.

    kb_tools semantic <co> <unit> "<query>" [--limit N]
    kb_tools add-url  <co> <unit> <url> [--clean]
    kb_tools promote  <co> <unit> <note>          # project KB -> compiled_wiki
    kb_tools pull     <co> <unit> <wiki-note>      # compiled_wiki -> project KB
    kb_tools audit    <co> <unit>                  # notes missing provenance
    kb_tools stale    <co> <unit> [--days 90]
    kb_tools graph    <co> <unit>                  # wikilink/tag cross-reference graph
"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "01_SKILLS"))
import knowledge_base as kb  # noqa: E402

WIKI_DIR = ROOT / "02_CURRICULUM" / "compiled_wiki"


def _notes(co: str, unit: str) -> list[pathlib.Path]:
    nd = kb.kb_root(co, unit) / "notes"
    return sorted(nd.rglob("*.md")) if nd.exists() else []


# ── Semantic search (TF-IDF cosine — local, no embeddings server needed) ─────

def semantic(co: str, unit: str, query: str, limit: int = 10) -> str:
    notes = _notes(co, unit)
    if not notes:
        return f"(no notes in {co}/{unit} KB)"
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except Exception:
        return kb.search(co, unit, query, limit, semantic=False)
    docs, titles = [], []
    for n in notes:
        txt = n.read_text(encoding="utf-8", errors="ignore")
        fm, body = kb.parse_frontmatter(txt)
        docs.append(body)
        titles.append((fm.get("title", n.stem), str(n.relative_to(kb.kb_root(co, unit)))))
    vec = TfidfVectorizer(stop_words="english", max_features=4000)
    try:
        mat = vec.fit_transform(docs + [query])
    except ValueError:
        return f"No matches for '{query}' in {co}/{unit} KB."
    sims = cosine_similarity(mat[-1], mat[:-1]).flatten()
    ranked = sorted(range(len(docs)), key=lambda i: sims[i], reverse=True)
    hits = [(titles[i][0], titles[i][1], sims[i]) for i in ranked if sims[i] > 0.01][:limit]
    if not hits:
        return f"No semantically-relevant notes for '{query}' in {co}/{unit} KB."
    out = [f"Semantic results for '{query}' in {co}/{unit} KB:"]
    for title, path, score in hits:
        out.append(f"  • {title:38} {path}   (relevance {score:.2f})")
    return "\n".join(out)


# ── Web / URL auto-ingestion ─────────────────────────────────────────────────

def add_url(co: str, unit: str, url: str, clean: bool = False) -> str:
    try:
        import requests
        from bs4 import BeautifulSoup
    except Exception as e:
        return f"❌ ingestion deps missing: {e}"
    try:
        html = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 DPM-KB"}).text
    except Exception as e:
        return f"❌ fetch failed: {e}"
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    title = (soup.title.string.strip() if soup.title and soup.title.string else url)
    text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n")).strip()
    if not text:
        return "❌ no extractable text"
    if clean and kb._OMLX:
        text = kb.clean_raw_content(text)
    root = kb.kb_root(co, unit)
    kb.scaffold(root, co, unit)
    rec = kb._write_note(root, title[:80], text, ["web", "ingested"], url)
    idx = kb.load_index(root)
    idx["documents"].append(rec)
    kb.save_index(root, idx)
    return f"✅ ingested '{rec['title']}' from {url} → {rec['path']} ({rec['bytes']} bytes)"


# ── Project KB ↔ global compiled_wiki bridge ─────────────────────────────────

def promote(co: str, unit: str, note: str) -> str:
    src = kb.kb_root(co, unit) / "notes" / (note if note.endswith(".md") else note + ".md")
    if not src.exists():
        return f"❌ note not found: {src}"
    WIKI_DIR.mkdir(parents=True, exist_ok=True)
    dst = WIKI_DIR / f"{co}__{unit}__{src.name}"
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return f"✅ promoted to shared wiki: 02_CURRICULUM/compiled_wiki/{dst.name}"


def pull(co: str, unit: str, wiki_note: str) -> str:
    src = WIKI_DIR / (wiki_note if wiki_note.endswith(".md") else wiki_note + ".md")
    if not src.exists():
        return f"❌ wiki note not found: {src}"
    txt = src.read_text(encoding="utf-8")
    fm, body = kb.parse_frontmatter(txt)
    root = kb.kb_root(co, unit)
    kb.scaffold(root, co, unit)
    rec = kb._write_note(root, fm.get("title", src.stem), body,
                         (fm.get("tags") if isinstance(fm.get("tags"), list) else ["from-wiki"]),
                         f"compiled_wiki/{src.name}")
    idx = kb.load_index(root); idx["documents"].append(rec); kb.save_index(root, idx)
    return f"✅ pulled into {co}/{unit} KB → {rec['path']}"


# ── Provenance audit + staleness ─────────────────────────────────────────────

def audit(co: str, unit: str) -> str:
    rows = []
    for n in _notes(co, unit):
        fm, _ = kb.parse_frontmatter(n.read_text(encoding="utf-8", errors="ignore"))
        src = fm.get("source", "")
        if not src or src in ("stdin", "manual", "unknown"):
            rows.append(n.stem)
    if not rows:
        return f"✅ {co}/{unit}: every note has a provenance source."
    return (f"⚠️  {co}/{unit}: {len(rows)} note(s) without a verifiable source:\n  - "
            + "\n  - ".join(rows))


def stale(co: str, unit: str, days: int = 90) -> str:
    cutoff = datetime.date.today() - datetime.timedelta(days=days)
    rows = []
    for n in _notes(co, unit):
        fm, _ = kb.parse_frontmatter(n.read_text(encoding="utf-8", errors="ignore"))
        d = fm.get("date", "")
        try:
            nd = datetime.date.fromisoformat(d[:10])
        except Exception:
            nd = datetime.date.fromtimestamp(n.stat().st_mtime)
        if nd < cutoff:
            rows.append(f"{n.stem} ({nd})")
    if not rows:
        return f"✅ {co}/{unit}: no notes older than {days} days."
    return f"⏳ {co}/{unit}: {len(rows)} note(s) older than {days} days:\n  - " + "\n  - ".join(rows)


# ── Cross-reference graph (wikilinks + shared tags) ──────────────────────────

def graph(co: str, unit: str) -> str:
    notes = _notes(co, unit)
    nodes, edges, tags = [], [], {}
    stems = {n.stem for n in notes}
    for n in notes:
        txt = n.read_text(encoding="utf-8", errors="ignore")
        fm, body = kb.parse_frontmatter(txt)
        nodes.append(n.stem)
        for m in re.findall(r"\[\[([^\]|#]+)", body):
            tgt = kb._slug(m) if hasattr(kb, "_slug") else m.strip()
            if tgt in stems:
                edges.append([n.stem, tgt, "link"])
        nt = fm.get("tags", [])
        for t in (nt if isinstance(nt, list) else [nt]):
            tags.setdefault(t, []).append(n.stem)
    for t, members in tags.items():
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                edges.append([members[i], members[j], f"tag:{t}"])
    g = {"company": co, "unit": unit, "nodes": nodes, "edges": edges}
    out = kb.kb_root(co, unit) / ".kb" / "graph.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(g, indent=2))
    return (f"✅ graph: {len(nodes)} notes, {len(edges)} cross-references "
            f"({sum(1 for e in edges if e[2]=='link')} links, "
            f"{sum(1 for e in edges if e[2].startswith('tag'))} shared-tag) → .kb/graph.json")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="kb_tools")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def cu(p):
        p.add_argument("company"); p.add_argument("unit")

    p = sub.add_parser("semantic"); cu(p); p.add_argument("query"); p.add_argument("--limit", type=int, default=10)
    p = sub.add_parser("add-url"); cu(p); p.add_argument("url"); p.add_argument("--clean", action="store_true")
    p = sub.add_parser("promote"); cu(p); p.add_argument("note")
    p = sub.add_parser("pull"); cu(p); p.add_argument("wiki_note")
    p = sub.add_parser("audit"); cu(p)
    p = sub.add_parser("stale"); cu(p); p.add_argument("--days", type=int, default=90)
    p = sub.add_parser("graph"); cu(p)

    a = ap.parse_args(argv)
    if a.cmd == "semantic":
        print(semantic(a.company, a.unit, a.query, a.limit))
    elif a.cmd == "add-url":
        print(add_url(a.company, a.unit, a.url, a.clean))
    elif a.cmd == "promote":
        print(promote(a.company, a.unit, a.note))
    elif a.cmd == "pull":
        print(pull(a.company, a.unit, a.wiki_note))
    elif a.cmd == "audit":
        print(audit(a.company, a.unit))
    elif a.cmd == "stale":
        print(stale(a.company, a.unit, a.days))
    elif a.cmd == "graph":
        print(graph(a.company, a.unit))
    return 0


if __name__ == "__main__":
    sys.exit(main())
