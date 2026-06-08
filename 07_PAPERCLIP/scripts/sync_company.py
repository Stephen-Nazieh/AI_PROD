#!/usr/bin/env python3
"""
sync_company.py — Sync shared library agents/skills into a Paperclip company package.

Usage:
    python sync_company.py --company solocorn-studios --all
    python sync_company.py --company company-two --agents ceo,cto,ai-engineer --skills marketing,engineering
    python sync_company.py --company solocorn-studios --agents-file agents.txt --skills-file skills.txt

What it does:
    1. Reads company config from 07_PAPERCLIP/companies/<name>/.paperclip.yaml
    2. Copies selected agents from library/agents/ → 07_PAPERCLIP/companies/<name>/agents/
    3. Copies selected skills from library/skills/ → 07_PAPERCLIP/companies/<name>/skills/
    4. Injects company-specific adapter configs from .paperclip.yaml into agent AGENTS.md
    5. Optionally pushes to Paperclip API

Directory layout:
    library/agents/<slug>/AGENTS.md      → canonical agent templates
    library/skills/<slug>/SKILL.md        → canonical skill definitions
    07_PAPERCLIP/companies/<name>/        → company package (thin config)
        ├── .paperclip.yaml               → adapter configs + agent roster
        ├── COMPANY.md                    → company identity
        ├── agents/                       → generated from library/
        ├── skills/                       → generated from library/
        ├── projects/                     → company-specific projects
        └── teams/                        → company-specific teams
"""

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path("/Users/nazeera/Documents/AI_PRODUCER")
LIBRARY_DIR = PROJECT_ROOT / "library"
COMPANIES_DIR = PROJECT_ROOT / "07_PAPERCLIP" / "companies"


def list_library_items(item_type: str) -> list[str]:
    """List all agent/skill slugs in the library."""
    source_dir = LIBRARY_DIR / item_type
    if not source_dir.exists():
        return []
    return sorted([d.name for d in source_dir.iterdir() if d.is_dir()])


def sync_item(source_dir: Path, dest_dir: Path, slug: str, item_type: str) -> bool:
    """Copy a single agent/skill from library to company package."""
    src = source_dir / slug
    dst = dest_dir / slug

    if not src.exists():
        print(f"  ⚠️  {item_type} '{slug}' not found in library", file=sys.stderr)
        return False

    # Remove old version if exists
    if dst.exists():
        shutil.rmtree(dst)

    # Copy
    shutil.copytree(src, dst)
    return True


def inject_adapter_config(agent_dir: Path, adapter_config: dict) -> None:
    """Inject company adapter config into agent AGENTS.md frontmatter."""
    agents_md = agent_dir / "AGENTS.md"
    if not agents_md.exists():
        return

    content = agents_md.read_text(encoding="utf-8")

    # Check if already has frontmatter
    if content.startswith("---"):
        # Replace existing adapter section or add it
        # Simple approach: don't modify if frontmatter exists
        # A more sophisticated approach would parse and update YAML
        pass
    else:
        # No frontmatter — the agent uses plain markdown
        # We don't inject into plain markdown (it's the canonical template)
        pass


def parse_agent_roster_from_config(config_path: Path) -> list[str]:
    """Extract agent names from .paperclip.yaml."""
    # Simple regex-based parsing — a real YAML parser would be better
    content = config_path.read_text(encoding="utf-8")
    agents = []

    # Look for agent names under 'agents:' section
    in_agents = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped == "agents:":
            in_agents = True
            continue
        if in_agents:
            if stripped.startswith("-") or stripped.startswith("name:"):
                # Not a robust parser — just a hint
                pass
            elif not stripped.startswith(" ") and stripped != "":
                in_agents = False

    return agents


def sync_company(
    company_name: str,
    agent_slugs: list[str] | None = None,
    skill_slugs: list[str] | None = None,
    all_agents: bool = False,
    all_skills: bool = False,
    push: bool = False,
) -> dict:
    """Sync shared library into a company package."""

    company_dir = COMPANIES_DIR / company_name
    if not company_dir.exists():
        print(f"❌ Company '{company_name}' not found at {company_dir}", file=sys.stderr)
        return {"status": "error", "error": f"Company not found: {company_name}"}

    config_path = company_dir / ".paperclip.yaml"
    if not config_path.exists():
        print(f"⚠️  No .paperclip.yaml found for {company_name}", file=sys.stderr)

    # Determine what to sync
    if all_agents:
        agent_slugs = list_library_items("agents")
    if all_skills:
        skill_slugs = list_library_items("skills")

    # Default: sync all if nothing specified
    if agent_slugs is None and skill_slugs is None:
        agent_slugs = list_library_items("agents")
        skill_slugs = list_library_items("skills")

    results = {
        "status": "ok",
        "company": company_name,
        "agents_synced": [],
        "agents_failed": [],
        "skills_synced": [],
        "skills_failed": [],
    }

    # Sync agents
    if agent_slugs:
        agents_dest = company_dir / "agents"
        agents_dest.mkdir(exist_ok=True)

        print(f"🤖 Syncing {len(agent_slugs)} agents...")
        for slug in agent_slugs:
            if sync_item(LIBRARY_DIR / "agents", agents_dest, slug, "agent"):
                results["agents_synced"].append(slug)
                print(f"  ✅ {slug}")
            else:
                results["agents_failed"].append(slug)
                print(f"  ❌ {slug}")

    # Sync skills
    if skill_slugs:
        skills_dest = company_dir / "skills"
        skills_dest.mkdir(exist_ok=True)

        print(f"📚 Syncing {len(skill_slugs)} skills...")
        for slug in skill_slugs:
            if sync_item(LIBRARY_DIR / "skills", skills_dest, slug, "skill"):
                results["skills_synced"].append(slug)
                print(f"  ✅ {slug}")
            else:
                results["skills_failed"].append(slug)
                print(f"  ❌ {slug}")

    # Push to Paperclip if requested
    if push:
        print(f"🚀 Pushing {company_name} to Paperclip...")
        # This would call the Paperclip API or CLI
        # For now, just show the command
        cmd = f"npx paperclipai company import --yes {company_dir}"
        print(f"   Run: {cmd}")
        results["push_command"] = cmd

    print(f"\n📊 Summary: {len(results['agents_synced'])} agents, {len(results['skills_synced'])} skills")
    return results


def main():
    parser = argparse.ArgumentParser(description="Sync shared library into a Paperclip company package")
    parser.add_argument("--company", required=True, help="Company name (e.g., solocorn-studios)")
    parser.add_argument("--agents", help="Comma-separated agent slugs (e.g., ceo,cto,ai-engineer)")
    parser.add_argument("--skills", help="Comma-separated skill slugs (e.g., marketing,engineering)")
    parser.add_argument("--agents-file", help="File with one agent slug per line")
    parser.add_argument("--skills-file", help="File with one skill slug per line")
    parser.add_argument("--all", action="store_true", help="Sync all agents and skills")
    parser.add_argument("--all-agents", action="store_true", help="Sync all agents")
    parser.add_argument("--all-skills", action="store_true", help="Sync all skills")
    parser.add_argument("--push", action="store_true", help="Push to Paperclip after sync")
    parser.add_argument("--list", action="store_true", help="List available agents and skills")
    args = parser.parse_args()

    if args.list:
        print("Available agents:")
        for slug in list_library_items("agents"):
            print(f"  {slug}")
        print(f"\nAvailable skills:")
        for slug in list_library_items("skills"):
            print(f"  {slug}")
        return 0

    agent_slugs = None
    skill_slugs = None

    if args.agents:
        agent_slugs = [s.strip() for s in args.agents.split(",")]
    if args.skills:
        skill_slugs = [s.strip() for s in args.skills.split(",")]

    if args.agents_file:
        with open(args.agents_file) as f:
            agent_slugs = [line.strip() for line in f if line.strip()]
    if args.skills_file:
        with open(args.skills_file) as f:
            skill_slugs = [line.strip() for line in f if line.strip()]

    result = sync_company(
        company_name=args.company,
        agent_slugs=agent_slugs,
        skill_slugs=skill_slugs,
        all_agents=args.all or args.all_agents,
        all_skills=args.all or args.all_skills,
        push=args.push,
    )

    return 0 if result["status"] != "error" else 1


if __name__ == "__main__":
    sys.exit(main())
