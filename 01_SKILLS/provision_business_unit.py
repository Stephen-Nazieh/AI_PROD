#!/usr/bin/env python3
"""
provision_business_unit.py — Create/sync a Solocorn business unit (channel).

A business unit = a Paperclip Project + same-named Team under the single
"Solocorn Studios" company, plus a unified filesystem home at
business_units/<slug>/ (knowledge/ + production/ + assets/ + BRIEF.md).

This is the canonical "create a channel as and when needed" tool. It is
idempotent: re-running for an existing unit repairs the folder structure,
re-ensures the Paperclip project/team, and rewrites BRIEF.md.

Usage:
    python3 01_SKILLS/provision_business_unit.py list
    python3 01_SKILLS/provision_business_unit.py provision ap-stats
    python3 01_SKILLS/provision_business_unit.py provision podcast \\
        --name "Solocorn Podcast" --domain "Long-form audio interviews"

Registry: 00_CORE/business_units.yaml (single source of truth).
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("ERROR: PyYAML required (pip install pyyaml).", file=sys.stderr)
    raise SystemExit(1)

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = WORKSPACE_ROOT / "00_CORE" / "business_units.yaml"
CORE_VAULT = WORKSPACE_ROOT / "00_CORE"
BU_ROOT = WORKSPACE_ROOT / "business_units"
COMPANY_PKG = WORKSPACE_ROOT / "07_PAPERCLIP" / "companies" / "solocorn-studios"
PAPERCLIP_API = "http://127.0.0.1:3100"

# Standard per-unit production pipeline subdirs (the 2D/3D pipeline stages).
PRODUCTION_DIRS = [
    "01-scripts", "02-storyboards", "03-layout", "04-raw_renders",
    "05-assets", "06-audio", "07-editing", "08-subtitles", "09-deliver",
]


# ── Registry ────────────────────────────────────────────────────────────────

def load_registry() -> dict:
    return yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}


def save_registry(reg: dict) -> None:
    REGISTRY_PATH.write_text(
        yaml.safe_dump(reg, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


# ── Paperclip API ─────────────────────────────────────────────────────────────

def _api(method: str, path: str, payload: dict | None = None) -> tuple[int, dict | list | None]:
    url = f"{PAPERCLIP_API}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode()
            return resp.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        print(f"  ⚠️  Paperclip API unreachable ({e}); filesystem scaffold only.")
        return 0, None


def ensure_paperclip_project(company_id: str, slug: str, name: str, domain: str,
                             folder_rel: str, existing_id: str | None) -> str | None:
    """Ensure a Paperclip project exists; return its id (or None if API down)."""
    # 1. If we already have an id and it still resolves, reuse it.
    if existing_id:
        code, _ = _api("GET", f"/api/companies/{company_id}/projects")
        # (list fetched below; treat existing_id as authoritative if present there)
    code, projects = _api("GET", f"/api/companies/{company_id}/projects")
    if code == 0:
        return existing_id  # API down — keep whatever the registry had
    projects = projects or []
    by_id = {p.get("id"): p for p in projects}
    # Reuse existing id, else match by name, else create.
    pid = existing_id if existing_id in by_id else None
    if not pid:
        for p in projects:
            if (p.get("name") or "").strip().lower() == name.strip().lower():
                pid = p.get("id"); break
    desc = f"{domain}\n\nBusiness-unit home: {folder_rel}/ (knowledge/, production/, assets/)."
    if pid:
        _api("PATCH", f"/api/projects/{pid}", {"description": desc})
        print(f"  ✅ Paperclip project exists: {pid}")
        return pid
    code, created = _api("POST", f"/api/companies/{company_id}/projects",
                         {"name": name, "description": desc})
    if created and created.get("id"):
        print(f"  ✅ created Paperclip project: {created['id']}")
        return created["id"]
    print("  ⚠️  could not create Paperclip project (API error).")
    return None


def ensure_team(slug: str, name: str, team: str) -> None:
    """Ensure the company-package team folder + TEAM.md exists (imported on next sync)."""
    team_dir = COMPANY_PKG / "teams" / team
    team_dir.mkdir(parents=True, exist_ok=True)
    team_md = team_dir / "TEAM.md"
    if not team_md.exists():
        team_md.write_text(
            f"# Team: {name}\n\n"
            f"Business unit `{slug}`. Agents staffing the {name} channel.\n",
            encoding="utf-8",
        )
        print(f"  ✅ created team package: teams/{team}/TEAM.md")
    else:
        print(f"  ✅ team package exists: teams/{team}/")


# ── Filesystem scaffold ───────────────────────────────────────────────────────

def scaffold_folder(slug: str, unit: dict) -> Path:
    home = WORKSPACE_ROOT / unit["folder"]
    (home / "knowledge").mkdir(parents=True, exist_ok=True)
    (home / "assets").mkdir(parents=True, exist_ok=True)
    # production/ is a CONTAINER of runs; each run (episode) gets its own 01–09
    # tree via init_project.py. Don't pre-create the pipeline dirs here.
    prod = home / "production"
    prod.mkdir(parents=True, exist_ok=True)
    prod_readme = prod / "README.md"
    if not prod_readme.exists():
        prod_readme.write_text(
            f"# {unit['name']} — production runs\n\n"
            "Each production run (episode/video) is a subfolder here with the "
            "standard pipeline tree:\n\n"
            "`" + "/  ".join(PRODUCTION_DIRS) + "/`\n\n"
            "Create a run with:\n\n"
            f"    python3 01_SKILLS/init_project.py create {slug}-<run> --title \"...\"\n",
            encoding="utf-8",
        )
    for keep in ("knowledge/.gitkeep",):
        p = home / keep
        if not p.exists():
            p.write_text("", encoding="utf-8")
    write_brief(home, slug, unit)
    print(f"  ✅ folder scaffolded: {unit['folder']}/")
    return home


def write_brief(home: Path, slug: str, unit: dict) -> None:
    brief = home / "BRIEF.md"
    brief.write_text(
        f"# Business Unit: {unit['name']}\n\n"
        f"- **Slug:** `{slug}`\n"
        f"- **Channel:** {unit.get('channel', '—')}\n"
        f"- **Domain:** {unit.get('domain', '—')}\n"
        f"- **Paperclip team:** `{unit.get('team', slug)}`\n"
        f"- **Paperclip project:** `{unit.get('paperclip_project_id', '(unset)')}`\n\n"
        "## Layout\n"
        "- `knowledge/` — curriculum input / source notes for this unit\n"
        "- `production/` — the 01–09 pipeline output (scripts → deliver)\n"
        "- `assets/` — rendered media (gitignored; regenerable)\n\n"
        "## Context\n"
        "Scriptwriting and asset agents for this unit should consult:\n"
        "- [`00_CORE/professional_identity.md`](../../00_CORE/professional_identity.md)\n"
        "- [`00_CORE/monetization_blueprint.md`](../../00_CORE/monetization_blueprint.md)\n"
        "- [`00_CORE/student_context.md`](../../00_CORE/student_context.md) — learner profiles & teaching counter-strategies\n",
        encoding="utf-8",
    )


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_provision(args) -> int:
    reg = load_registry()
    units = reg.setdefault("units", {})
    slug = args.slug
    unit = units.get(slug)
    if unit is None:
        if not args.name:
            print(f"❌ '{slug}' is a new unit — provide --name (and ideally --domain).", file=sys.stderr)
            return 1
        unit = {
            "name": args.name,
            "domain": args.domain or "",
            "team": args.team or slug,
            "folder": f"business_units/{slug}",
            "paperclip_project_id": None,
        }
        units[slug] = unit
        print(f"🆕 new business unit: {slug}")
    else:
        if args.name:
            unit["name"] = args.name
        if args.domain:
            unit["domain"] = args.domain
        print(f"🔁 syncing business unit: {slug}")
    unit.setdefault("folder", f"business_units/{slug}")
    unit.setdefault("team", slug)

    scaffold_folder(slug, unit)
    ensure_team(slug, unit["name"], unit["team"])
    pid = ensure_paperclip_project(
        reg.get("company_id", ""), slug, unit["name"],
        unit.get("domain", ""), unit["folder"], unit.get("paperclip_project_id"),
    )
    if pid:
        unit["paperclip_project_id"] = pid
    save_registry(reg)
    print(f"✅ provisioned '{slug}'. Registry updated.")
    print(f"   (Optional: in Paperclip, link the project's local folder to {unit['folder']}/.)")
    return 0


def provision_from_paperclip_project(project: dict) -> str | None:
    """
    Register + scaffold a business unit from an existing Paperclip project dict.
    Used by the bridge auto-scaffold poller (project created in Paperclip -> unit
    home appears on disk). Idempotent. Returns the unit slug, or None on bad input.
    """
    pid = project.get("id")
    slug = (project.get("urlKey") or pid or "").strip()
    if not slug:
        return None
    reg = load_registry()
    units = reg.setdefault("units", {})
    existing = next((s for s, u in units.items()
                     if u.get("paperclip_project_id") == pid or s == slug), None)
    if existing:
        slug = existing
        unit = units[slug]
    else:
        unit = {
            "name": project.get("name") or slug,
            "domain": (project.get("description") or "").split("\n")[0],
            "team": slug,
            "folder": f"business_units/{slug}",
            "paperclip_project_id": pid,
        }
        units[slug] = unit
    unit.setdefault("folder", f"business_units/{slug}")
    unit.setdefault("team", slug)
    if pid:
        unit["paperclip_project_id"] = pid
    scaffold_folder(slug, unit)
    ensure_team(slug, unit["name"], unit["team"])
    save_registry(reg)
    return slug


def registered_project_ids() -> set:
    """Paperclip project IDs already registered as business units."""
    reg = load_registry()
    return {u.get("paperclip_project_id") for u in reg.get("units", {}).values()
            if u.get("paperclip_project_id")}


def cmd_list(args) -> int:
    reg = load_registry()
    units = reg.get("units", {})
    print(f"Business units under '{reg.get('company')}' ({len(units)}):")
    for slug, u in units.items():
        present = "✓" if (WORKSPACE_ROOT / u.get("folder", "")).exists() else "✗"
        print(f"  [{present} folder] {slug:<14} {u.get('name'):<38} team={u.get('team')} pid={u.get('paperclip_project_id')}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Provision/sync a Solocorn business unit (channel).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("provision", help="Create or re-sync a business unit")
    p.add_argument("slug")
    p.add_argument("--name")
    p.add_argument("--domain")
    p.add_argument("--team")
    p.set_defaults(func=cmd_provision)
    lp = sub.add_parser("list", help="List registered business units")
    lp.set_defaults(func=cmd_list)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
