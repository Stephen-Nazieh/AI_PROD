#!/usr/bin/env python3
"""
DeParadigm Media Skills Bridge — Integration layer for Obsidian-skills derived vault operations.
Provides direct filesystem access to 02_CURRICULUM/compiled_wiki/ with oMLX-powered
content processing, search, and batch transformations.
"""
import os
import sys
import json
import re
import subprocess
import urllib.request
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Tuple, Callable, Any

# Master Host Workspace Context Mapping
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
CORE_VAULT = WORKSPACE_ROOT / "00_CORE"
SKILLS_DIR = WORKSPACE_ROOT / "01_SKILLS"
WIKI_DIR = WORKSPACE_ROOT / "02_CURRICULUM" / "compiled_wiki"
RAW_SOURCES_DIR = WORKSPACE_ROOT / "02_CURRICULUM" / "raw_sources"
HANDOFF_DIR = WORKSPACE_ROOT / "03_ASSETS" / "_HANDOFF_FCP_CAPCUT"

# ---------------------------------------------------------------------------
# oMLX Inference Integration
# ---------------------------------------------------------------------------

def run_local_omlx_inference(prompt: str, system_instruction: str, model: str = "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit") -> str:
    url = "http://127.0.0.1:8000/v1/chat/completions"
    """
    Direct, native endpoint query routing straight to the local oMLX engine.
    Bypasses Docker container network layers to exploit full hardware memory speeds.
    """
    
    headers = {"Content-Type": "application/json"}
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1
    }

    req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers)
    try:
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode("utf-8"))
            return res["choices"][0]["message"]["content"]
    except Exception as e:
        return f"ERROR: Direct local connection to native oMLX server failed. Details: {str(e)}"


def clean_raw_content(raw_text: str) -> str:
    """
    Dispatch raw text to the local oMLX server for cleaning and structuring.
    Strips filler words, fixes syntax, formats math, and adds heading hierarchy.
    """
    system_instruction = (
        "You are a document cleaning engine. Your job is to:\n"
        "1. Remove all filler words (um, uh, like, you know, basically)\n"
        "2. Fix any broken code syntax\n"
        "3. Convert math expressions to LaTeX markdown ($...$ or $$...$$)\n"
        "4. Structure the output with clear headings\n"
        "5. Preserve all factual claims and technical details exactly\n"
        "6. Do NOT add opinions or commentary not present in the source"
    )
    return run_local_omlx_inference(raw_text, system_instruction)


# ---------------------------------------------------------------------------
# Vault Path Resolution
# ---------------------------------------------------------------------------

def _resolve_note_path(name_or_path: str) -> Path:
    """
    Resolve a note name or relative path to an absolute path inside compiled_wiki/.

    Accepts bare names ("ZScores") and workspace-relative paths that already
    include the wiki prefix ("02_CURRICULUM/compiled_wiki/ZScores.md"). The prefix
    is stripped so callers passing a full repo-relative path don't produce a
    doubled "compiled_wiki/02_CURRICULUM/compiled_wiki/..." nest.
    """
    p = name_or_path.strip().lstrip("/")
    wiki_rel = WIKI_DIR.relative_to(WORKSPACE_ROOT).as_posix()  # 02_CURRICULUM/compiled_wiki
    if p == wiki_rel or p.startswith(wiki_rel + "/"):
        p = p[len(wiki_rel):].lstrip("/")
    target = WIKI_DIR / p
    if not target.suffix:
        target = target.with_suffix(".md")
    return target


def _ensure_dir(path: Path) -> None:
    """Ensure the parent directory of a file path exists."""
    path.parent.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Note CRUD Operations
# ---------------------------------------------------------------------------

def read_note(name_or_path: str) -> str:
    """Read the full markdown content of a note from the compiled wiki."""
    target = _resolve_note_path(name_or_path)
    if not target.exists():
        return f"ERROR: Note not found: {target}"
    return target.read_text(encoding="utf-8")


def create_note(name: str, content: str, frontmatter: Optional[Dict[str, Any]] = None) -> str:
    """
    Create a new note in the compiled wiki.
    If frontmatter is provided, it is prepended as YAML frontmatter.
    """
    target = _resolve_note_path(name)
    _ensure_dir(target)

    if target.exists():
        return f"ERROR: Note already exists: {target}"

    output = ""
    if frontmatter:
        output += "---\n"
        output += json.dumps(frontmatter, indent=2, ensure_ascii=False).replace('"', '').replace(',', '').replace('{', '').replace('}', '')
        # Actually use yaml-like format
        output = "---\n"
        for key, value in frontmatter.items():
            if isinstance(value, list):
                output += f"{key}:\n"
                for item in value:
                    output += f"  - {item}\n"
            else:
                output += f"{key}: {value}\n"
        output += "---\n\n"

    output += content
    target.write_text(output, encoding="utf-8")
    return f"[+] Created note: {target}"


def append_to_note(name_or_path: str, content: str) -> str:
    """Append content to the end of an existing note."""
    target = _resolve_note_path(name_or_path)
    if not target.exists():
        return f"ERROR: Note not found: {target}"

    with open(target, "a", encoding="utf-8") as f:
        f.write(content)
    return f"[+] Appended to note: {target}"


def update_note(name_or_path: str, content: str, frontmatter: Optional[Dict[str, Any]] = None) -> str:
    """Overwrite an existing note with new content."""
    target = _resolve_note_path(name_or_path)
    if not target.exists():
        return f"ERROR: Note not found: {target}"

    output = ""
    if frontmatter:
        output = "---\n"
        for key, value in frontmatter.items():
            if isinstance(value, list):
                output += f"{key}:\n"
                for item in value:
                    output += f"  - {item}\n"
            else:
                output += f"{key}: {value}\n"
        output += "---\n\n"

    output += content
    target.write_text(output, encoding="utf-8")
    return f"[+] Updated note: {target}"


# ---------------------------------------------------------------------------
# Frontmatter / Property Operations
# ---------------------------------------------------------------------------

def parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """
    Parse YAML frontmatter from markdown content.
    Returns (frontmatter_dict, body_without_frontmatter).
    """
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    fm_text = parts[1].strip()
    body = parts[2].strip()

    fm = {}
    current_key = None
    for line in fm_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- "):
            if current_key:
                fm[current_key].append(stripped[2:].strip())
        elif ":" in stripped:
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value:
                fm[key] = value
            else:
                fm[key] = []
                current_key = key
        else:
            current_key = None

    return fm, body

def set_property(name_or_path: str, property_name: str, property_value: Any) -> str:
    """Set or update a single frontmatter property on a note."""
    target = _resolve_note_path(name_or_path)
    if not target.exists():
        return f"ERROR: Note not found: {target}"

    content = target.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(content)
    fm[property_name] = property_value

    result = update_note(name_or_path, body, fm)
    return result.replace("Updated", "Property set on")


def get_property(name_or_path: str, property_name: str) -> Any:
    """Get the value of a frontmatter property from a note."""
    content = read_note(name_or_path)
    if content.startswith("ERROR:"):
        return content
    fm, _ = parse_frontmatter(content)
    return fm.get(property_name)


# ---------------------------------------------------------------------------
# Search & Query Operations
# ---------------------------------------------------------------------------

def search_vault(query: str, limit: int = 10) -> List[Dict[str, str]]:
    """
    Search the compiled wiki for notes matching a query string.
    Returns list of dicts with 'path', 'title', and 'snippet' keys.
    """
    results = []
    query_lower = query.lower()

    for md_file in WIKI_DIR.rglob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        if query_lower in content.lower():
            # Extract snippet around first match
            idx = content.lower().find(query_lower)
            start = max(0, idx - 60)
            end = min(len(content), idx + len(query) + 60)
            snippet = content[start:end].replace("\n", " ")

            # Extract title from first heading or filename
            title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            title = title_match.group(1) if title_match else md_file.stem

            results.append({
                "path": str(md_file.relative_to(WIKI_DIR)),
                "title": title,
                "snippet": f"...{snippet}..."
            })

            if len(results) >= limit:
                break

    return results


def list_tags(sort_by: str = "count") -> Dict[str, int]:
    """
    Extract all tags from frontmatter and inline tags across the vault.
    Returns dict mapping tag string to occurrence count.
    """
    tags: Dict[str, int] = {}

    for md_file in WIKI_DIR.rglob("*.md"):
        content = md_file.read_text(encoding="utf-8")

        # Frontmatter tags
        fm, _ = parse_frontmatter(content)
        fm_tags = fm.get("tags", [])
        if isinstance(fm_tags, str):
            fm_tags = [fm_tags]
        for tag in fm_tags:
            tags[tag] = tags.get(tag, 0) + 1

        # Inline tags (#tag)
        for match in re.finditer(r"#([a-zA-Z0-9_\-/]+)", content):
            tag = match.group(1)
            tags[tag] = tags.get(tag, 0) + 1

    if sort_by == "count":
        tags = dict(sorted(tags.items(), key=lambda x: x[1], reverse=True))

    return tags


def get_backlinks(name_or_path: str) -> List[str]:
    """
    Find all notes in the vault that wikilink to the target note.
    Returns list of note names (without extension).
    """
    target = _resolve_note_path(name_or_path)
    target_name = target.stem
    backlinks = []

    for md_file in WIKI_DIR.rglob("*.md"):
        if md_file == target:
            continue
        content = md_file.read_text(encoding="utf-8")
        # Match wikilinks to the target name (with or without display text)
        pattern = re.compile(rf"\[\[{re.escape(target_name)}(?:\||#|\]\])")
        if pattern.search(content):
            backlinks.append(md_file.stem)

    return backlinks


def query_tasks(status: Optional[str] = None, file_name: Optional[str] = None) -> List[Dict[str, str]]:
    """
    Query incomplete or complete tasks across the vault.
    Status values: 'todo' (unchecked), 'done' (checked).
    """
    tasks = []
    files_to_scan = []

    if file_name:
        target = _resolve_note_path(file_name)
        if target.exists():
            files_to_scan = [target]
    else:
        files_to_scan = list(WIKI_DIR.rglob("*.md"))

    for md_file in files_to_scan:
        content = md_file.read_text(encoding="utf-8")
        lines = content.splitlines()

        for i, line in enumerate(lines):
            if status == "todo" and re.match(r"^\s*- \[ \]", line):
                tasks.append({
                    "file": md_file.stem,
                    "line": i + 1,
                    "task": line.strip()
                })
            elif status == "done" and re.match(r"^\s*- \[x\]", line):
                tasks.append({
                    "file": md_file.stem,
                    "line": i + 1,
                    "task": line.strip()
                })
            elif status is None and re.match(r"^\s*- \[[ x]\]", line):
                tasks.append({
                    "file": md_file.stem,
                    "line": i + 1,
                    "task": line.strip()
                })

    return tasks


# ---------------------------------------------------------------------------
# Daily Notes
# ---------------------------------------------------------------------------

def daily_note_path() -> Path:
    """Return the path for today's daily note, creating the directory if needed."""
    today = datetime.now().strftime("%Y-%m-%d")
    daily_dir = WIKI_DIR / "Daily Notes"
    daily_dir.mkdir(parents=True, exist_ok=True)
    return daily_dir / f"{today}.md"


def read_daily_note() -> str:
    """Read today's daily note, creating it with a template if missing."""
    path = daily_note_path()
    if not path.exists():
        template = f"""---
date: {datetime.now().strftime("%Y-%m-%d")}
tags:
  - daily
---

# {datetime.now().strftime("%Y-%m-%d")}

## Tasks

## Notes

## Links
"""
        path.write_text(template, encoding="utf-8")
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Batch Operations
# ---------------------------------------------------------------------------

def batch_transform(query: str, transform: Callable[[str, Dict[str, Any]], Tuple[str, Dict[str, Any]]]) -> str:
    """
    Apply a transformation function to all notes matching a query.
    The transform function receives (content_body, frontmatter_dict) and returns
    (new_content_body, new_frontmatter_dict).
    """
    matching = search_vault(query, limit=1000)
    modified_count = 0

    for result in matching:
        target = WIKI_DIR / result["path"]
        content = target.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(content)

        new_body, new_fm = transform(body, fm)

        if new_body != body or new_fm != fm:
            update_note(result["path"], new_body, new_fm)
            modified_count += 1

    return f"[+] Batch transform complete. Modified {modified_count} notes."


# ---------------------------------------------------------------------------
# Raw Source Processing
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Raw Source Processing
# ---------------------------------------------------------------------------

def process_raw_sources() -> str:
    """
    Scan 02_CURRICULUM/raw_sources/ for unprocessed files, clean them via oMLX,
    and write structured nodes into 02_CURRICULUM/compiled_wiki/.
    """
    processed = 0
    rejected = 0

    for ingest_dir in [RAW_SOURCES_DIR / "youtube_ingest", RAW_SOURCES_DIR / "web_ingest"]:
        if not ingest_dir.exists():
            continue

        for raw_file in ingest_dir.iterdir():
            if raw_file.is_dir():
                continue

            # 🛡️ Protection Guard: Skip hidden macOS system files (.DS_Store, etc.)
            if raw_file.name.startswith("."):
                continue

            content = raw_file.read_text(encoding="utf-8", errors="ignore")
            if not content.strip():
                rejected_dir = RAW_SOURCES_DIR / "_rejected"
                rejected_dir.mkdir(exist_ok=True)
                raw_file.rename(rejected_dir / raw_file.name)
                rejected += 1
                continue

            cleaned = clean_raw_content(content)

            slug = raw_file.stem.lower().replace(" ", "_").replace("-", "_")[:40]
            source_type = "youtube" if "youtube" in str(ingest_dir) else "web"
            date_str = datetime.now().strftime("%Y-%m-%d")
            out_name = f"{slug}_{source_type}_{date_str}.md"

            frontmatter = {
                "title": raw_file.stem,
                "date": date_str,
                "tags": [source_type, "auto-ingested"],
                "source": str(raw_file.name)
            }

            result = create_note(out_name, cleaned, frontmatter)
            if result.startswith("[+]"):
                processed += 1
            else:
                rejected += 1

    return f"[+] Processed {processed} raw sources, rejected {rejected}."


# ---------------------------------------------------------------------------
# Zotero Integration
# ---------------------------------------------------------------------------

def _get_zotero_db_path() -> Optional[Path]:
    """
    Auto-detect the Zotero SQLite database path on macOS.
    Searches ~/Library/Application Support/Zotero/Profiles/ for zotero.sqlite.
    """
    zotero_base = Path.home() / "Library" / "Application Support" / "Zotero" / "Profiles"
    if not zotero_base.exists():
        return None
    for profile_dir in zotero_base.iterdir():
        if profile_dir.is_dir():
            db_path = profile_dir / "zotero.sqlite"
            if db_path.exists():
                return db_path
    return None


def _query_zotero_db(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """
    Execute a read-only query against the Zotero SQLite database.
    Returns a list of row dictionaries.
    """
    db_path = _get_zotero_db_path()
    if not db_path:
        return [{"error": "Zotero database not found. Ensure Zotero Desktop is installed."}]

    try:
        import sqlite3
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except Exception as e:
        return [{"error": f"Zotero DB query failed: {str(e)}"}]


def search_zotero_keyword(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Search Zotero items by keyword across title, abstract, and notes.
    Uses direct SQLite access to the local Zotero database.
    """
    sql = """
    SELECT i.itemID, idv.value as title,
           ic.dateAdded, ic.dateModified,
           it.typeName as item_type
    FROM items i
    JOIN itemData id ON i.itemID = id.itemID
    JOIN itemDataValues idv ON id.valueID = idv.valueID
    JOIN fields f ON id.fieldID = f.fieldID
    JOIN itemTypes it ON i.itemTypeID = it.itemTypeID
    LEFT JOIN itemCreators icr ON i.itemID = icr.itemID
    LEFT JOIN creators c ON icr.creatorID = c.creatorID
    JOIN itemAttachments ia ON i.itemID = ia.parentItemID
    WHERE f.fieldName = 'title'
      AND (idv.value LIKE ? OR idv.value LIKE ?)
    GROUP BY i.itemID
    ORDER BY ic.dateAdded DESC
    LIMIT ?
    """
    like_query = f"%{query}%"
    return _query_zotero_db(sql, (like_query, like_query, limit))


def search_zotero_author(author_name: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Search Zotero items by author name.
    """
    sql = """
    SELECT i.itemID, idv.value as title, c.firstName, c.lastName,
           ic.dateAdded, it.typeName as item_type
    FROM items i
    JOIN itemData id ON i.itemID = id.itemID
    JOIN itemDataValues idv ON id.valueID = idv.valueID
    JOIN fields f ON id.fieldID = f.fieldID
    JOIN itemTypes it ON i.itemTypeID = it.itemTypeID
    JOIN itemCreators icr ON i.itemID = icr.itemID
    JOIN creators c ON icr.creatorID = c.creatorID
    WHERE f.fieldName = 'title'
      AND (c.firstName LIKE ? OR c.lastName LIKE ?)
    GROUP BY i.itemID
    ORDER BY ic.dateAdded DESC
    LIMIT ?
    """
    like_name = f"%{author_name}%"
    return _query_zotero_db(sql, (like_name, like_name, limit))


def get_zotero_tags() -> List[str]:
    """
    Retrieve all user-defined tags from the Zotero database.
    """
    sql = "SELECT DISTINCT name FROM tags ORDER BY name"
    rows = _query_zotero_db(sql)
    return [row["name"] for row in rows if "name" in row]


def search_zotero_by_tag(tag: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Search Zotero items by tag.
    """
    sql = """
    SELECT i.itemID, idv.value as title, t.name as tag,
           ic.dateAdded, it.typeName as item_type
    FROM items i
    JOIN itemData id ON i.itemID = id.itemID
    JOIN itemDataValues idv ON id.valueID = idv.valueID
    JOIN fields f ON id.fieldID = f.fieldID
    JOIN itemTypes it ON i.itemTypeID = it.itemTypeID
    JOIN itemTags itg ON i.itemID = itg.itemID
    JOIN tags t ON itg.tagID = t.tagID
    WHERE f.fieldName = 'title'
      AND t.name = ?
    ORDER BY ic.dateAdded DESC
    LIMIT ?
    """
    return _query_zotero_db(sql, (tag, limit))


def search_zotero_annotations(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Search user annotations and notes in Zotero for a given query.
    """
    sql = """
    SELECT i.itemID, idv.value as title, ia.text as annotation_text,
           it.typeName as item_type
    FROM items i
    JOIN itemData id ON i.itemID = id.itemID
    JOIN itemDataValues idv ON id.valueID = idv.valueID
    JOIN fields f ON id.fieldID = f.fieldID
    JOIN itemTypes it ON i.itemTypeID = it.itemTypeID
    JOIN itemAnnotations ia ON i.itemID = ia.parentItemID
    WHERE f.fieldName = 'title'
      AND ia.text LIKE ?
    ORDER BY i.itemID
    LIMIT ?
    """
    like_query = f"%{query}%"
    return _query_zotero_db(sql, (like_query, limit))


def search_zotero_semantic(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Semantic search through Zotero items using local oMLX inference.
    Retrieves item metadata, then dispatches to oMLX for conceptual relevance ranking.
    """
    # First, get candidate items (recent additions and keyword matches)
    candidates = search_zotero_keyword(query, limit=limit * 3)
    if not candidates or "error" in candidates[0]:
        return candidates

    # Build a prompt for oMLX to rank relevance
    item_texts = []
    for idx, item in enumerate(candidates):
        title = item.get("title", "Untitled")
        item_texts.append(f"{idx + 1}. {title}")

    prompt = (
        f"Given the research query: '{query}'\n\n"
        f"Rate the relevance of these Zotero items on a scale of 1-10.\n"
        f"Return ONLY a JSON array of objects with fields: index, relevance_score, reason.\n\n"
        f"Items:\n" + "\n".join(item_texts)
    )

    system_instruction = (
        "You are a research librarian. Evaluate bibliographic relevance precisely. "
        "Return only valid JSON. No markdown formatting, no explanations outside the JSON."
    )

    response = run_local_omlx_inference(prompt, system_instruction)

    # Try to extract JSON from response
    try:
        # Find JSON array in response
        json_start = response.find("[")
        json_end = response.rfind("]") + 1
        if json_start >= 0 and json_end > json_start:
            rankings = json.loads(response[json_start:json_end])
            # Sort by relevance score descending
            rankings.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
            # Return top results with ranking metadata
            results = []
            for r in rankings[:limit]:
                idx = r.get("index", 1) - 1
                if 0 <= idx < len(candidates):
                    item = candidates[idx].copy()
                    item["relevance_score"] = r.get("relevance_score", 0)
                    item["relevance_reason"] = r.get("reason", "")
                    results.append(item)
            return results
    except Exception:
        pass

    # Fallback: return candidates as-is
    return candidates[:limit]


def translate_zotero_text(text: str, target_lang: str = "English") -> str:
    """
    Translate Zotero metadata (titles, abstracts) using local oMLX.
    target_lang: 'English' or 'Chinese'
    """
    prompt = f"Translate the following text to {target_lang}. Preserve academic terminology precisely.\n\n{text}"
    system_instruction = (
        "You are a precise academic translator. "
        "Preserve technical terms, author names, and citation conventions exactly. "
        "Output only the translation, no additional commentary."
    )
    return run_local_omlx_inference(prompt, system_instruction)


def get_zotero_collections() -> List[Dict[str, Any]]:
    """
    List all Zotero collections with item counts.
    """
    sql = """
    SELECT c.collectionID, c.collectionName, c.parentCollectionID,
           COUNT(ci.itemID) as item_count
    FROM collections c
    LEFT JOIN collectionItems ci ON c.collectionID = ci.collectionID
    GROUP BY c.collectionID
    ORDER BY c.collectionName
    """
    return _query_zotero_db(sql)


def export_zotero_bibliography(query: str, topic_slug: str) -> str:
    """
    Search Zotero comprehensively and export results as a wiki note
    into 02_CURRICULUM/compiled_wiki/bibliographies/.
    Performs multi-strategy search (semantic + keyword + tag + annotation).
    """
    print(f"[*] Running comprehensive Zotero search for: {query}")

    # Multi-strategy search
    semantic_results = search_zotero_semantic(query, limit=10)
    keyword_results = search_zotero_keyword(query, limit=10)
    annotation_results = search_zotero_annotations(query, limit=10)

    # Deduplicate by itemID
    seen_ids = set()
    all_items = []
    for result_set in [semantic_results, keyword_results, annotation_results]:
        for item in result_set:
            if "error" in item:
                continue
            item_id = item.get("itemID")
            if item_id and item_id not in seen_ids:
                seen_ids.add(item_id)
                all_items.append(item)

    if not all_items:
        return f"[!] No Zotero results found for query: {query}"

    # Build bibliography markdown
    today = datetime.now().strftime("%Y-%m-%d")
    bib_lines = [
        "---",
        f"title: \"{query} — Zotero Bibliography\"",
        f"date: {today}",
        "tags:",
        "  - bibliography",
        "  - zotero",
        f"  - {topic_slug}",
        f"zotero_query: \"{query}\"",
        "sources_found: " + str(len(all_items)),
        "---",
        "",
        f"# {query} — Research Bibliography",
        "",
        f"*Auto-generated from local Zotero library on {today}*",
        "",
        "- Research Topic",
    ]

    for idx, item in enumerate(all_items, 1):
        title = item.get("title", "Untitled")
        item_type = item.get("item_type", "Unknown")
        relevance = item.get("relevance_score", "")
        rel_reason = item.get("relevance_reason", "")

        bib_lines.append(f"\t- {idx}. {title}")
        bib_lines.append(f"\t\t- Type: {item_type}")
        if relevance:
            bib_lines.append(f"\t\t- Relevance: {relevance}/10")
        if rel_reason:
            bib_lines.append(f"\t\t- Reason: {rel_reason}")
        bib_lines.append(f"\t\t- Zotero: zotero://select/library/items/{item.get('itemID', '')}")

    bib_content = "\n".join(bib_lines)

    # Write to compiled_wiki
    bib_dir = WIKI_DIR / "bibliographies"
    bib_dir.mkdir(parents=True, exist_ok=True)
    bib_path = bib_dir / f"{topic_slug}-zotero-bib.md"

    bib_path.write_text(bib_content, encoding="utf-8")
    return f"[+] Exported {len(all_items)} items to {bib_path}"


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("[+] DeParadigm Media Skills Bridge Online.")
    print(f"    Wiki directory: {WIKI_DIR}")
    print(f"    Raw sources:    {RAW_SOURCES_DIR}")
    print("    Available: read_note, create_note, append_to_note, search_vault,")
    print("               list_tags, get_backlinks, query_tasks, process_raw_sources,")
    print("               run_local_omlx_inference, batch_transform,")
    print("               search_zotero_keyword, search_zotero_semantic,")
    print("               search_zotero_author, search_zotero_by_tag,")
    print("               search_zotero_annotations, get_zotero_tags,")
    print("               get_zotero_collections, export_zotero_bibliography,")
    print("               translate_zotero_text")
