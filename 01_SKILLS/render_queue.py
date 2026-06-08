#!/usr/bin/env python3
"""
render_queue.py — Async Render Queue for DeParadigm Media Media Production

Provides SQLite-backed job queueing with parallel workers for:
  - Blender headless renders
  - Manim scene renders
  - After Effects batch renders
  - Motion project renders
  - DaVinci Resolve batch renders
  - FFmpeg transcoding/muxing
  - ComfyUI image generation
  - Custom shell commands

Usage:
    # Enqueue a job
    python render_queue.py enqueue --project ap-stats-movie --shot SC001 --renderer blender --command "blender --background scene.blend --render-frame 1"

    # Start worker pool
    python render_queue.py worker --workers 4 --project ap-stats-movie

    # Check status
    python render_queue.py status --project ap-stats-movie

    # Retry failed jobs
    python render_queue.py retry --project ap-stats-movie
"""

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

# ── Configuration ───────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUEUE_DB = PROJECT_ROOT / "08_RENDER_FARM" / "queue.db"
LOGS_DIR = PROJECT_ROOT / "08_RENDER_FARM" / "logs"

DEFAULT_WORKERS = 4
DEFAULT_TIMEOUT = 3600  # 1 hour
MAX_RETRIES = 2

# ── Data Model ──────────────────────────────────────────────────────────────

@dataclass
class RenderJob:
    job_id: int | None
    project_id: str
    shot_id: str
    renderer: str  # blender, manim, after_effects, motion, resolve, ffmpeg, comfyui, custom
    command: str
    cwd: str
    env_json: str
    output_path: str
    log_path: str
    priority: int  # 1-10, lower = higher priority
    status: str  # queued, running, completed, failed, retrying, cancelled
    retry_count: int
    created_at: str
    started_at: str | None
    completed_at: str | None
    error_message: str | None
    exit_code: int | None


# ── Database Layer ──────────────────────────────────────────────────────────

class QueueDatabase:
    def __init__(self, db_path: Path = QUEUE_DB):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS render_jobs (
                    job_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    shot_id TEXT NOT NULL,
                    renderer TEXT NOT NULL,
                    command TEXT NOT NULL,
                    cwd TEXT DEFAULT '.',
                    env_json TEXT DEFAULT '{}',
                    output_path TEXT,
                    log_path TEXT,
                    priority INTEGER DEFAULT 5,
                    status TEXT DEFAULT 'queued',
                    retry_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now')),
                    started_at TEXT,
                    completed_at TEXT,
                    error_message TEXT,
                    exit_code INTEGER
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_jobs_project_status
                ON render_jobs(project_id, status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_jobs_status_priority
                ON render_jobs(status, priority, created_at)
            """)
            conn.commit()

    def enqueue(self, job: RenderJob) -> int:
        with self._connect() as conn:
            cursor = conn.execute("""
                INSERT INTO render_jobs
                (project_id, shot_id, renderer, command, cwd, env_json,
                 output_path, log_path, priority, status, retry_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job.project_id, job.shot_id, job.renderer, job.command,
                job.cwd, job.env_json, job.output_path, job.log_path,
                job.priority, job.status, job.retry_count, job.created_at,
            ))
            conn.commit()
            return cursor.lastrowid

    def dequeue(self, project_id: str | None = None) -> RenderJob | None:
        """Atomically fetch the highest-priority queued job."""
        with self._connect() as conn:
            if project_id:
                row = conn.execute("""
                    SELECT * FROM render_jobs
                    WHERE project_id = ? AND status = 'queued'
                    ORDER BY priority ASC, created_at ASC
                    LIMIT 1
                """, (project_id,)).fetchone()
            else:
                row = conn.execute("""
                    SELECT * FROM render_jobs
                    WHERE status = 'queued'
                    ORDER BY priority ASC, created_at ASC
                    LIMIT 1
                """).fetchone()

            if not row:
                return None

            job = self._row_to_job(row)

            # Mark as running
            conn.execute("""
                UPDATE render_jobs
                SET status = 'running', started_at = datetime('now')
                WHERE job_id = ? AND status = 'queued'
            """, (job.job_id,))

            if conn.total_changes == 0:
                # Another worker grabbed it
                return None

            conn.commit()
            return job

    def update_status(self, job_id: int, status: str, error_message: str | None = None,
                      exit_code: int | None = None) -> None:
        with self._connect() as conn:
            conn.execute("""
                UPDATE render_jobs
                SET status = ?, error_message = ?, exit_code = ?,
                    completed_at = CASE WHEN ? IN ('completed', 'failed') THEN datetime('now') ELSE completed_at END
                WHERE job_id = ?
            """, (status, error_message, exit_code, status, job_id))
            conn.commit()

    def retry_failed(self, project_id: str | None = None) -> int:
        """Reset failed jobs to queued if retry_count < MAX_RETRIES."""
        with self._connect() as conn:
            if project_id:
                cursor = conn.execute("""
                    UPDATE render_jobs
                    SET status = 'queued', retry_count = retry_count + 1,
                        error_message = NULL, exit_code = NULL,
                        started_at = NULL, completed_at = NULL
                    WHERE project_id = ? AND status = 'failed' AND retry_count < ?
                """, (project_id, MAX_RETRIES))
            else:
                cursor = conn.execute("""
                    UPDATE render_jobs
                    SET status = 'queued', retry_count = retry_count + 1,
                        error_message = NULL, exit_code = NULL,
                        started_at = NULL, completed_at = NULL
                    WHERE status = 'failed' AND retry_count < ?
                """, (MAX_RETRIES,))
            conn.commit()
            return cursor.rowcount

    def get_status(self, project_id: str | None = None) -> dict:
        with self._connect() as conn:
            if project_id:
                rows = conn.execute("""
                    SELECT status, COUNT(*) as count
                    FROM render_jobs
                    WHERE project_id = ?
                    GROUP BY status
                """, (project_id,)).fetchall()
                total = conn.execute(
                    "SELECT COUNT(*) FROM render_jobs WHERE project_id = ?",
                    (project_id,)
                ).fetchone()[0]
            else:
                rows = conn.execute("""
                    SELECT status, COUNT(*) as count
                    FROM render_jobs
                    GROUP BY status
                """).fetchall()
                total = conn.execute("SELECT COUNT(*) FROM render_jobs").fetchone()[0]

            counts = {row["status"]: row["count"] for row in rows}
            return {
                "total": total,
                "queued": counts.get("queued", 0),
                "running": counts.get("running", 0),
                "completed": counts.get("completed", 0),
                "failed": counts.get("failed", 0),
                "retrying": counts.get("retrying", 0),
                "cancelled": counts.get("cancelled", 0),
            }

    def get_jobs(self, project_id: str | None = None, status: str | None = None,
                 limit: int = 50) -> list[RenderJob]:
        with self._connect() as conn:
            query = "SELECT * FROM render_jobs WHERE 1=1"
            params = []
            if project_id:
                query += " AND project_id = ?"
                params.append(project_id)
            if status:
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [self._row_to_job(row) for row in rows]

    def _row_to_job(self, row: sqlite3.Row) -> RenderJob:
        return RenderJob(
            job_id=row["job_id"],
            project_id=row["project_id"],
            shot_id=row["shot_id"],
            renderer=row["renderer"],
            command=row["command"],
            cwd=row["cwd"],
            env_json=row["env_json"],
            output_path=row["output_path"],
            log_path=row["log_path"],
            priority=row["priority"],
            status=row["status"],
            retry_count=row["retry_count"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            error_message=row["error_message"],
            exit_code=row["exit_code"],
        )


# ── Worker ──────────────────────────────────────────────────────────────────

class RenderWorker:
    def __init__(self, db: QueueDatabase, worker_id: int = 0):
        self.db = db
        self.worker_id = worker_id
        self.running = False

    def run_once(self, project_id: str | None = None, timeout: int = DEFAULT_TIMEOUT) -> bool:
        """Process one job. Returns True if a job was processed."""
        job = self.db.dequeue(project_id)
        if not job:
            return False

        print(f"[Worker {self.worker_id}] Job {job.job_id}: {job.renderer} → {job.shot_id}")

        # Ensure log directory exists
        log_path = Path(job.log_path) if job.log_path else None
        if log_path:
            log_path.parent.mkdir(parents=True, exist_ok=True)

        # Prepare environment
        env = os.environ.copy()
        try:
            env.update(json.loads(job.env_json or "{}"))
        except json.JSONDecodeError:
            pass

        # Resolve working directory
        cwd = Path(job.cwd)
        if not cwd.is_absolute():
            cwd = PROJECT_ROOT / cwd
        cwd = cwd.resolve()

        # Execute command
        start_time = time.time()
        try:
            result = subprocess.run(
                job.command,
                shell=True,
                cwd=str(cwd),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            elapsed = time.time() - start_time

            # Write log
            if log_path:
                log_content = (
                    f"# Render Job {job.job_id}\n"
                    f"# Project: {job.project_id}\n"
                    f"# Shot: {job.shot_id}\n"
                    f"# Renderer: {job.renderer}\n"
                    f"# Command: {job.command}\n"
                    f"# Started: {job.started_at}\n"
                    f"# Elapsed: {elapsed:.1f}s\n"
                    f"# Exit Code: {result.returncode}\n"
                    f"\n## STDOUT\n{result.stdout}\n"
                    f"\n## STDERR\n{result.stderr}\n"
                )
                log_path.write_text(log_content, encoding="utf-8")

            if result.returncode == 0:
                self.db.update_status(job.job_id, "completed", exit_code=0)
                print(f"  ✅ Completed in {elapsed:.1f}s")
            else:
                error_msg = result.stderr[:500] if result.stderr else f"Exit code {result.returncode}"
                self.db.update_status(job.job_id, "failed", error_message=error_msg,
                                      exit_code=result.returncode)
                print(f"  ❌ Failed: {error_msg[:100]}")

        except subprocess.TimeoutExpired:
            elapsed = time.time() - start_time
            error_msg = f"Timeout after {timeout}s"
            self.db.update_status(job.job_id, "failed", error_message=error_msg)
            if log_path:
                log_path.write_text(f"# TIMEOUT\n{error_msg}\n", encoding="utf-8")
            print(f"  ⏱️  {error_msg}")

        except Exception as e:
            error_msg = f"Exception: {str(e)}"
            self.db.update_status(job.job_id, "failed", error_message=error_msg)
            print(f"  💥 {error_msg}")

        return True

    def run_loop(self, project_id: str | None = None, workers: int = 1,
                 poll_interval: float = 2.0, timeout: int = DEFAULT_TIMEOUT) -> None:
        """Continuously process jobs until interrupted."""
        self.running = True
        print(f"[Worker {self.worker_id}] Starting render worker (poll={poll_interval}s, timeout={timeout}s)")

        while self.running:
            processed = self.run_once(project_id, timeout)
            if not processed:
                time.sleep(poll_interval)

    def stop(self) -> None:
        self.running = False


# ── CLI ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="DeParadigm Media Render Queue")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # enqueue
    enqueue_parser = subparsers.add_parser("enqueue", help="Enqueue a render job")
    enqueue_parser.add_argument("--project", required=True, help="Project ID/slug")
    enqueue_parser.add_argument("--shot", required=True, help="Shot ID")
    enqueue_parser.add_argument("--renderer", required=True,
                                choices=["blender", "manim", "after_effects", "motion",
                                         "resolve", "ffmpeg", "comfyui", "custom"],
                                help="Renderer type")
    enqueue_parser.add_argument("--cmd", required=True, help="Shell command to execute")
    enqueue_parser.add_argument("--cwd", default=".", help="Working directory")
    enqueue_parser.add_argument("--env", default="{}", help="JSON environment variables")
    enqueue_parser.add_argument("--output", help="Expected output file path")
    enqueue_parser.add_argument("--log", help="Log file path")
    enqueue_parser.add_argument("--priority", type=int, default=5, help="Priority (1-10, lower=higher)")

    # worker
    worker_parser = subparsers.add_parser("worker", help="Start render worker(s)")
    worker_parser.add_argument("--project", help="Filter to specific project")
    worker_parser.add_argument("--workers", type=int, default=1, help="Number of parallel workers")
    worker_parser.add_argument("--poll", type=float, default=2.0, help="Poll interval in seconds")
    worker_parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Job timeout in seconds")

    # status
    status_parser = subparsers.add_parser("status", help="Show queue status")
    status_parser.add_argument("--project", help="Filter to specific project")
    status_parser.add_argument("--jobs", action="store_true", help="List individual jobs")

    # retry
    retry_parser = subparsers.add_parser("retry", help="Retry failed jobs")
    retry_parser.add_argument("--project", help="Filter to specific project")

    args = parser.parse_args()
    db = QueueDatabase()

    if args.command == "enqueue":
        log_path = args.log or str(LOGS_DIR / f"{args.project}_{args.shot}_{int(time.time())}.log")
        job = RenderJob(
            job_id=None,
            project_id=args.project,
            shot_id=args.shot,
            renderer=args.renderer,
            command=args.cmd,
            cwd=args.cwd,
            env_json=args.env,
            output_path=args.output or "",
            log_path=log_path,
            priority=args.priority,
            status="queued",
            retry_count=0,
            created_at=datetime.utcnow().isoformat(),
            started_at=None,
            completed_at=None,
            error_message=None,
            exit_code=None,
        )
        job_id = db.enqueue(job)
        print(f"Enqueued job {job_id}: {args.renderer} → {args.project}/{args.shot}")
        return 0

    elif args.command == "worker":
        if args.workers == 1:
            worker = RenderWorker(db, worker_id=0)
            try:
                worker.run_loop(args.project, args.workers, args.poll, args.timeout)
            except KeyboardInterrupt:
                print("\nWorker stopped.")
        else:
            import multiprocessing
            processes = []
            for i in range(args.workers):
                p = multiprocessing.Process(
                    target=_worker_process,
                    args=(args.project, i, args.poll, args.timeout),
                )
                p.start()
                processes.append(p)
            try:
                for p in processes:
                    p.join()
            except KeyboardInterrupt:
                print("\nStopping workers...")
                for p in processes:
                    p.terminate()
        return 0

    elif args.command == "status":
        status = db.get_status(args.project)
        print(f"Queue Status{' for ' + args.project if args.project else ''}:")
        print(f"  Total:     {status['total']}")
        print(f"  Queued:    {status['queued']}")
        print(f"  Running:   {status['running']}")
        print(f"  Completed: {status['completed']}")
        print(f"  Failed:    {status['failed']}")
        print(f"  Retrying:  {status['retrying']}")
        print(f"  Cancelled: {status['cancelled']}")

        if args.jobs:
            jobs = db.get_jobs(args.project, limit=20)
            print(f"\nRecent jobs:")
            for job in jobs:
                print(f"  #{job.job_id} [{job.status:12}] {job.renderer:16} {job.project_id}/{job.shot_id}")
        return 0

    elif args.command == "retry":
        count = db.retry_failed(args.project)
        print(f"Retried {count} failed job(s)")
        return 0

    else:
        parser.print_help()
        return 1


def _worker_process(project_id: str | None, worker_id: int, poll: float, timeout: int) -> None:
    """Entry point for multiprocessing worker."""
    db = QueueDatabase()
    worker = RenderWorker(db, worker_id=worker_id)
    worker.run_loop(project_id, poll_interval=poll, timeout=timeout)


if __name__ == "__main__":
    sys.exit(main())
