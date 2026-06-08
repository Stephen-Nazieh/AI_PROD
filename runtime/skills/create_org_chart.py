#!/usr/bin/env python3
"""
create_org_chart.py — Phase 2 of the Paperclip migration.

Generates ~235 agent AGENTS.md files plus COMPANY.md, .paperclip.yaml, and TEAM.md
org subtree definitions from the skills manifest produced by normalize_skills.py.

Usage:
    cd /Users/nazeera/Documents/AI_PRODUCER
    source env/bin/activate
    python3 runtime/create_org_chart.py
"""

import json
import sys
from pathlib import Path

import yaml

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST_PATH = WORKSPACE_ROOT / "07_PAPERCLIP" / "scripts" / "skills_manifest.json"
COMPANY_DIR = WORKSPACE_ROOT / "07_PAPERCLIP" / "deparadigm-media"

# ── Executive layer (manually curated) ──────────────────────────────────────
EXECUTIVES = [
    {
        "slug": "ceo",
        "name": "Chief Executive Officer",
        "title": "Chief Executive Officer",
        "reportsTo": None,
        "skills": ["nexus-strategy", "agents-orchestrator", "specialized-chief-of-staff"],
        "body": (
            "You are the CEO of DeParadigm Media, a local-first AI media production company "
            "operating four monetization channels: Developer EdTech, AP Statistics Movie Series, "
            "Multi-Language Translation Factory, and Ambient Lo-Fi loops.\n\n"
            "Your mandate is strategic oversight, capital allocation, and cross-track alignment. "
            "All inference runs locally through mlx-lm on port 8000. No cloud API dependencies.\n\n"
            "You report to the founder (Stephen). You directly manage the CTO, COO, and CFO."
        ),
    },
    {
        "slug": "cto",
        "name": "Chief Technology Officer",
        "title": "Chief Technology Officer",
        "reportsTo": "ceo",
        "skills": ["engineering-ai-engineer", "engineering-git-workflow-master",
                    "engineering-minimal-change-engineer", "backend-architect-with-memory"],
        "body": (
            "You are the CTO of DeParadigm Media. You own the technical architecture, "
            "the Python bridge ecosystem, local inference infrastructure, and all rendering pipelines.\n\n"
            "Key systems under your care:\n"
            "- orchestrator.py (production daemon)\n"
            "- solocorn_media_bridge.py (FCPXML, FFmpeg, Manim)\n"
            "- graphify/knowledge_graph.py (Postgres-backed nodes)\n"
            "- mlx-lm inference server on port 8000\n\n"
            "You manage the EdTech Lead, AP Stats Lead, Bridge Operator, and OpenClaw Proxy."
        ),
    },
    {
        "slug": "coo",
        "name": "Chief Operating Officer",
        "title": "Chief Operating Officer",
        "reportsTo": "ceo",
        "skills": ["project-management-studio-operations", "project-management-studio-producer",
                    "support-infrastructure-maintainer"],
        "body": (
            "You are the COO of DeParadigm Media. You own studio operations, content scheduling, "
            "translation factory pipelines, and ambient loop production workflows.\n\n"
            "You manage the Translation Factory Lead and the Ambient Loops Lead. "
            "You also coordinate marketing, sales, and support agents across all tracks."
        ),
    },
    {
        "slug": "cfo",
        "name": "Chief Financial Officer",
        "title": "Chief Financial Officer",
        "reportsTo": "ceo",
        "skills": ["finance-financial-analyst", "finance-fpa-analyst",
                    "support-finance-tracker"],
        "body": (
            "You are the CFO of DeParadigm Media. You own budgeting, runway analysis, "
            "and operational expense tracking.\n\n"
            "You interface with the legacy PaperclipEnterpriseGovernor on Postgres port 5433 "
            "and will eventually migrate its ledgers into Paperclip's native budget system.\n\n"
            "You directly manage all finance, legal, and compliance agents."
        ),
    },
    {
        "slug": "edtech-lead",
        "name": "EdTech Track Lead",
        "title": "EdTech Track Lead",
        "reportsTo": "cto",
        "skills": ["solocorn-devops-scriptwriter", "engineering-devops-automator",
                    "vercel-developer", "supabase-developer"],
        "body": (
            "You lead the Developer/Cloud EdTech monetization channel. "
            "Your team produces serverless GCP architectures, AWS transition guides, "
            "and Security+ compliance content.\n\n"
            "Target output: 02_CURRICULUM/01_SOLOCORN_EDTECH/"
        ),
    },
    {
        "slug": "apstats-lead",
        "name": "AP Stats Movie Lead",
        "title": "AP Statistics Movie Lead",
        "reportsTo": "cto",
        "skills": ["ap-stats-narrative-architect", "zotero-research-scout",
                    "academic-psychologist", "visual-director"],
        "body": (
            "You lead the AP Statistics Movie Series — a cinematic, story-driven multi-episode "
            "season mapped to the official College Board AP Stats syllabus.\n\n"
            "Your team generates Manim scenes, voice tracks, and FCPXML timelines.\n\n"
            "Target output: 02_CURRICULUM/02_AP_STATS_MOVIE/ → 03_ASSETS/_HANDOFF_FCP_CAPCUT/"
        ),
    },
    {
        "slug": "translate-lead",
        "name": "Translation Factory Lead",
        "title": "Translation Factory Lead",
        "reportsTo": "coo",
        "skills": ["language-translator", "marketing-china-localization",
                    "marketing-china-market-localization-strategist"],
        "body": (
            "You lead the Multi-Language Translation Factory. "
            "Your team automates Spanish and Mandarin dubbing via XTTS v2 voice cloning.\n\n"
            "You manage localization strategists, voice-AI integration engineers, and quality auditors."
        ),
    },
    {
        "slug": "lofi-lead",
        "name": "Ambient Loops Lead",
        "title": "Ambient Loops Lead",
        "reportsTo": "coo",
        "skills": ["game-audio-engineer", "product-behavioral-nudge-engine"],
        "body": (
            "You lead the Passive Deep-Focus Atmospheric Loops channel. "
            "Your team produces 10-hour coding ambience videos for passive monetization.\n\n"
            "Focus: generative audio, loop composition, and long-form video assembly."
        ),
    },
    {
        "slug": "bridge-operator",
        "name": "Python Bridge Operator",
        "title": "Python Bridge Operator",
        "reportsTo": "cto",
        "skills": ["solocorn-vault-librarian", "engineering-sre",
                    "engineering-incident-response-commander"],
        "body": (
            "You are the runtime bridge between Paperclip and the DeParadigm Media Python ecosystem.\n\n"
            "You execute calls to:\n"
            "- orchestrator.py (ingestion & render pipeline)\n"
            "- solocorn_media_bridge.py (FCPXML, voiceover, manifests)\n"
            "- lesson_compiler.py (blueprint generation)\n"
            "- script_processor.py (scene manifest compilation)\n"
            "- skills.py (vault CRUD & Zotero queries)\n\n"
            "You run as an HTTP server on localhost:3101 and as a Paperclip process adapter."
        ),
    },
    {
        "slug": "openclaw-proxy",
        "name": "OpenClaw Proxy Agent",
        "title": "OpenClaw Proxy Agent",
        "reportsTo": "cto",
        "skills": ["openclaw-bridge-skill"],  # Will be created if needed, or left as placeholder
        "body": (
            "You are the gateway between Paperclip and the OpenClaw daemon running in Docker on port 18789.\n\n"
            "Your adapter type is openclaw_gateway. You translate Paperclip tasks into OpenClaw "
            "sessions and stream results back into the Paperclip activity log.\n\n"
            "Auth token: ***REMOVED-ROTATED-SEE-.docker/.env***"
        ),
    },
]

# ── Reporting-line heuristics ───────────────────────────────────────────────

def determine_reports_to(entry: dict) -> str:
    """Map a skill manifest entry to its Paperclip reportsTo slug."""
    slug = entry["slug"]
    filename = Path(entry["source_file"]).stem
    specialty = (entry["original_metadata"].get("specialty") or "").lower()
    target = (entry["original_metadata"].get("target_output_dir") or "").lower()

    # Strip backticks from target
    target = target.replace("`", "").strip()

    # 1. Target output directory takes precedence
    if "01_solocorn_edtech" in target or "03_devops_control" in target:
        return "edtech-lead"
    if "02_ap_stats_movie" in target:
        return "apstats-lead"
    if "04_vertical_farming" in target:
        return "coo"  # Vertical farming reports to ops

    # 2. Domain keyword heuristics from filename/slug
    domain_prefixes = {
        "engineering-": "cto",
        "engineering_": "cto",
        "devops-": "cto",
        "backend-": "cto",
        "frontend-": "cto",
        "ai-engineer": "cto",
        "data-engineer": "cto",
        "security-": "cto",
        "sre": "cto",
        "incident-response": "cto",
        "git-": "cto",
        "code-": "cto",
        "database-": "cto",
        "cms-": "cto",
        "mobile-app": "cto",
        "rapid-prototyper": "cto",
        "software-architect": "cto",
        "solidity-": "cto",
        "technical-writer": "cto",
        "threat-detection": "cto",
        "voice-ai": "cto",
        "wechat-mini": "cto",
        "lsp-": "cto",
        "filament-": "cto",
        "feishu-": "cto",
        "email-intelligence": "cto",
        "embedded-firmware": "cto",
        "autonomous-optimization": "cto",
        "codebase-onboarding": "cto",
        "blender-": "cto",
        "unity-": "cto",
        "unreal-": "cto",
        "godot-": "cto",
        "roblox-": "cto",
        "macos-": "cto",
        "visionos-": "cto",
        "xr-": "cto",
        "spatial-": "cto",
        "technical-artist": "cto",
        "level-designer": "cto",
        "narrative-designer": "cto",
        "game-designer": "cto",
        "game-audio": "cto",
        "pae-da-vinci": "cto",
        "obsidian-": "cto",
        "zotero-": "apstats-lead",
        "academic-": "apstats-lead",
        "research-": "apstats-lead",
        "youtube-": "apstats-lead",
        "seo-agent": "apstats-lead",
        "thumbnail-agent": "apstats-lead",
        "script-agent": "apstats-lead",
        "visual-director": "apstats-lead",
        "ap-stats-": "apstats-lead",
        "marketing-": "coo",
        "sales-": "coo",
        "design-": "coo",
        "product-": "coo",
        "project-management-": "coo",
        "support-": "coo",
        "customer-service": "coo",
        "healthcare-": "coo",
        "hospitality-": "coo",
        "legal-": "coo",
        "hr-": "coo",
        "retail-": "coo",
        "real-estate-": "coo",
        "recruitment-": "coo",
        "loan-officer": "coo",
        "government-": "coo",
        "specialized-": "coo",
        "finance-": "cfo",
        "accounts-payable": "cfo",
        "compliance-": "cfo",
        "testing-": "cto",
        "stripe-": "cto",
        "nextjs-": "cto",
        "vercel-": "cto",
        "supabase-": "cto",
        "phase-": "cto",
        "scenario-": "cto",
        "studio-launch": "ceo",
        "nexus-strategy": "ceo",
        "agents-orchestrator": "ceo",
        "agentic-identity-trust": "ceo",
        "agent-activation-prompts": "ceo",
        "automation-governance-architect": "ceo",
        "executive-brief": "ceo",
        "handoff-templates": "coo",
        "editor-brief": "coo",
        "sample-lesson": "apstats-lead",
        "solocorn-devops-scriptwriter": "edtech-lead",
        "solocorn-vault-librarian": "bridge-operator",
        "quickstart": "ceo",
        "skill": "cto",
        "claude": "cto",
        "prompttogiveclaude": "cto",
        "git-auto-backup": "cto",
        "report-distribution": "coo",
        "terminal-integration": "cto",
        "vault-scraper": "cto",
        "zk-steward": "cto",
        "blockchain-": "cto",
        "data-consolidation": "cto",
    }

    for prefix, lead in domain_prefixes.items():
        if slug.startswith(prefix) or filename.startswith(prefix):
            return lead

    # 3. Specialty keyword fallback
    if any(k in specialty for k in ["engineering", "devops", "backend", "frontend", "ai/ml", "security"]):
        return "cto"
    if any(k in specialty for k in ["marketing", "sales", "content", "social media"]):
        return "coo"
    if any(k in specialty for k in ["finance", "accounting", "tax", "bookkeeping"]):
        return "cfo"
    if any(k in specialty for k in ["academic", "research", "education", "curriculum"]):
        return "apstats-lead"
    if any(k in specialty for k in ["design", "ux", "ui", "visual"]):
        return "coo"

    # Default fallback
    return "coo"


def generate_agent_file(entry: dict, reports_to: str) -> None:
    """Generate a single AGENTS.md file for a skill-based agent."""
    slug = entry["slug"]
    name = entry["name"]
    description = entry["description"] or f"Agent specializing in {slug.replace('-', ' ')}"

    # Derive a nicer title from name or slug
    title = name if len(name) < 60 else slug.replace("-", " ").title()

    frontmatter = {
        "name": title,
        "title": title,
        "reportsTo": reports_to,
        "skills": [slug],
    }

    body = (
        f"You are **{title}**, a specialist agent at DeParadigm Media.\n\n"
        f"**Domain**: {description}\n\n"
        f"**Primary Skill**: [{slug}](../skills/{slug}/SKILL.md)\n\n"
        f"**Reports To**: {reports_to}\n\n"
        f"All work must route inference through the local mlx-lm server at `http://127.0.0.1:8000/v1`. "
        f"No external cloud APIs unless explicitly authorized by the CTO."
    )

    out_dir = COMPANY_DIR / "agents" / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "AGENTS.md"

    fm_yaml = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False)
    out_file.write_text(f"---\n{fm_yaml}---\n\n{body}\n", encoding="utf-8")


def generate_executive_files() -> None:
    """Write the manually curated C-suite and lead agents."""
    for exec_def in EXECUTIVES:
        slug = exec_def["slug"]
        out_dir = COMPANY_DIR / "agents" / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "AGENTS.md"

        frontmatter = {
            "name": exec_def["name"],
            "title": exec_def["title"],
            "reportsTo": exec_def["reportsTo"],
            "skills": exec_def["skills"],
        }
        fm_yaml = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False)
        out_file.write_text(f"---\n{fm_yaml}---\n\n{exec_def['body']}\n", encoding="utf-8")
        print(f"  🏢 Executive: {slug} → reportsTo={exec_def['reportsTo']}")


def generate_team_files() -> None:
    """Generate TEAM.md org subtree definitions."""
    teams = {
        "executive": {
            "name": "Executive Team",
            "lead": "ceo",
            "members": ["ceo", "cto", "coo", "cfo"],
        },
        "edtech": {
            "name": "EdTech Track",
            "lead": "edtech-lead",
            "members": [],  # populated dynamically
        },
        "ap-stats": {
            "name": "AP Stats Movie Track",
            "lead": "apstats-lead",
            "members": [],
        },
        "translation": {
            "name": "Translation Factory",
            "lead": "translate-lead",
            "members": [],
        },
        "ambient-loops": {
            "name": "Ambient Loops Track",
            "lead": "lofi-lead",
            "members": [],
        },
        "infrastructure": {
            "name": "Infrastructure & Bridge Ops",
            "lead": "cto",
            "members": ["bridge-operator", "openclaw-proxy"],
        },
    }

    # We don't need to populate member lists for TEAM.md; Paperclip's org chart
    # is driven by agents' individual reportsTo fields. TEAM.md is optional grouping.
    for slug, info in teams.items():
        out_dir = COMPANY_DIR / "teams" / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "TEAM.md"

        frontmatter = {
            "name": info["name"],
            "lead": info["lead"],
        }
        fm_yaml = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False)
        body = f"# {info['name']}\n\nLead: **{info['lead']}**\n"
        out_file.write_text(f"---\n{fm_yaml}---\n\n{body}\n", encoding="utf-8")


def generate_company_md() -> None:
    """Write the root COMPANY.md file."""
    out_file = COMPANY_DIR / "COMPANY.md"
    frontmatter = {
        "name": "DeParadigm Media",
        "slug": "deparadigm-media",
        "schema": "agentcompanies/v1",
        "version": "1.0.0",
        "license": "MIT",
        "goals": [
            "Produce world-class educational video content across 4 monetization channels",
            "Maintain full local-first sovereignty on Apple Silicon hardware",
            "Scale from solo operation to autonomous agent-managed studio",
        ],
    }
    fm_yaml = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False)
    body = (
        "# DeParadigm Media\n\n"
        "A local-first, solo-operated AI media production studio based in China.\n\n"
        "## Monetization Channels\n\n"
        "1. **Developer/Cloud EdTech** — Serverless GCP architectures, AWS transitions, Security+ compliance\n"
        "2. **AP Statistics Movie Series** — Cinematic, story-driven multi-episode seasons\n"
        "3. **Multi-Language Translation Factory** — Automated Spanish and Mandarin dubbing via XTTS v2\n"
        "4. **Passive Deep-Focus Atmospheric Loops** — 10-hour coding ambience channels\n\n"
        "## Local Infrastructure\n\n"
        "- **Inference**: mlx-lm server on `http://127.0.0.1:8000/v1`\n"
        "- **Orchestration**: Paperclip on `http://127.0.0.1:3100`\n"
        "- **Bridge**: Python bridge server on `http://127.0.0.1:3101`\n"
        "- **Database**: Embedded PostgreSQL (Paperclip) + Postgres port 5433 (governance ledger)\n"
        "- **Docker**: OpenClaw (18789), Open WebUI (3000), Playwright (30005)\n"
    )
    out_file.write_text(f"---\n{fm_yaml}---\n\n{body}\n", encoding="utf-8")
    print(f"  🏛️  COMPANY.md written")


def generate_paperclip_yaml() -> None:
    """Write the .paperclip.yaml vendor extension file."""
    out_file = COMPANY_DIR / ".paperclip.yaml"
    content = """schema: paperclip/v1

agents:
  ceo:
    adapter:
      type: claude_local
      config:
        cwd: /Users/nazeera/Documents/AI_PRODUCER
        model: claude-sonnet-4-5-20250929
        timeoutSec: 1800
    runtime:
      heartbeat:
        enabled: false
        wakeOnDemand: true

  cto:
    adapter:
      type: claude_local
      config:
        cwd: /Users/nazeera/Documents/AI_PRODUCER
        model: claude-sonnet-4-5-20250929
        timeoutSec: 1800
    runtime:
      heartbeat:
        enabled: false
        wakeOnDemand: true

  coo:
    adapter:
      type: claude_local
      config:
        cwd: /Users/nazeera/Documents/AI_PRODUCER
        model: claude-sonnet-4-5-20250929
        timeoutSec: 1800
    runtime:
      heartbeat:
        enabled: false
        wakeOnDemand: true

  cfo:
    adapter:
      type: claude_local
      config:
        cwd: /Users/nazeera/Documents/AI_PRODUCER
        model: claude-sonnet-4-5-20250929
        timeoutSec: 1800
    runtime:
      heartbeat:
        enabled: false
        wakeOnDemand: true

  openclaw-proxy:
    adapter:
      type: openclaw_gateway
      config:
        url: ws://127.0.0.1:18789
        authToken: ***REMOVED-ROTATED-SEE-.docker/.env***
        timeoutSec: 120
        disableDeviceAuth: true
        sessionKeyStrategy: issue

  bridge-operator:
    adapter:
      type: process
      config:
        command: python3
        args:
          - /Users/nazeera/Documents/AI_PRODUCER/runtime/paperclip_bridge.py
        timeoutSec: 3600
"""
    out_file.write_text(content, encoding="utf-8")
    print(f"  ⚙️  .paperclip.yaml written")


def main() -> int:
    print("🚀 DeParadigm Media Org Chart Generator — Phase 2")
    print(f"   Manifest: {MANIFEST_PATH}")
    print(f"   Output:   {COMPANY_DIR}")
    print()

    if not MANIFEST_PATH.exists():
        print(f"❌ ERROR: Manifest not found. Run normalize_skills.py first.")
        return 1

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    entries = manifest["entries"]

    # Filter out executives that already exist as skills (we'll use our manual defs)
    executive_slugs = {e["slug"] for e in EXECUTIVES}
    skill_entries = [e for e in entries if e["slug"] not in executive_slugs]

    # 1. Write executives
    print("Creating executive layer...")
    generate_executive_files()

    # 2. Bulk-generate skill agents
    print(f"\nCreating {len(skill_entries)} skill agents...")
    reports_counter = {}
    for entry in skill_entries:
        reports_to = determine_reports_to(entry)
        generate_agent_file(entry, reports_to)
        reports_counter[reports_to] = reports_counter.get(reports_to, 0) + 1
        print(f"  👤 {entry['slug']:50s} → reportsTo={reports_to}")

    # 3. Write teams
    print("\nCreating team definitions...")
    generate_team_files()

    # 4. Write COMPANY.md
    print("\nCreating company metadata...")
    generate_company_md()

    # 5. Write .paperclip.yaml
    generate_paperclip_yaml()

    # Summary
    total_agents = len(EXECUTIVES) + len(skill_entries)
    print()
    print("─" * 60)
    print(f"📊 Results: {total_agents} agents created")
    print(f"   Executives: {len(EXECUTIVES)}")
    print(f"   Skill agents: {len(skill_entries)}")
    print("   Reporting distribution:")
    for lead, count in sorted(reports_counter.items(), key=lambda x: -x[1]):
        print(f"      → {lead}: {count}")
    print(f"\n📁 Company package: {COMPANY_DIR}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
