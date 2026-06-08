#!/usr/bin/env python3
"""
provision_business_unit.py — Create/sync companies and their business units.

Model (multi-company):
  COMPANY  = a Paperclip company + a package under 07_PAPERCLIP/companies/<slug>/
  BUSINESS UNIT (channel) = a Paperclip Project + same-named Team within a company,
  with a unified filesystem home at business_units/<company>/<unit>/
  (BRIEF.md, knowledge/, production/, assets/).

Idempotent — re-running repairs the folder, re-ensures the Paperclip project/team,
and updates the registry (00_CORE/business_units.yaml, the source of truth).

Usage:
    python3 01_SKILLS/provision_business_unit.py companies
    python3 01_SKILLS/provision_business_unit.py add-company acme --name "Acme Co" [--id <paperclip-id>]
    python3 01_SKILLS/provision_business_unit.py provision solocorn-studios ap-stats
    python3 01_SKILLS/provision_business_unit.py provision acme shorts --name "Acme Shorts" --domain "..."
    python3 01_SKILLS/provision_business_unit.py list [--company solocorn-studios]
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
COMPANIES_PKG_ROOT = WORKSPACE_ROOT / "07_PAPERCLIP" / "companies"
PAPERCLIP_API = "http://127.0.0.1:3100"

PRODUCTION_DIRS = [
    "01-scripts", "02-storyboards", "03-layout", "04-raw_renders",
    "05-assets", "06-audio", "07-editing", "08-subtitles", "09-deliver",
]


# ── Registry ────────────────────────────────────────────────────────────────

def load_registry() -> dict:
    reg = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    reg.setdefault("companies", {})
    return reg


def save_registry(reg: dict) -> None:
    REGISTRY_PATH.write_text(
        yaml.safe_dump(reg, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


# ── Paperclip API ─────────────────────────────────────────────────────────────

def _api(method: str, path: str, payload: dict | None = None) -> tuple[int, object]:
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


def ensure_paperclip_company(slug: str, name: str, existing_id: str | None) -> str | None:
    """Ensure a Paperclip company exists; return its id (None if API down)."""
    code, companies = _api("GET", "/api/companies")
    if code == 0:
        return existing_id
    companies = companies if isinstance(companies, list) else (companies or {}).get("companies", [])
    by_id = {c.get("id"): c for c in companies}
    if existing_id and existing_id in by_id:
        return existing_id
    for c in companies:
        if (c.get("name") or "").strip().lower() == name.strip().lower():
            return c.get("id")
    code, created = _api("POST", "/api/companies", {"name": name})
    if isinstance(created, dict) and created.get("id"):
        print(f"  ✅ created Paperclip company: {created['id']}")
        return created["id"]
    print("  ⚠️  could not create Paperclip company (API error).")
    return existing_id


def ensure_paperclip_project(company_id: str, name: str, domain: str,
                             folder_rel: str, existing_id: str | None) -> str | None:
    code, projects = _api("GET", f"/api/companies/{company_id}/projects")
    if code == 0:
        return existing_id
    projects = projects if isinstance(projects, list) else []
    by_id = {p.get("id"): p for p in projects}
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
    if isinstance(created, dict) and created.get("id"):
        print(f"  ✅ created Paperclip project: {created['id']}")
        return created["id"]
    print("  ⚠️  could not create Paperclip project (API error).")
    return None


def ensure_team(company: dict, unit_slug: str, name: str, team: str) -> None:
    pkg = WORKSPACE_ROOT / company.get("package", f"07_PAPERCLIP/companies/{company['slug']}")
    team_dir = pkg / "teams" / team
    team_dir.mkdir(parents=True, exist_ok=True)
    team_md = team_dir / "TEAM.md"
    if not team_md.exists():
        team_md.write_text(
            f"# Team: {name}\n\nBusiness unit `{unit_slug}` of {company.get('name')}. "
            f"Agents staffing the {name} channel.\n",
            encoding="utf-8",
        )
        print(f"  ✅ created team package: {team_dir.relative_to(WORKSPACE_ROOT)}/TEAM.md")
    else:
        print(f"  ✅ team package exists: {team_dir.relative_to(WORKSPACE_ROOT)}/")


# ── Filesystem scaffold ───────────────────────────────────────────────────────

def scaffold_folder(company_slug: str, unit_slug: str, unit: dict, company_name: str) -> Path:
    home = WORKSPACE_ROOT / unit["folder"]
    (home / "knowledge").mkdir(parents=True, exist_ok=True)
    (home / "assets").mkdir(parents=True, exist_ok=True)
    prod = home / "production"
    prod.mkdir(parents=True, exist_ok=True)
    (prod / "README.md").write_text(
        f"# {unit['name']} ({company_name}) — production runs\n\n"
        "Each production run (episode/video) is a subfolder here with the "
        "standard pipeline tree:\n\n"
        "`" + "/  ".join(PRODUCTION_DIRS) + "/`\n\n"
        "Create a run with:\n\n"
        f"    python3 01_SKILLS/init_project.py create <run> "
        f"--company {company_slug} --unit {unit_slug} --title \"...\"\n",
        encoding="utf-8",
    )
    keep = home / "knowledge" / ".gitkeep"
    if not keep.exists():
        keep.write_text("", encoding="utf-8")
    write_brief(home, company_slug, unit_slug, unit, company_name)
    print(f"  ✅ folder scaffolded: {unit['folder']}/")
    return home


def write_brief(home: Path, company_slug: str, unit_slug: str, unit: dict, company_name: str) -> None:
    depth = "../../.."  # business_units/<company>/<unit>/ -> repo root
    (home / "BRIEF.md").write_text(
        f"# Business Unit: {unit['name']}\n\n"
        f"- **Company:** {company_name} (`{company_slug}`)\n"
        f"- **Slug:** `{unit_slug}`\n"
        f"- **Channel:** {unit.get('channel', '—')}\n"
        f"- **Domain:** {unit.get('domain', '—')}\n"
        f"- **Paperclip team:** `{unit.get('team', unit_slug)}`\n"
        f"- **Paperclip project:** `{unit.get('paperclip_project_id', '(unset)')}`\n\n"
        "## Layout\n"
        "- `knowledge/` — curriculum input / source notes for this unit\n"
        "- `production/` — container of runs; each run has the 01–09 pipeline tree\n"
        "- `assets/` — rendered media (gitignored; regenerable)\n\n"
        "## Context\n"
        "Scriptwriting and asset agents for this unit should consult:\n"
        f"- [`00_CORE/professional_identity.md`]({depth}/00_CORE/professional_identity.md)\n"
        f"- [`00_CORE/monetization_blueprint.md`]({depth}/00_CORE/monetization_blueprint.md)\n"
        f"- [`00_CORE/student_context.md`]({depth}/00_CORE/student_context.md) — learner profiles\n",
        encoding="utf-8",
    )


# ── Core operations ───────────────────────────────────────────────────────────

def get_company(reg: dict, slug: str) -> dict | None:
    c = reg["companies"].get(slug)
    if c is not None:
        c["slug"] = slug
    return c


def provision_unit(company_slug: str, unit_slug: str, name: str | None,
                   domain: str | None, team: str | None) -> int:
    reg = load_registry()
    company = get_company(reg, company_slug)
    if company is None:
        print(f"❌ Unknown company '{company_slug}'. Run add-company first, or: "
              f"{', '.join(reg['companies']) or '(none registered)'}", file=sys.stderr)
        return 1
    units = company.setdefault("units", {})
    unit = units.get(unit_slug)
    if unit is None:
        if not name:
            print(f"❌ '{unit_slug}' is new — provide --name (and ideally --domain).", file=sys.stderr)
            return 1
        unit = {"name": name, "domain": domain or "", "team": team or unit_slug,
                "folder": f"business_units/{company_slug}/{unit_slug}",
                "paperclip_project_id": None}
        units[unit_slug] = unit
        print(f"🆕 new business unit: {company_slug}/{unit_slug}")
    else:
        if name:
            unit["name"] = name
        if domain:
            unit["domain"] = domain
        print(f"🔁 syncing business unit: {company_slug}/{unit_slug}")
    unit.setdefault("folder", f"business_units/{company_slug}/{unit_slug}")
    unit.setdefault("team", unit_slug)

    scaffold_folder(company_slug, unit_slug, unit, company.get("name", company_slug))
    ensure_team(company, unit_slug, unit["name"], unit["team"])
    pid = ensure_paperclip_project(company.get("id", ""), unit["name"],
                                   unit.get("domain", ""), unit["folder"],
                                   unit.get("paperclip_project_id"))
    if pid:
        unit["paperclip_project_id"] = pid
    save_registry(reg)
    print(f"✅ provisioned '{company_slug}/{unit_slug}'.")
    return 0


def provision_from_paperclip_project(company_slug: str, project: dict) -> str | None:
    """Register + scaffold a business unit from a Paperclip project (for the poller)."""
    pid = project.get("id")
    slug = (project.get("urlKey") or pid or "").strip()
    if not slug:
        return None
    reg = load_registry()
    company = get_company(reg, company_slug)
    if company is None:
        return None
    units = company.setdefault("units", {})
    existing = next((s for s, u in units.items()
                     if u.get("paperclip_project_id") == pid or s == slug), None)
    if existing:
        slug = existing
        unit = units[slug]
    else:
        unit = {"name": project.get("name") or slug,
                "domain": (project.get("description") or "").split("\n")[0],
                "team": slug, "folder": f"business_units/{company_slug}/{slug}",
                "paperclip_project_id": pid}
        units[slug] = unit
    unit.setdefault("folder", f"business_units/{company_slug}/{slug}")
    unit.setdefault("team", slug)
    if pid:
        unit["paperclip_project_id"] = pid
    scaffold_folder(company_slug, slug, unit, company.get("name", company_slug))
    ensure_team(company, slug, unit["name"], unit["team"])
    save_registry(reg)
    return slug


def registered_project_ids(company_slug: str | None = None) -> set:
    reg = load_registry()
    out = set()
    for cslug, c in reg["companies"].items():
        if company_slug and cslug != company_slug:
            continue
        for u in c.get("units", {}).values():
            if u.get("paperclip_project_id"):
                out.add(u["paperclip_project_id"])
    return out


def registered_companies() -> list[tuple[str, str]]:
    """Return [(company_slug, company_id), ...] for companies with a Paperclip id."""
    reg = load_registry()
    return [(s, c["id"]) for s, c in reg["companies"].items() if c.get("id")]


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_add_company(args) -> int:
    reg = load_registry()
    slug = args.slug
    company = reg["companies"].get(slug, {})
    company["name"] = args.name or company.get("name", slug)
    company.setdefault("package", f"07_PAPERCLIP/companies/{slug}")
    cid = ensure_paperclip_company(slug, company["name"], args.id or company.get("id"))
    if cid:
        company["id"] = cid
    company.setdefault("units", {})
    reg["companies"][slug] = company
    (WORKSPACE_ROOT / company["package"]).mkdir(parents=True, exist_ok=True)
    save_registry(reg)
    print(f"✅ company '{slug}' registered (id={company.get('id')}).")
    return 0


def cmd_provision(args) -> int:
    return provision_unit(args.company, args.unit, args.name, args.domain, args.team)


def cmd_companies(args) -> int:
    reg = load_registry()
    print(f"Companies ({len(reg['companies'])}):")
    for slug, c in reg["companies"].items():
        print(f"  {slug:<20} {c.get('name'):<24} id={c.get('id')}  units={len(c.get('units', {}))}")
    return 0


def cmd_list(args) -> int:
    reg = load_registry()
    for cslug, c in reg["companies"].items():
        if args.company and cslug != args.company:
            continue
        print(f"{c.get('name')} ({cslug}):")
        for uslug, u in c.get("units", {}).items():
            present = "✓" if (WORKSPACE_ROOT / u.get("folder", "")).exists() else "✗"
            print(f"  [{present}] {uslug:<14} {u.get('name'):<36} pid={u.get('paperclip_project_id')}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Provision companies and business units.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ac = sub.add_parser("add-company", help="Register/create a company")
    ac.add_argument("slug")
    ac.add_argument("--name")
    ac.add_argument("--id", help="Existing Paperclip company id (else one is created)")
    ac.set_defaults(func=cmd_add_company)

    p = sub.add_parser("provision", help="Create or re-sync a business unit")
    p.add_argument("company")
    p.add_argument("unit")
    p.add_argument("--name")
    p.add_argument("--domain")
    p.add_argument("--team")
    p.set_defaults(func=cmd_provision)

    cs = sub.add_parser("companies", help="List companies")
    cs.set_defaults(func=cmd_companies)

    lp = sub.add_parser("list", help="List business units")
    lp.add_argument("--company")
    lp.set_defaults(func=cmd_list)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
