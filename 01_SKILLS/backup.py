#!/usr/bin/env python3
"""
Studio backup — snapshots the durable, hard-to-regenerate studio state:
  • both Postgres databases (governance :5433, production-tracking :5432)
  • the business-unit registry (00_CORE/business_units.yaml)
  • per-project knowledge bases (notes + index, the curated content)
  • agent personas (library/agents/)

Target: the external RAID if mounted, else .backups/ (gitignored). Timestamped.
Run on demand (`studio backup`) or from cron. Heavy/regenerable artifacts
(renders, raw sources) are deliberately NOT backed up.
"""
from __future__ import annotations

import datetime
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAID = pathlib.Path("/Volumes/SolocornRAID")


def env() -> dict:
    d = {}
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip()
    return d


def dump_db(container: str, user: str, db: str, password: str, out: pathlib.Path) -> str:
    try:
        r = subprocess.run(
            ["docker", "exec", "-e", f"PGPASSWORD={password}", container,
             "pg_dump", "-U", user, "-d", db],
            capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            return f"⚠️  {container}: {r.stderr.strip()[:80]}"
        out.write_text(r.stdout, encoding="utf-8")
        return f"✅ {container} → {out.name} ({len(r.stdout)//1024}K)"
    except Exception as e:
        return f"⚠️  {container}: {e}"


def main() -> int:
    # Maintenance: reclaim duplicate production artifacts before snapshotting state
    # (skip with --no-dedup). Symlinks in-place; gitignored regenerable files only.
    if "--no-dedup" not in sys.argv:
        try:
            import business
            print("🧹 Dedup pass (reclaiming duplicate production artifacts)…")
            business.dedup(None, apply=True)
            print()
        except Exception as ex:
            print(f"  ⚠️ dedup skipped: {ex}\n")

    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = (RAID / "_studio_backups") if RAID.exists() else (ROOT / ".backups")
    dest = base / f"backup_{ts}"
    dest.mkdir(parents=True, exist_ok=True)
    e = env()
    print(f"📦 Backing up to {dest}")

    # 1. databases
    print("  " + dump_db("paperclip_studio_database", e.get("PAPERCLIP_DB_USER", "paperclip_admin"),
                         e.get("PAPERCLIP_DB_NAME", "paperclip_governance"),
                         e.get("PAPERCLIP_DB_PASSWORD", ""), dest / "governance.sql"))
    print("  " + dump_db("solocorn_db", e.get("PRODUCTION_DB_USER", "postgres"),
                         e.get("PRODUCTION_DB_NAME", "postgres"),
                         e.get("PRODUCTION_DB_PASSWORD", ""), dest / "production.sql"))

    # 2. registry + org docs
    core = dest / "00_CORE"
    core.mkdir(exist_ok=True)
    for f in ("business_units.yaml", "PROJECT_ORGANIZATION.md"):
        src = ROOT / "00_CORE" / f
        if src.exists():
            shutil.copy2(src, core / f)
    print(f"  ✅ registry + org docs")

    # 3. knowledge bases (notes + index only — the curated content, not heavy sources)
    kb_count = 0
    for kdir in ROOT.glob("business_units/*/*/knowledge"):
        rel = kdir.relative_to(ROOT)
        for sub in ("notes", ".kb", "README.md"):
            src = kdir / sub
            if src.exists():
                tgt = dest / rel / sub
                tgt.parent.mkdir(parents=True, exist_ok=True)
                (shutil.copytree(src, tgt, dirs_exist_ok=True) if src.is_dir()
                 else shutil.copy2(src, tgt))
        kb_count += 1
    print(f"  ✅ {kb_count} knowledge base(s)")

    # 4. agent personas
    if (ROOT / "library" / "agents").exists():
        shutil.copytree(ROOT / "library" / "agents", dest / "library" / "agents", dirs_exist_ok=True)
        print("  ✅ agent personas")

    # retention: keep the 14 most recent backups
    backups = sorted(base.glob("backup_*"))
    for old in backups[:-14]:
        shutil.rmtree(old, ignore_errors=True)

    total = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())
    print(f"📦 Done — {total//1024}K, retaining {min(len(backups), 14)} backups in {base}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
