#!/usr/bin/env python3
"""
paperclip_bridge.py — Phase 3 + Phase 8: Paperclip ↔ Solocorn Python Bridge Adapter.

A lightweight threaded HTTP server that exposes the existing Python bridge
modules as REST endpoints, with bidirectional Paperclip sync.

Modes:
    HTTP server (default):    python3 paperclip_bridge.py
    One-shot CLI execution:   python3 paperclip_bridge.py --execute <json_task>

Usage:
    cd /Users/nazeera/Documents/AI_PRODUCER
    source env/bin/activate
    python3 runtime/paperclip_bridge.py

Endpoints:
    GET  /health              — Check MLX, Postgres, Manim, FFmpeg
    POST /ingest              — Trigger orchestrator pipeline
    POST /compile-lesson      — Generate lesson blueprint via LLM
    POST /run-curriculum      — Run AP Stats batch curriculum
    POST /process-manifest    — Execute render/manifest task
    POST /generate-timeline   — Build FCPXML from asset list
    POST /voiceover           — Synthesize WAV via macOS say
    POST /process-script      — Parse markdown script → scene manifests
    POST /vault/search        — Query compiled wiki
    POST /vault/create        — Create wiki note
"""

import io
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

# 🔗 Resolve workspace root from script location
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS_DIR = WORKSPACE_ROOT / "01_SKILLS"

try:
    from dotenv import load_dotenv
    load_dotenv(WORKSPACE_ROOT / ".env")
except ImportError:
    pass  # dotenv optional; falls back to the already-exported environment

# Inject skills directory into path for imports
sys.path.insert(0, str(SKILLS_DIR))

# ── Lazy imports (fail gracefully if modules are broken) ────────────────────

def _import_or_none(module_name: str):
    try:
        return __import__(module_name)
    except Exception as e:
        print(f"⚠️  Bridge import warning: {module_name} — {e}")
        return None


# Suppress noisy stdout from modules during import
_original_stdout = sys.stdout
sys.stdout = io.StringIO()

orchestrator = _import_or_none("orchestrator")
lesson_compiler = _import_or_none("lesson_compiler")
curriculum_runner = _import_or_none("curriculum_runner")
solocorn_media_bridge = _import_or_none("solocorn_media_bridge")
script_processor = _import_or_none("script_processor")
skills = _import_or_none("skills")

_import_noise = sys.stdout.getvalue()
sys.stdout = _original_stdout
if _import_noise:
    # Only print import noise when running as HTTP server, not in CLI mode
    pass

# ── Configuration ───────────────────────────────────────────────────────────

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 3101
MLX_URL = "http://127.0.0.1:8000/v1/chat/completions"
POSTGRES_HOST = os.environ.get("PRODUCTION_DB_HOST", "127.0.0.1")
POSTGRES_PORT = int(os.environ.get("PRODUCTION_DB_PORT", "5432"))

# Paperclip API configuration for bidirectional sync
PAPERCLIP_API_BASE = os.environ.get("PAPERCLIP_API_BASE", "http://127.0.0.1:3100")
PAPERCLIP_COMPANY_ID = os.environ.get("PAPERCLIP_COMPANY_ID", "15041ee2-b1c5-43ac-b488-04934bfa1806")

# Project ID mapping for auto-routing issues
PROJECT_IDS = {
    "solocorn-edtech": "76cdf731-76e9-4678-aac1-67df6def0c3e",
    "ap-stats-movie": "23b2f710-b364-4263-b1e7-bacace21ba62",
    "translation-factory": "8da8fae2-7add-4252-9c99-4a9e5f1742b0",
    "ambient-loops": "cd533598-b85c-4bf6-a3dd-7a6084d23c18",
}

BRIDGE_AGENT_ID = "3ab5c382-241f-4283-a39d-9612e8fd4df5"


# ── Paperclip Bidirectional Reporter (Phase 8) ──────────────────────────────

class PaperclipReporter:
    """
    Reports bridge execution results back to Paperclip via its REST API.
    Creates issues for tracked work and updates them on completion/failure.
    """

    def __init__(self, api_base: str = PAPERCLIP_API_BASE, company_id: str = PAPERCLIP_COMPANY_ID):
        self.api_base = api_base.rstrip("/")
        self.company_id = company_id

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict | None:
        """Make a Paperclip API request."""
        url = f"{self.api_base}{path}"
        data = json.dumps(payload).encode("utf-8") if payload else None
        req = urllib.request.Request(url, data=data, method=method)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            print(f"⚠️  Paperclip API {method} {path} failed: {e.code} {body}")
            return None
        except Exception as e:
            print(f"⚠️  Paperclip API {method} {path} error: {e}")
            return None

    def create_issue(self, title: str, description: str, project_id: str | None = None,
                     assignee_agent_id: str | None = None) -> dict | None:
        """Create a tracked issue in Paperclip."""
        payload = {
            "title": title,
            "description": description,
            "status": "backlog",
            "priority": "medium",
        }
        if project_id:
            payload["projectId"] = project_id
        if assignee_agent_id:
            payload["assigneeAgentId"] = assignee_agent_id

        result = self._request("POST", f"/api/companies/{self.company_id}/issues", payload)
        if result and "id" in result:
            print(f"📋 Paperclip issue created: {result.get('identifier', result['id'])}", file=sys.stderr)
            return result
        return None

    def update_issue(self, issue_id: str, **fields) -> dict | None:
        """Update an existing issue (status, description, etc.)."""
        return self._request("PATCH", f"/api/issues/{issue_id}", fields)

    def resolve_project_id(self, endpoint: str, payload: dict) -> str | None:
        """Guess the most relevant project ID from the endpoint + payload."""
        explicit = payload.get("project_id") or payload.get("projectId")
        if explicit:
            return explicit

        endpoint_project_map = {
            "/ingest": "solocorn-edtech",
            "/compile-lesson": "ap-stats-movie",
            "/run-curriculum": "ap-stats-movie",
            "/process-manifest": "ap-stats-movie",
            "/generate-timeline": "ap-stats-movie",
            "/voiceover": "ap-stats-movie",
            "/process-script": "ap-stats-movie",
            "/vault/search": None,
            "/vault/create": None,
        }
        project_slug = endpoint_project_map.get(endpoint)
        if project_slug:
            return PROJECT_IDS.get(project_slug)
        return None

    def create_work_product(self, issue_id: str, title: str, product_type: str,
                            provider: str = "solocorn-bridge", url: str | None = None,
                            status: str = "active", summary: str | None = None,
                            metadata: dict | None = None, is_primary: bool = False,
                            project_id: str | None = None) -> dict | None:
        """Attach a work product (artifact, preview_url, document, etc.) to a Paperclip issue."""
        payload = {
            "type": product_type,
            "provider": provider,
            "title": title,
            "status": status,
            "isPrimary": is_primary,
        }
        if url:
            payload["url"] = url
        if summary:
            payload["summary"] = summary
        if metadata:
            payload["metadata"] = metadata
        if project_id:
            payload["projectId"] = project_id

        result = self._request("POST", f"/api/issues/{issue_id}/work-products", payload)
        if result and "id" in result:
            print(f"📎 Work product attached: {result.get('title')} ({result.get('type')})", file=sys.stderr)
        return result


def attach_work_products(issue_id: str, endpoint: str, result_body: dict,
                         project_id: str | None = None) -> list[dict]:
    """
    Extract generated file paths from a bridge result and attach them as
    Paperclip work products (type: artifact) on the given issue.
    Returns list of created work products.
    """
    products = []
    if not issue_id:
        return products

    # Map result keys to (title, type) descriptors
    file_key_map = {
        "blueprint_path": ("Lesson Blueprint", "artifact"),
        "output_path": ("Generated Output", "artifact"),
        "manifest_path": ("Render Manifest", "artifact"),
        "fcpxml_path": ("FCPXML Timeline", "artifact"),
        "voiceover_path": ("Voiceover Audio", "artifact"),
    }

    # Single-file outputs
    for key, (title, product_type) in file_key_map.items():
        if key in result_body and result_body[key]:
            path = str(result_body[key])
            file_name = os.path.basename(path)
            ext = os.path.splitext(file_name)[1].lower()

            # Determine a more specific title based on extension
            ext_title_map = {
                ".md": "Markdown Document",
                ".txt": "Text Document",
                ".json": "JSON Manifest",
                ".yaml": "YAML Config",
                ".yml": "YAML Config",
                ".fcpxml": "FCPXML Timeline",
                ".wav": "WAV Audio",
                ".mp4": "MP4 Video",
                ".png": "PNG Image",
            }
            specific_title = ext_title_map.get(ext, title)

            # Build file:// URL for local filesystem access
            absolute_path = os.path.abspath(path)
            file_url = f"file://{absolute_path}"

            meta = {
                "localPath": absolute_path,
                "relativePath": path,
                "endpoint": endpoint,
                "fileName": file_name,
                "extension": ext,
            }
            if os.path.exists(absolute_path):
                meta["byteSize"] = os.path.getsize(absolute_path)
                meta["exists"] = True
            else:
                meta["exists"] = False

            wp = _reporter.create_work_product(
                issue_id=issue_id,
                title=specific_title,
                product_type=product_type,
                url=file_url,
                status="active",
                summary=f"Generated by {endpoint} — {file_name}",
                metadata=meta,
                is_primary=(key == "blueprint_path"),
                project_id=project_id,
            )
            if wp:
                products.append(wp)

    # Multi-file outputs (e.g., manifests list)
    if "manifests" in result_body and isinstance(result_body["manifests"], list):
        for idx, mpath in enumerate(result_body["manifests"]):
            path = str(mpath)
            absolute_path = os.path.abspath(path)
            file_url = f"file://{absolute_path}"
            file_name = os.path.basename(path)
            meta = {
                "localPath": absolute_path,
                "relativePath": path,
                "endpoint": endpoint,
                "fileName": file_name,
                "index": idx,
            }
            if os.path.exists(absolute_path):
                meta["byteSize"] = os.path.getsize(absolute_path)
                meta["exists"] = True
            else:
                meta["exists"] = False

            wp = _reporter.create_work_product(
                issue_id=issue_id,
                title=f"Scene Manifest #{idx + 1}",
                product_type="artifact",
                url=file_url,
                status="active",
                summary=f"Generated by {endpoint} — {file_name}",
                metadata=meta,
                is_primary=(idx == 0),
                project_id=project_id,
            )
            if wp:
                products.append(wp)

    return products


# ── Global reporter instance ────────────────────────────────────────────────

_reporter = PaperclipReporter()


def report_task(endpoint: str, payload: dict, result: dict, elapsed_ms: float) -> None:
    """
    Report a completed bridge task back to Paperclip.
    Creates an issue and immediately resolves it if successful.
    """
    try:
        project_id = _reporter.resolve_project_id(endpoint, payload)
        title = f"Bridge: {endpoint}"
        status = result.get("status", "unknown")
        error = result.get("error", "")

        desc_lines = [
            f"**Endpoint**: `{endpoint}`",
            f"**Status**: {status}",
            f"**Elapsed**: {elapsed_ms:.1f} ms",
        ]
        if error:
            desc_lines.append(f"**Error**: {error}")
        if "output_path" in result:
            desc_lines.append(f"**Output**: `{result['output_path']}`")
        if "blueprint_path" in result:
            desc_lines.append(f"**Blueprint**: `{result['blueprint_path']}`")
        if "manifests" in result:
            desc_lines.append(f"**Manifests**: {len(result['manifests'])} files")

        description = "\n\n".join(desc_lines)

        issue = _reporter.create_issue(
            title=title,
            description=description,
            project_id=project_id,
            assignee_agent_id=BRIDGE_AGENT_ID,
        )

        if issue and status == "ok":
            _reporter.update_issue(issue["id"], status="done")
            # Attach generated files as work products
            attach_work_products(issue["id"], endpoint, result, project_id)
            print(f"✅ Issue {issue.get('identifier', issue['id'])} resolved", file=sys.stderr)
        elif issue and error:
            _reporter.update_issue(issue["id"], status="backlog")
            print(f"⚠️  Issue {issue.get('identifier', issue['id'])} left open (error)", file=sys.stderr)

    except Exception as e:
        print(f"⚠️  Paperclip reporting failed: {e}", file=sys.stderr)


# ── Cost Estimation & Reporting ─────────────────────────────────────────────

class CostEstimator:
    """
    Estimates compute costs for bridge operations.
    All values are symbolic — local inference has near-zero cloud cost,
    but tracking prevents runaway loops and enables budget enforcement.
    """

    # Symbolic rates (cents per unit)
    RATES = {
        "mlx_per_1k_tokens": 0.2,      # $0.002 per 1K tokens
        "manim_per_render": 10.0,       # 10 cents per Manim scene
        "ffmpeg_per_op": 1.0,           # 1 cent per FFmpeg operation
        "voiceover_per_minute": 5.0,    # 5 cents per minute of audio
        "vault_per_op": 0.1,            # 0.1 cents per vault operation
        "script_per_op": 1.0,           # 1 cent per script parse
        "curriculum_per_batch": 50.0,   # 50 cents per batch
    }

    # Base cost per endpoint (cents)
    BASE_COSTS = {
        "/health": 0.0,
        "/ingest": 15.0,                # MLX + Manim + FFmpeg + voice
        "/compile-lesson": 2.0,         # MLX inference
        "/run-curriculum": 50.0,        # Batch
        "/process-manifest": 10.0,      # Render
        "/generate-timeline": 5.0,      # FFmpeg mux
        "/voiceover": 2.0,              # ~24s of audio @ 5c/min
        "/process-script": 1.0,         # Parsing
        "/vault/search": 0.1,           # Local query
        "/vault/create": 0.1,           # Local write
    }

    @classmethod
    def estimate(cls, endpoint: str, response_body: dict, elapsed_ms: float) -> dict:
        """Return a cost breakdown dict with costCents, tokens, etc."""
        base = cls.BASE_COSTS.get(endpoint, 1.0)
        input_tokens = 0
        output_tokens = 0

        # Try to extract actual token counts from MLX response
        if "usage" in response_body:
            usage = response_body["usage"]
            input_tokens = usage.get("prompt_tokens", 0) + usage.get("input_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0) + usage.get("output_tokens", 0)
        elif "blueprint_path" in response_body:
            # compile-lesson: estimate from typical blueprint size
            input_tokens = 500
            output_tokens = 800
        elif "action" in response_body and "vault_stream" in response_body["action"]:
            # ingest: estimate from orchestrator's typical workload
            input_tokens = 2000
            output_tokens = 500

        # Token cost (symbolic)
        token_cost = ((input_tokens + output_tokens) / 1000) * cls.RATES["mlx_per_1k_tokens"]

        # Elapsed-time surcharge for long-running ops (prevents runaway loops)
        time_surcharge = 0.0
        if elapsed_ms > 30000:   # > 30s
            time_surcharge = 5.0
        elif elapsed_ms > 10000: # > 10s
            time_surcharge = 2.0

        total_cents = max(int(round(base + token_cost + time_surcharge)), 1)

        return {
            "costCents": total_cents,
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "baseCents": base,
            "tokenCents": round(token_cost, 4),
            "timeSurchargeCents": time_surcharge,
            "provider": "solocorn-local",
            "biller": "solocorn-local",
            "billingType": "metered_api" if input_tokens > 0 else "fixed",
            "model": "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit",
        }


def report_cost_event(endpoint: str, response_body: dict, elapsed_ms: float,
                      issue_id: str | None = None, project_id: str | None = None,
                      run_id: str | None = None) -> None:
    """Post a cost event to Paperclip's cost tracking system."""
    try:
        estimate = CostEstimator.estimate(endpoint, response_body, elapsed_ms)
        payload = {
            "agentId": BRIDGE_AGENT_ID,
            "issueId": issue_id,
            "projectId": project_id,
            "heartbeatRunId": run_id,
            "provider": estimate["provider"],
            "biller": estimate["biller"],
            "billingType": estimate["billingType"],
            "model": estimate["model"],
            "inputTokens": estimate["inputTokens"],
            "outputTokens": estimate["outputTokens"],
            "costCents": int(estimate["costCents"]),
            "occurredAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        # Remove nulls
        payload = {k: v for k, v in payload.items() if v is not None}

        result = _api_request("POST", f"/api/companies/{PAPERCLIP_COMPANY_ID}/cost-events", payload)
        if result:
            print(f"💰 Cost event reported: {estimate['costCents']} cents "
                  f"({estimate['inputTokens']} in / {estimate['outputTokens']} out tokens)", file=sys.stderr)
        else:
            print(f"⚠️  Cost event failed to report", file=sys.stderr)

    except Exception as e:
        print(f"⚠️  Cost estimation failed: {e}", file=sys.stderr)


# ── Health checks ───────────────────────────────────────────────────────────

def check_mlx() -> dict:
    """Check if local mlx-lm server responds."""
    try:
        req = urllib.request.Request(
            MLX_URL,
            data=json.dumps({
                "model": "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit",
                "messages": [
                    {"role": "system", "content": "You are a concise assistant."},
                    {"role": "user", "content": "Say 'ok'"},
                ],
                "temperature": 0.1,
                "max_tokens": 2,
            }).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return {"status": "ok", "code": resp.status}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def check_postgres() -> dict:
    """Check if Postgres on 5432 accepts connections."""
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=POSTGRES_HOST, port=POSTGRES_PORT,
            user=os.environ.get("PRODUCTION_DB_USER", "postgres"),
            password=os.environ.get("PRODUCTION_DB_PASSWORD", "postgres"),
            dbname=os.environ.get("PRODUCTION_DB_NAME", "postgres"),
            connect_timeout=5,
        )
        conn.close()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def check_binary(name: str) -> dict:
    """Check if a binary is on PATH or in the venv bin directory."""
    # Check system PATH first
    result = subprocess.run(["which", name], capture_output=True, text=True)
    if result.returncode == 0:
        return {"status": "ok", "path": result.stdout.strip()}

    # Fall back to venv bin directory (for background-started processes)
    venv_bin = WORKSPACE_ROOT / "env" / "bin"
    candidate = venv_bin / name
    if candidate.exists():
        return {"status": "ok", "path": str(candidate)}

    return {"status": "error", "detail": f"{name} not found on PATH or in {venv_bin}"}


# ── JSON response helpers ───────────────────────────────────────────────────

def json_response(status: int, payload: dict) -> bytes:
    body = json.dumps(payload, indent=2, ensure_ascii=False)
    return body.encode("utf-8")


# ── Route handlers ──────────────────────────────────────────────────────────

class BridgeHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the Solocorn Paperclip bridge."""

    def log_message(self, fmt: str, *args) -> None:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {self.address_string()} {fmt % args}")

    def _send_json(self, status: int, payload: dict) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json_response(status, payload))

    def _read_json(self) -> dict:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        body = self.rfile.read(content_length).decode("utf-8")
        return json.loads(body)

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        path = self.path
        if path == "/health":
            self._handle_health()
        elif path == "/sync-projects":
            self._handle_sync_projects()
        else:
            self._send_json(404, {"error": f"Unknown endpoint: {path}"})

    def do_POST(self) -> None:
        path = self.path
        handler_map = {
            "/ingest": self._handle_ingest,
            "/compile-lesson": self._handle_compile_lesson,
            "/run-curriculum": self._handle_run_curriculum,
            "/process-manifest": self._handle_process_manifest,
            "/generate-timeline": self._handle_generate_timeline,
            "/voiceover": self._handle_voiceover,
            "/process-script": self._handle_process_script,
            "/vault/search": self._handle_vault_search,
            "/vault/create": self._handle_vault_create,
            "/sync-projects": self._handle_sync_projects,
        }
        handler = handler_map.get(path)
        if handler:
            try:
                handler()
            except Exception as e:
                self._send_json(500, {"status": "error", "error": str(e), "endpoint": path})
        else:
            self._send_json(404, {"error": f"Unknown endpoint: {path}"})

    # ── GET /health ────────────────────────────────────────────────────────

    def _handle_health(self) -> None:
        start = time.time()
        self._send_json(200, {
            "status": "ok",
            "service": "solocorn-bridge",
            "checks": {
                "mlx_server": check_mlx(),
                "postgres_5432": check_postgres(),
                "manim": check_binary("manim"),
                "ffmpeg": check_binary("ffmpeg"),
            },
            "elapsed_ms": round((time.time() - start) * 1000, 2),
        })

    # ── GET|POST /sync-projects ──────────────────────────────────────────────

    def _handle_sync_projects(self) -> None:
        """Manually trigger a project-folder scaffold sweep (same logic as the poller)."""
        result = scaffold_projects_once(PaperclipReporter())
        code = 200 if result.get("status") == "ok" else 500
        self._send_json(code, result)

    # ── POST /ingest ───────────────────────────────────────────────────────

    def _handle_ingest(self) -> None:
        if orchestrator is None:
            self._send_json(503, {"status": "error", "error": "orchestrator module not loaded"})
            return

        payload = self._read_json()
        start = time.time()

        raw_text = payload.get("raw_source_text")
        raw_filename = payload.get("raw_filename", "staged_ingest.md")
        if raw_text:
            raw_dir = WORKSPACE_ROOT / "02_CURRICULUM" / "raw_sources"
            raw_dir.mkdir(parents=True, exist_ok=True)
            (raw_dir / raw_filename).write_text(raw_text, encoding="utf-8")

        try:
            orchestrator.process_incoming_vault_stream()
            result = {
                "status": "ok",
                "action": "vault_stream_processed",
                "elapsed_ms": round((time.time() - start) * 1000, 2),
            }
            self._send_json(200, result)
            report_task("/ingest", payload, result, result["elapsed_ms"])
        except Exception as e:
            result = {"status": "error", "error": str(e)}
            self._send_json(500, result)
            report_task("/ingest", payload, result, round((time.time() - start) * 1000, 2))

    # ── POST /compile-lesson ───────────────────────────────────────────────

    def _handle_compile_lesson(self) -> None:
        if lesson_compiler is None:
            self._send_json(503, {"status": "error", "error": "lesson_compiler module not loaded"})
            return

        payload = self._read_json()
        topic = payload.get("topic", "AP Statistics Variance Shift")
        start = time.time()

        try:
            result_path = lesson_compiler.compile_topic_to_lesson(topic)
            result = {
                "status": "ok",
                "topic": topic,
                "blueprint_path": str(result_path),
                "elapsed_ms": round((time.time() - start) * 1000, 2),
            }
            self._send_json(200, result)
            report_task("/compile-lesson", payload, result, result["elapsed_ms"])
        except Exception as e:
            result = {"status": "error", "error": str(e)}
            self._send_json(500, result)
            report_task("/compile-lesson", payload, result, round((time.time() - start) * 1000, 2))

    # ── POST /run-curriculum ───────────────────────────────────────────────

    def _handle_run_curriculum(self) -> None:
        if curriculum_runner is None:
            self._send_json(503, {"status": "error", "error": "curriculum_runner module not loaded"})
            return

        payload = self._read_json()
        start = time.time()
        try:
            curriculum_runner.execution_batch_course_pipeline()
            result = {
                "status": "ok",
                "action": "batch_curriculum_executed",
                "elapsed_ms": round((time.time() - start) * 1000, 2),
            }
            self._send_json(200, result)
            report_task("/run-curriculum", payload, result, result["elapsed_ms"])
        except Exception as e:
            result = {"status": "error", "error": str(e)}
            self._send_json(500, result)
            report_task("/run-curriculum", payload, result, round((time.time() - start) * 1000, 2))

    # ── POST /process-manifest ─────────────────────────────────────────────

    def _handle_process_manifest(self) -> None:
        if solocorn_media_bridge is None:
            self._send_json(503, {"status": "error", "error": "solocorn_media_bridge module not loaded"})
            return

        payload = self._read_json()
        manifest_path = payload.get("manifest_path")
        manifest_dict = payload.get("manifest_dict")
        start = time.time()

        try:
            if manifest_path:
                solocorn_media_bridge.process_incoming_manifest(manifest_path)
                result = {
                    "status": "ok",
                    "manifest_path": manifest_path,
                    "elapsed_ms": round((time.time() - start) * 1000, 2),
                }
            elif manifest_dict:
                solocorn_media_bridge.run_master_pipeline(manifest_dict)
                result = {
                    "status": "ok",
                    "manifest_dict": manifest_dict,
                    "elapsed_ms": round((time.time() - start) * 1000, 2),
                }
            else:
                result = {"status": "error", "error": "Provide manifest_path or manifest_dict"}
                self._send_json(400, result)
                return
            self._send_json(200, result)
            report_task("/process-manifest", payload, result, result["elapsed_ms"])
        except Exception as e:
            result = {"status": "error", "error": str(e)}
            self._send_json(500, result)
            report_task("/process-manifest", payload, result, round((time.time() - start) * 1000, 2))

    # ── POST /generate-timeline ────────────────────────────────────────────

    def _handle_generate_timeline(self) -> None:
        if solocorn_media_bridge is None:
            self._send_json(503, {"status": "error", "error": "solocorn_media_bridge module not loaded"})
            return

        payload = self._read_json()
        assets = payload.get("assets", [])
        output_path = payload.get("output_path", str(WORKSPACE_ROOT / "03_ASSETS" / "_HANDOFF_FCP_CAPCUT" / "generated_timeline.fcpxml"))
        start = time.time()

        try:
            solocorn_media_bridge.generate_fcpxml_timeline(assets, output_path)
            result = {
                "status": "ok",
                "output_path": output_path,
                "asset_count": len(assets),
                "elapsed_ms": round((time.time() - start) * 1000, 2),
            }
            self._send_json(200, result)
            report_task("/generate-timeline", payload, result, result["elapsed_ms"])
        except Exception as e:
            result = {"status": "error", "error": str(e)}
            self._send_json(500, result)
            report_task("/generate-timeline", payload, result, round((time.time() - start) * 1000, 2))

    # ── POST /voiceover ────────────────────────────────────────────────────

    def _handle_voiceover(self) -> None:
        if solocorn_media_bridge is None:
            self._send_json(503, {"status": "error", "error": "solocorn_media_bridge module not loaded"})
            return

        payload = self._read_json()
        text = payload.get("text", "")
        output_path = payload.get("output_path", str(WORKSPACE_ROOT / "media" / "audio" / "voiceover.wav"))
        start = time.time()

        if not text:
            self._send_json(400, {"status": "error", "error": "text is required"})
            return

        try:
            solocorn_media_bridge.synthesize_voiceover(text, output_path)
            result = {
                "status": "ok",
                "output_path": output_path,
                "elapsed_ms": round((time.time() - start) * 1000, 2),
            }
            self._send_json(200, result)
            report_task("/voiceover", payload, result, result["elapsed_ms"])
        except Exception as e:
            result = {"status": "error", "error": str(e)}
            self._send_json(500, result)
            report_task("/voiceover", payload, result, round((time.time() - start) * 1000, 2))

    # ── POST /process-script ───────────────────────────────────────────────

    def _handle_process_script(self) -> None:
        if script_processor is None:
            self._send_json(503, {"status": "error", "error": "script_processor module not loaded"})
            return

        payload = self._read_json()
        markdown_path = payload.get("markdown_path")
        track_name = payload.get("track_name", "ap_stats_movie")
        start = time.time()

        if not markdown_path:
            self._send_json(400, {"status": "error", "error": "markdown_path is required"})
            return

        try:
            manifest_paths = script_processor.compile_markdown_script_to_manifests(markdown_path, track_name)
            result = {
                "status": "ok",
                "manifests": manifest_paths,
                "elapsed_ms": round((time.time() - start) * 1000, 2),
            }
            self._send_json(200, result)
            report_task("/process-script", payload, result, result["elapsed_ms"])
        except Exception as e:
            result = {"status": "error", "error": str(e)}
            self._send_json(500, result)
            report_task("/process-script", payload, result, round((time.time() - start) * 1000, 2))

    # ── POST /vault/search ─────────────────────────────────────────────────

    def _handle_vault_search(self) -> None:
        if skills is None:
            self._send_json(503, {"status": "error", "error": "skills module not loaded"})
            return

        payload = self._read_json()
        query = payload.get("query", "")
        limit = payload.get("limit", 10)
        start = time.time()

        try:
            results = skills.search_vault(query, limit)
            result = {
                "status": "ok",
                "query": query,
                "results": results,
                "elapsed_ms": round((time.time() - start) * 1000, 2),
            }
            self._send_json(200, result)
            report_task("/vault/search", payload, result, result["elapsed_ms"])
        except Exception as e:
            result = {"status": "error", "error": str(e)}
            self._send_json(500, result)
            report_task("/vault/search", payload, result, round((time.time() - start) * 1000, 2))

    # ── POST /vault/create ─────────────────────────────────────────────────

    def _handle_vault_create(self) -> None:
        if skills is None:
            self._send_json(503, {"status": "error", "error": "skills module not loaded"})
            return

        payload = self._read_json()
        note_path = payload.get("path", "")
        content = payload.get("content", "")
        start = time.time()

        if not note_path:
            self._send_json(400, {"status": "error", "error": "path is required"})
            return

        try:
            skills.create_note(note_path, content)
            result = {
                "status": "ok",
                "path": note_path,
                "elapsed_ms": round((time.time() - start) * 1000, 2),
            }
            self._send_json(200, result)
            report_task("/vault/create", payload, result, result["elapsed_ms"])
        except Exception as e:
            result = {"status": "error", "error": str(e)}
            self._send_json(500, result)
            report_task("/vault/create", payload, result, round((time.time() - start) * 1000, 2))


# ── CLI execution mode (for Paperclip process adapter) ──────────────────────

def execute_cli_task(task_json: dict, issue_id: str | None = None,
                       project_id: str | None = None) -> dict:
    """
    Execute a single bridge endpoint from CLI and return the result.
    Used when Paperclip's process adapter invokes the bridge script directly.
    Optionally reports cost events to Paperclip.
    """
    endpoint = task_json.get("endpoint", "/health")
    payload = task_json.get("payload", {})
    method = task_json.get("method", "POST")

    start = time.time()

    # Build a minimal request/response simulation
    handler = BridgeHandler.__new__(BridgeHandler)
    handler.path = endpoint
    handler.headers = {"Content-Length": str(len(json.dumps(payload).encode()))}
    handler.rfile = io.BytesIO(json.dumps(payload).encode())

    response_data = [None]
    def mock_send_json(status, payload_dict):
        response_data[0] = {"status_code": status, "body": payload_dict}

    handler._send_json = mock_send_json
    handler._read_json = lambda: payload

    if method == "GET" and endpoint == "/health":
        handler._handle_health()
    elif method == "POST":
        handler_map = {
            "/ingest": handler._handle_ingest,
            "/compile-lesson": handler._handle_compile_lesson,
            "/run-curriculum": handler._handle_run_curriculum,
            "/process-manifest": handler._handle_process_manifest,
            "/generate-timeline": handler._handle_generate_timeline,
            "/voiceover": handler._handle_voiceover,
            "/process-script": handler._handle_process_script,
            "/vault/search": handler._handle_vault_search,
            "/vault/create": handler._handle_vault_create,
        }
        handler_fn = handler_map.get(endpoint)
        if handler_fn:
            handler_fn()
        else:
            mock_send_json(404, {"error": f"Unknown endpoint: {endpoint}"})
    else:
        mock_send_json(405, {"error": "Method not allowed"})

    result = response_data[0] or {"error": "No response generated"}
    elapsed_ms = round((time.time() - start) * 1000, 2)

    # Report cost to Paperclip
    report_cost_event(
        endpoint=endpoint,
        response_body=result.get("body", {}),
        elapsed_ms=elapsed_ms,
        issue_id=issue_id,
        project_id=project_id,
    )

    return result


# ── Paperclip Worker Mode (process adapter heartbeat) ───────────────────────

def _api_request(method: str, path: str, payload: dict | None = None) -> dict | None:
    """Make a Paperclip API request (reused from reporter)."""
    url = f"{PAPERCLIP_API_BASE}{path}"
    data = json.dumps(payload).encode("utf-8") if payload else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"⚠️  API {method} {path} failed: {e}", file=sys.stderr)
        return None


def parse_issue_to_task(issue: dict) -> tuple[str, dict]:
    """
    Parse a Paperclip issue title/description into a bridge endpoint + payload.
    Uses keyword heuristics for automatic routing.
    """
    title = issue.get("title", "").lower()
    desc = issue.get("description", "").lower()
    combined = f"{title} {desc}"

    # Keyword → endpoint mapping
    keyword_map = [
        (["ingest", "raw source", "vault stream"], "/ingest", {}),
        (["compile lesson", "lesson blueprint", "generate blueprint"], "/compile-lesson", {"topic": "AP Statistics"}),
        (["run curriculum", "batch curriculum", "ap stats batch"], "/run-curriculum", {}),
        (["process manifest", "render manifest", "manim render"], "/process-manifest", {}),
        (["generate timeline", "fcpxml", "fcp xml"], "/generate-timeline", {"assets": []}),
        (["voiceover", "synthesize voice", "say ", "wav"], "/voiceover", {"text": "Hello from Solocorn bridge."}),
        (["process script", "scene manifest", "markdown script"], "/process-script", {"track_name": "ap_stats_movie"}),
        (["vault search", "search wiki", "query vault"], "/vault/search", {"query": "z-score", "limit": 5}),
        (["vault create", "create note", "new wiki"], "/vault/create", {"path": "_worker_note.md", "content": "# Worker Note\n\nCreated by bridge-operator."}),
    ]

    for keywords, endpoint, default_payload in keyword_map:
        if any(kw in combined for kw in keywords):
            return endpoint, default_payload

    # Default fallback
    return "/health", {}


def worker_mode() -> int:
    """
    Paperclip process adapter worker mode.
    Pulls one pending task from Paperclip, executes it, reports back, and exits.

    When Paperclip invokes this via process adapter, it sets PAPERCLIP_ISSUE_ID
    to the specific issue it wants processed. We honor that first, falling back
    to backlog polling only when no specific issue is targeted.
    """
    agent_id = os.environ.get("PAPERCLIP_AGENT_ID")
    company_id = os.environ.get("PAPERCLIP_COMPANY_ID", PAPERCLIP_COMPANY_ID)
    api_url = os.environ.get("PAPERCLIP_API_URL", PAPERCLIP_API_BASE)
    explicit_issue_id = os.environ.get("PAPERCLIP_ISSUE_ID")
    explicit_issue_identifier = os.environ.get("PAPERCLIP_ISSUE_IDENTIFIER", "")

    print(f"🤖 Bridge worker mode active", file=sys.stderr)
    print(f"   Agent:    {agent_id}", file=sys.stderr)
    print(f"   API:      {api_url}", file=sys.stderr)
    if explicit_issue_id:
        print(f"   Issue:    {explicit_issue_identifier or explicit_issue_id} (from env)", file=sys.stderr)

    issue = None

    # 1a. If Paperclip told us exactly which issue to process, fetch it directly
    if explicit_issue_id:
        issue = _api_request("GET", f"/api/issues/{explicit_issue_id}")
        if issue is None:
            print(f"❌ Could not fetch issue {explicit_issue_id}", file=sys.stderr)
            return 1
        if issue.get("status") == "done":
            print(f"ℹ️  Issue {explicit_issue_identifier or explicit_issue_id} is already done. Nothing to do.", file=sys.stderr)
            return 0

    # 1b. Otherwise, poll the backlog for any issue assigned to this agent
    if issue is None:
        issues = _api_request(
            "GET",
            f"/api/companies/{company_id}/issues?assigneeAgentId={agent_id}"
        )
        if issues is None:
            print("❌ Failed to fetch assigned issues", file=sys.stderr)
            return 1

        pending = [i for i in issues if i.get("status") in ("backlog",)]
        if not pending:
            print("ℹ️  No pending tasks. Exiting cleanly.", file=sys.stderr)
            return 0
        issue = pending[0]

    issue_id = issue["id"]
    identifier = issue.get("identifier", issue_id)
    print(f"📋 Claimed task: {identifier} — {issue['title']}", file=sys.stderr)

    # 2. Mark issue as in-progress (if not already)
    if issue.get("status") != "in_progress":
        _api_request("PATCH", f"/api/issues/{issue_id}", {"status": "in_progress"})

    # 3. Parse and execute
    endpoint, payload = parse_issue_to_task(issue)
    print(f"🔧 Routing to endpoint: {endpoint}", file=sys.stderr)

    start = time.time()
    result = execute_cli_task(
        {"endpoint": endpoint, "method": "POST", "payload": payload},
        issue_id=issue_id,
        project_id=issue.get("projectId"),
    )
    elapsed_ms = round((time.time() - start) * 1000, 2)

    # 4. Report result back to Paperclip
    status_code = result.get("status_code", 500)
    body = result.get("body", {})
    bridge_status = body.get("status", "unknown")
    error = body.get("error", "")

    # Build a rich comment/description update
    update_payload = {
        "status": "done" if status_code < 400 and bridge_status == "ok" else "backlog",
        "description": (
            f"**Endpoint**: `{endpoint}`\n\n"
            f"**Status**: {bridge_status}\n\n"
            f"**HTTP**: {status_code}\n\n"
            f"**Elapsed**: {elapsed_ms} ms\n\n"
            f"{'**Error**: ' + error if error else ''}"
        ),
    }
    _api_request("PATCH", f"/api/issues/{issue_id}", update_payload)

    # 4b. Attach generated files as work products on the original issue
    if status_code < 400 and bridge_status == "ok":
        wps = attach_work_products(issue_id, endpoint, body, issue.get("projectId"))
        if wps:
            print(f"📎 Attached {len(wps)} work product(s) to {identifier}", file=sys.stderr)

    # 5. Output result JSON to stdout for Paperclip to capture
    print(json.dumps(result, indent=2, ensure_ascii=False))

    return 0 if status_code < 400 else 1


# ── Project auto-scaffold (mirror Paperclip projects → 05_PROJECTS/<slug>/) ──
#
# Paperclip stores projects internally by UUID in ~/.paperclip/instances/.
# It does NOT create folders in this repo on its own. This poller bridges that
# gap: it watches the Paperclip projects API and runs init_project.py to scaffold
# a 05_PROJECTS/<slug>/ folder for any project that doesn't have one yet — so a
# project created in the Paperclip UI shows up as a real folder in the workspace.

SCAFFOLD_STATE_PATH = WORKSPACE_ROOT / ".pids" / "scaffolded_projects.json"
SCAFFOLD_POLL_INTERVAL = int(os.environ.get("PROJECT_SCAFFOLD_POLL_SECONDS", "30"))


def _load_scaffold_state() -> dict:
    """Return {project_id: folder_slug} for projects already scaffolded."""
    try:
        return json.loads(SCAFFOLD_STATE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_scaffold_state(state: dict) -> None:
    SCAFFOLD_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCAFFOLD_STATE_PATH.write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def scaffold_projects_once(reporter: "PaperclipReporter") -> dict:
    """
    Fetch Paperclip projects and scaffold a 05_PROJECTS/<slug>/ folder for any
    that aren't tracked yet. Returns a summary dict. Idempotent: a project is
    recorded in the state file once handled, and existing folders are never
    overwritten (init_project.py refuses to clobber).
    """
    projects = reporter._request(
        "GET", f"/api/companies/{reporter.company_id}/projects"
    )
    if not isinstance(projects, list):
        return {"status": "error", "error": "could not list projects", "scaffolded": []}

    # init_project.create_project lives in 01_SKILLS (already on sys.path)
    try:
        from init_project import create_project
    except ImportError as e:
        return {"status": "error", "error": f"init_project import failed: {e}", "scaffolded": []}

    state = _load_scaffold_state()
    scaffolded: list[str] = []

    for proj in projects:
        pid = proj.get("id")
        slug = proj.get("urlKey") or pid
        if not pid or pid in state:
            continue

        project_dir = WORKSPACE_ROOT / "05_PROJECTS" / slug
        if project_dir.exists():
            # Already on disk (created manually or by an earlier run) — just record it.
            state[pid] = slug
            continue

        result = create_project(
            slug,
            proj.get("name") or slug,
            proj.get("description") or "",
        )
        if result.get("status") == "error":
            print(f"⚠️  scaffold failed for {slug}: {result.get('message')}", file=sys.stderr)
            continue

        state[pid] = slug
        scaffolded.append(slug)
        print(f"🗂️  Scaffolded 05_PROJECTS/{slug}/ for Paperclip project '{proj.get('name')}'")

    if scaffolded or state != _load_scaffold_state():
        _save_scaffold_state(state)

    return {"status": "ok", "checked": len(projects), "scaffolded": scaffolded}


def project_scaffold_poller(interval: int = SCAFFOLD_POLL_INTERVAL) -> None:
    """Background loop: periodically scaffold folders for new Paperclip projects."""
    reporter = PaperclipReporter()
    print(f"🛰️  Project auto-scaffold poller started (every {interval}s → 05_PROJECTS/)")
    while True:
        try:
            scaffold_projects_once(reporter)
        except Exception as e:  # never let the poller kill the thread
            print(f"⚠️  project scaffold poll error: {e}", file=sys.stderr)
        time.sleep(interval)


# ── Server bootstrap ────────────────────────────────────────────────────────

def main() -> int:
    # Check for explicit CLI execution mode
    if len(sys.argv) > 1 and sys.argv[1] == "--execute":
        task_input = sys.argv[2] if len(sys.argv) > 2 else sys.stdin.read()
        try:
            task_json = json.loads(task_input)
        except json.JSONDecodeError:
            print("❌ Invalid JSON task input", file=sys.stderr)
            return 1
        result = execute_cli_task(task_json)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("status_code", 500) < 400 else 1

    # Check for Paperclip process adapter worker mode
    if os.environ.get("PAPERCLIP_AGENT_ID") and not (len(sys.argv) > 1 and sys.argv[1] == "--server"):
        return worker_mode()

    # Default: HTTP server mode
    host = os.environ.get("BRIDGE_HOST", DEFAULT_HOST)
    port = int(os.environ.get("BRIDGE_PORT", DEFAULT_PORT))

    server = ThreadingHTTPServer((host, port), BridgeHandler)
    print(f"🌉 Solocorn Paperclip Bridge running at http://{host}:{port}")
    print(f"   Endpoints: /health, /ingest, /compile-lesson, /run-curriculum,")
    print(f"              /process-manifest, /generate-timeline, /voiceover,")
    print(f"              /process-script, /vault/search, /vault/create, /sync-projects")
    print(f"   Bidirectional sync: ENABLED (reports to Paperclip on {PAPERCLIP_API_BASE})")

    # Background poller: scaffold 05_PROJECTS/<slug>/ folders for new Paperclip projects.
    if os.environ.get("PROJECT_SCAFFOLD_DISABLED") != "1":
        threading.Thread(target=project_scaffold_poller, daemon=True).start()
    print(f"   CLI mode: --execute '<json_task>'")
    print(f"   Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Bridge server stopped.")
        server.shutdown()

    return 0


if __name__ == "__main__":
    sys.exit(main())
