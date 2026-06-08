#!/usr/bin/env python3
"""
normalize_skills.py — Phase 1 of the Paperclip migration.

Scans 01_SKILLS/*.md, detects metadata format (YAML frontmatter vs 5-line briefing
header), and emits Paperclip-compatible SKILL.md files plus a JSON manifest.

Usage:
    cd /Users/nazeera/Documents/AI_PRODUCER
    source env/bin/activate
    python3 runtime/normalize_skills.py
"""

import json
import os
import re
import sys
from pathlib import Path

import yaml

# 🔗 Path constants derived from __file__ — no hardcoded user paths
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS_SOURCE_DIR = WORKSPACE_ROOT / "01_SKILLS"
OUTPUT_DIR = WORKSPACE_ROOT / "07_PAPERCLIP" / "solocorn-studios" / "skills"
MANIFEST_PATH = WORKSPACE_ROOT / "07_PAPERCLIP" / "scripts" / "skills_manifest.json"

# Files to skip (not skill definitions)
SKIP_FILES = {
    ".ds_store",
    "agents.md",
    "readme.md",
    "contributing.md",
    "license.md",
    ".gitignore",
}


def kebab_slug(filename: str) -> str:
    """Convert 'engineering_ai_engineer.md' → 'engineering-ai-engineer'."""
    base = Path(filename).stem
    # Replace underscores and spaces with hyphens
    slug = re.sub(r"[_\s]+", "-", base).lower()
    # Remove any non-alphanumeric/hyphen characters
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    # Collapse multiple hyphens
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def extract_first_h1(content: str) -> str | None:
    """Extract text from first '# Heading' line."""
    for line in content.splitlines():
        match = re.match(r"^#\s+(.+)$", line.strip())
        if match:
            return match.group(1).strip()
    return None


def extract_first_paragraph(content: str) -> str | None:
    """Extract first non-empty, non-header paragraph."""
    lines = content.splitlines()
    in_header = False
    para_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("---"):
            in_header = not in_header
            continue
        if in_header:
            continue
        if stripped.startswith("#") or stripped.startswith(">"):
            continue
        if not stripped:
            if para_lines:
                break
            continue
        para_lines.append(stripped)
    return " ".join(para_lines)[:300] if para_lines else None


def parse_yaml_frontmatter(content: str) -> tuple[dict | None, str]:
    """
    Parse YAML frontmatter from markdown content.
    Returns (metadata_dict, body_without_frontmatter) or (None, original_content).
    """
    if not content.startswith("---"):
        return None, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return None, content

    try:
        meta = yaml.safe_load(parts[1])
        if not isinstance(meta, dict):
            return None, content
        body = parts[2].lstrip("\n")
        return meta, body
    except yaml.YAMLError:
        return None, content


def parse_briefing_header(content: str) -> tuple[dict | None, str]:
    """
    Parse the 5-line briefing header blockquote anywhere in the document.
    Returns (metadata_dict, body_without_header) or (None, original_content).
    """
    lines = content.splitlines()

    # Find the start of the briefing header block
    header_start = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("> **Briefing Header**") or \
           stripped.startswith("> **Briefing**") or \
           stripped.startswith("> **Agent Briefing**") or \
           stripped.startswith("> **Skill Briefing**") or \
           stripped.startswith("> **Briefing Header**"):
            header_start = i
            break

    if header_start is None:
        return None, content

    # Collect all consecutive blockquote lines starting from header_start
    header_lines = []
    header_end = header_start
    for i in range(header_start, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith(">") or (not stripped and header_lines and lines[i-1].strip().startswith(">")):
            header_lines.append(stripped)
            header_end = i + 1
        elif not stripped and not header_lines:
            continue
        elif header_lines and not stripped:
            # Allow one blank line after blockquote, then stop
            header_end = i + 1
            # Peek next line
            if i + 1 < len(lines) and not lines[i + 1].strip().startswith(">"):
                break
            continue
        elif header_lines and not stripped.startswith(">"):
            break

    if len(header_lines) < 3:
        return None, content

    # Parse the 5 fields from header lines
    meta = {
        "specialty": None,
        "target_output_dir": None,
        "stylistic_tone": None,
        "asset_paths": None,
        "pause_and_confirm": None,
    }

    full_header = "\n".join(header_lines)

    # Try regex extraction for each field
    patterns = {
        "specialty": re.compile(r"[Ss]pecialty[:\s*]+(.+)", re.MULTILINE),
        "target_output_dir": re.compile(r"[Tt]arget output directory[:\s*]+(.+)", re.MULTILINE),
        "stylistic_tone": re.compile(r"[Ss]tylistic tone[:\s*]+(.+)", re.MULTILINE),
        "asset_paths": re.compile(r"[Pp]rioritized asset(?: folder)? paths?[:\s*]+(.+)", re.MULTILINE),
        "pause_and_confirm": re.compile(r"[Ss]trict pause-and-confirm parameters?[:\s*]+(.+)", re.MULTILINE),
    }

    for key, pattern in patterns.items():
        match = pattern.search(full_header)
        if match:
            meta[key] = match.group(1).strip().rstrip("*").strip()

    # Reconstruct body: everything before header + everything after header
    body_before = "\n".join(lines[:header_start]).rstrip("\n")
    body_after = "\n".join(lines[header_end:]).lstrip("\n")
    body = f"{body_before}\n\n{body_after}".strip("\n")
    return meta, body


def normalize_skill_file(filepath: Path) -> dict | None:
    """
    Process a single skill .md file and return its manifest entry.
    Returns None if the file should be skipped.
    """
    filename = filepath.name

    # Skip non-skill files
    if filename.lower() in SKIP_FILES:
        return None
    if filename.startswith("."):
        return None
    if not filename.endswith(".md"):
        return None

    content = filepath.read_text(encoding="utf-8")
    slug = kebab_slug(filename)

    # Try YAML frontmatter first
    meta, body = parse_yaml_frontmatter(content)
    format_type = "yaml_frontmatter"

    if meta is None:
        meta, body = parse_briefing_header(content)
        format_type = "briefing_header"

    if meta is None:
        # Plain markdown — minimal metadata
        meta = {}
        body = content
        format_type = "plain"

    # Derive name from first H1
    name = extract_first_h1(body) or slug.replace("-", " ").title()

    # Derive description
    description = None
    if format_type == "yaml_frontmatter":
        description = meta.get("type") or meta.get("description") or extract_first_paragraph(body)
    elif format_type == "briefing_header":
        description = meta.get("specialty") or extract_first_paragraph(body)
    else:
        description = extract_first_paragraph(body) or ""

    # Build Paperclip SKILL.md frontmatter
    paperclip_meta = {
        "name": name,
        "description": description or "",
    }

    # Add metadata block
    paperclip_meta["metadata"] = {
        "paperclip": {
            "tags": [],
            "source_file": f"01_SKILLS/{filename}",
            "format_detected": format_type,
        }
    }

    # Carry forward original metadata
    if format_type == "yaml_frontmatter":
        if "agent_id" in meta:
            paperclip_meta["metadata"]["paperclip"]["original_agent_id"] = meta["agent_id"]
        if "type" in meta:
            paperclip_meta["metadata"]["paperclip"]["tags"].append(meta["type"])
        if "model_target" in meta:
            paperclip_meta["metadata"]["paperclip"]["model_target"] = meta["model_target"]
        if "output_path" in meta:
            paperclip_meta["metadata"]["paperclip"]["output_path"] = meta["output_path"]
    elif format_type == "briefing_header":
        if meta.get("specialty"):
            # Derive tags from specialty keywords
            specialty = meta["specialty"].lower()
            tag_map = {
                "engineering": "engineering",
                "marketing": "marketing",
                "design": "design",
                "sales": "sales",
                "finance": "finance",
                "support": "support",
                "testing": "testing",
                "product": "product",
                "research": "research",
                "academic": "academic",
                "devops": "devops",
                "ai": "ai",
                "security": "security",
            }
            for keyword, tag in tag_map.items():
                if keyword in specialty:
                    paperclip_meta["metadata"]["paperclip"]["tags"].append(tag)
        if meta.get("target_output_dir"):
            paperclip_meta["metadata"]["paperclip"]["target_output_dir"] = meta["target_output_dir"]
        if meta.get("stylistic_tone"):
            paperclip_meta["metadata"]["paperclip"]["stylistic_tone"] = meta["stylistic_tone"]

    # Deduplicate tags
    paperclip_meta["metadata"]["paperclip"]["tags"] = list(dict.fromkeys(
        paperclip_meta["metadata"]["paperclip"]["tags"]
    ))

    # Write output file
    out_dir = OUTPUT_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "SKILL.md"

    frontmatter_yaml = yaml.dump(paperclip_meta, default_flow_style=False, allow_unicode=True, sort_keys=False)
    output_content = f"---\n{frontmatter_yaml}---\n\n{body}"
    out_file.write_text(output_content, encoding="utf-8")

    return {
        "slug": slug,
        "source_file": str(filepath.relative_to(WORKSPACE_ROOT)),
        "output_file": str(out_file.relative_to(WORKSPACE_ROOT)),
        "name": name,
        "description": description or "",
        "format_detected": format_type,
        "original_metadata": meta,
    }


def main() -> int:
    print("🚀 Solocorn Skill Normalizer — Phase 1")
    print(f"   Source: {SKILLS_SOURCE_DIR}")
    print(f"   Output: {OUTPUT_DIR}")
    print()

    if not SKILLS_SOURCE_DIR.exists():
        print(f"❌ ERROR: Source directory not found: {SKILLS_SOURCE_DIR}")
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    md_files = sorted([f for f in SKILLS_SOURCE_DIR.iterdir() if f.is_file() and f.suffix == ".md"])
    manifest = []
    skipped = []
    errors = []

    for filepath in md_files:
        try:
            entry = normalize_skill_file(filepath)
            if entry:
                manifest.append(entry)
                print(f"  ✅ {filepath.name:50s} → {entry['slug']} ({entry['format_detected']})")
            else:
                skipped.append(filepath.name)
                print(f"  ⏭️  {filepath.name:50s} (skipped)")
        except Exception as e:
            errors.append({"file": filepath.name, "error": str(e)})
            print(f"  ❌ {filepath.name:50s} ERROR: {e}")

    # Write manifest
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    manifest_data = {
        "total_processed": len(manifest),
        "total_skipped": len(skipped),
        "total_errors": len(errors),
        "skipped_files": skipped,
        "errors": errors,
        "entries": manifest,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest_data, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print("─" * 60)
    print(f"📊 Results: {len(manifest)} normalized | {len(skipped)} skipped | {len(errors)} errors")
    print(f"📋 Manifest: {MANIFEST_PATH}")

    if errors:
        print()
        print("⚠️  ERRORS encountered:")
        for err in errors:
            print(f"   • {err['file']}: {err['error']}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
