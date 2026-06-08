#!/usr/bin/env python3
"""
health_check.py — Unified System Health Check for Solocorn Studio

Verifies all critical services, model files, and dependencies are available
before starting a production pipeline run.

Usage:
    python3 health_check.py
    python3 health_check.py --json
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
SHARED_ASSETS = WORKSPACE_ROOT / "06_SHARED_ASSETS"

try:
    from dotenv import load_dotenv
    load_dotenv(WORKSPACE_ROOT / ".env")
except ImportError:
    pass  # dotenv optional; falls back to the already-exported environment


def check_http(url: str, timeout: float = 5.0) -> dict:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"status": "ok", "code": resp.status}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}


def check_mlx_server(port: int, model_name: str = "") -> dict:
    result = check_http(f"http://127.0.0.1:{port}/v1/models", timeout=3.0)
    if result["status"] == "ok":
        return {"status": "ok", "port": port, "model": model_name}
    return {"status": "error", "port": port, "model": model_name, "message": result.get("message", "unreachable")}


def check_comfyui() -> dict:
    result = check_http("http://127.0.0.1:8188/system_stats", timeout=5.0)
    if result["status"] == "ok":
        return {"status": "ok", "url": "http://127.0.0.1:8188"}
    return {"status": "error", "url": "http://127.0.0.1:8188", "message": result.get("message", "unreachable")}


def check_binary(name: str, args = None) -> dict:
    # Normalize args to list of lists
    if args is None:
        try_args = [["--version"], ["-version"], ["-h"]]
    elif isinstance(args, str):
        try_args = [[args]]
    else:
        try_args = args
    for arg_list in try_args:
        try:
            result = subprocess.run([name, *arg_list], capture_output=True, text=True, timeout=5)
            if result.returncode == 0 or (name == "ffmpeg" and result.stdout):
                first_line = result.stdout.strip().split("\n")[0]
                return {"status": "ok", "version": first_line[:80]}
        except FileNotFoundError:
            return {"status": "error", "message": "not installed"}
        except Exception:
            pass
    return {"status": "error", "message": "not installed or version check failed"}


def check_postgres(port: int) -> dict:
    # Port-specific credentials, sourced from environment (.env at repo root)
    if port == 5433:
        user = os.environ.get("PAPERCLIP_DB_USER", "paperclip_admin")
        password = os.environ.get("PAPERCLIP_DB_PASSWORD", "")
        dbname = os.environ.get("PAPERCLIP_DB_NAME", "paperclip_governance")
    else:
        user = os.environ.get("PRODUCTION_DB_USER", "postgres")
        password = os.environ.get("PRODUCTION_DB_PASSWORD", "postgres")
        dbname = os.environ.get("PRODUCTION_DB_NAME", "postgres")

    # Try psycopg2 first (available in venv), fall back to psql CLI
    try:
        import psycopg2
        conn = psycopg2.connect(
            host="localhost", port=port, user=user, password=password, dbname=dbname,
            connect_timeout=3,
        )
        cur = conn.cursor()
        cur.execute("SELECT 1;")
        cur.fetchone()
        cur.close()
        conn.close()
        return {"status": "ok", "port": port}
    except ImportError:
        pass
    except Exception as e:
        return {"status": "error", "port": port, "message": str(e)[:100]}

    try:
        result = subprocess.run(
            ["psql", "-h", "localhost", "-p", str(port), "-U", user, "-d", dbname, "-c", "SELECT 1;"],
            capture_output=True, text=True, timeout=5,
            env={**dict(subprocess.os.environ), "PGPASSWORD": password},
        )
        if result.returncode == 0:
            return {"status": "ok", "port": port}
        return {"status": "error", "port": port, "message": result.stderr[:100]}
    except FileNotFoundError:
        return {"status": "error", "port": port, "message": "psql not installed"}
    except Exception as e:
        return {"status": "error", "port": port, "message": str(e)[:100]}


def check_model_file(path: Path, label: str) -> dict:
    if path.exists():
        size_mb = path.stat().st_size / (1024 * 1024)
        return {"status": "ok", "label": label, "path": str(path), "size_mb": round(size_mb, 1)}
    return {"status": "error", "label": label, "path": str(path), "message": "file not found"}


def check_venv() -> dict:
    venv_py = WORKSPACE_ROOT / "env" / "bin" / "python3"
    if venv_py.exists():
        try:
            result = subprocess.run([str(venv_py), "--version"], capture_output=True, text=True, timeout=5)
            return {"status": "ok", "path": str(venv_py), "version": result.stdout.strip()}
        except Exception as e:
            return {"status": "error", "message": str(e)[:100]}
    return {"status": "error", "message": "venv python3 not found"}


def run_all_checks() -> dict:
    results = {
        "mlx_servers": [
            check_mlx_server(8000, "Llama4 Scout"),
            check_mlx_server(8001, "Qwen 32B"),
            check_mlx_server(8002, "Qwen 7B"),
        ],
        "comfyui": check_comfyui(),
        "binaries": {
            "ffmpeg": check_binary("ffmpeg"),
            "blender": check_binary("blender", "--version"),
            "python3": check_binary("python3", "--version"),
        },
        "postgresql": [
            check_postgres(5432),
            check_postgres(5433),
        ],
        "venv": check_venv(),
        "models": [
            check_model_file(SHARED_ASSETS / "ai-models" / "kokoro" / "kokoro-v1.0.onnx", "Kokoro ONNX"),
            check_model_file(SHARED_ASSETS / "ai-models" / "kokoro" / "voices-v1.0.bin", "Kokoro voices"),
            check_model_file(SHARED_ASSETS / "ai-models" / "mediapipe" / "pose_landmarker_full.task", "MediaPipe Pose"),
            check_model_file(WORKSPACE_ROOT / "OpenVoice" / "checkpoints" / "base_speakers" / "EN" / "checkpoint.pth", "OpenVoice EN"),
        ],
    }

    # Calculate summary
    all_ok = True
    for s in results["mlx_servers"]:
        if s["status"] != "ok":
            all_ok = False
    if results["comfyui"]["status"] != "ok":
        all_ok = False
    for b in results["binaries"].values():
        if b["status"] != "ok":
            all_ok = False
    for p in results["postgresql"]:
        if p["status"] != "ok":
            all_ok = False
    if results["venv"]["status"] != "ok":
        all_ok = False
    for m in results["models"]:
        if m["status"] != "ok":
            all_ok = False

    results["summary"] = "all_ok" if all_ok else "issues_found"
    return results


def print_report(results: dict):
    print("=" * 60)
    print("🩺 Solocorn Studio Health Check")
    print("=" * 60)

    print("\n🧠 MLX Inference Servers")
    for s in results["mlx_servers"]:
        icon = "✅" if s["status"] == "ok" else "❌"
        print(f"  {icon} Port {s['port']} ({s.get('model', '?')})")
        if s["status"] != "ok":
            print(f"     → {s.get('message', '')}")

    print("\n🎨 ComfyUI")
    c = results["comfyui"]
    icon = "✅" if c["status"] == "ok" else "❌"
    print(f"  {icon} {c['url']}")
    if c["status"] != "ok":
        print(f"     → {c.get('message', '')}")

    print("\n🔧 Binaries")
    for name, b in results["binaries"].items():
        icon = "✅" if b["status"] == "ok" else "❌"
        ver = b.get("version", "")
        print(f"  {icon} {name:<12} {ver}")
        if b["status"] != "ok":
            print(f"     → {b.get('message', '')}")

    print("\n🐘 PostgreSQL")
    for p in results["postgresql"]:
        icon = "✅" if p["status"] == "ok" else "❌"
        print(f"  {icon} Port {p['port']}")
        if p["status"] != "ok":
            print(f"     → {p.get('message', '')}")

    print("\n🐍 Python Venv")
    v = results["venv"]
    icon = "✅" if v["status"] == "ok" else "❌"
    print(f"  {icon} {v.get('version', v.get('message', ''))}")

    print("\n📦 Model Files")
    for m in results["models"]:
        icon = "✅" if m["status"] == "ok" else "❌"
        size = m.get("size_mb", "")
        size_str = f" ({size} MB)" if size else ""
        print(f"  {icon} {m['label']}{size_str}")
        if m["status"] != "ok":
            print(f"     → {m.get('message', '')}")

    print("\n" + "=" * 60)
    if results["summary"] == "all_ok":
        print("✅ All systems operational. Ready for production.")
    else:
        print("⚠️  Some systems are down. Review errors above before running pipelines.")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Solocorn Studio Health Check")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    results = run_all_checks()

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print_report(results)

    sys.exit(0 if results["summary"] == "all_ok" else 1)


if __name__ == "__main__":
    main()
