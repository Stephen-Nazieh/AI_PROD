#!/usr/bin/env python3
"""Content-addressed render cache — skip re-rendering unchanged shots.

The 2D/3D pipeline re-runs whole stages on every invocation; an unchanged shot
(same prompt/seed/voice/reference image) gets re-rendered from scratch even though
the bytes would be identical. On a 4-core, thermally-limited host that's the main
wall-clock cost. This keys each rendered artifact by a hash of its *inputs* (with
input FILES hashed by content, not path), so identical inputs across runs restore
instantly instead of re-rendering.

Adoption is a one-line wrap around an existing "inputs → output file" producer:

    from render_cache import RenderCache
    cache = RenderCache()
    res = cache.materialize(
        stage="dub",
        inputs={"text": dialogue, "voice": voice, "speed": speed},
        dest=wav_path,
        produce=lambda out: generate_kokoro_audio(text, out, voice, speed),
    )
    # res["hit"] is True when restored from cache (producer NOT called).

Store location: env RENDER_CACHE_DIR, else <repo>/.cache/render (gitignored).
Restores use hardlinks when possible (instant, no extra disk), falling back to copy
across filesystems (e.g. local cache → RAID dest).
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import time
from typing import Any, Callable

WORKSPACE_ROOT = pathlib.Path(__file__).resolve().parent.parent
_DEFAULT_ROOT = pathlib.Path(
    os.environ.get("RENDER_CACHE_DIR", str(WORKSPACE_ROOT / ".cache" / "render"))
)


def _hash_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonicalize(value: Any) -> Any:
    """Normalize one input value for hashing.

    A pathlib.Path, or a str naming an existing file, contributes its CONTENT hash
    (so editing a reference image busts the key); everything else contributes its
    literal value. Dicts/lists recurse so nested params stay order-stable.
    """
    if isinstance(value, pathlib.Path):
        p = value
    elif isinstance(value, str) and os.path.sep in value and os.path.isfile(value):
        p = pathlib.Path(value)
    else:
        if isinstance(value, dict):
            return {k: _canonicalize(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [_canonicalize(v) for v in value]
        return value
    return {"__file_sha256__": _hash_file(p)}


def cache_key(stage: str, inputs: dict) -> str:
    """Stable content-address for (stage, inputs). Input files hashed by content."""
    canon = {"stage": stage, "inputs": _canonicalize(inputs)}
    blob = json.dumps(canon, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class RenderCache:
    def __init__(self, root: str | pathlib.Path | None = None):
        self.root = pathlib.Path(root) if root else _DEFAULT_ROOT
        self.root.mkdir(parents=True, exist_ok=True)
        self._stats_path = self.root / "stats.json"

    # ── store layout: shard by first 2 hex chars to keep dirs small ──────────
    def _blob_path(self, key: str, suffix: str) -> pathlib.Path:
        return self.root / key[:2] / f"{key}{suffix}"

    def _link_or_copy(self, src: pathlib.Path, dst: pathlib.Path) -> None:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            dst.unlink()
        try:
            os.link(src, dst)  # hardlink: instant, shares bytes
        except OSError:
            shutil.copy2(src, dst)  # cross-filesystem fallback

    def get(self, stage: str, inputs: dict, suffix: str) -> pathlib.Path | None:
        blob = self._blob_path(cache_key(stage, inputs), suffix)
        return blob if blob.exists() else None

    def materialize(self, stage: str, inputs: dict, dest: str | pathlib.Path,
                    produce: Callable[[pathlib.Path], Any]) -> dict:
        """Restore (stage, inputs)→dest from cache, else produce(dest) and store it.

        `produce` is only called on a miss and must write the artifact to the path
        it's given. Returns {hit, key, path, bytes}.
        """
        dest = pathlib.Path(dest)
        key = cache_key(stage, inputs)
        blob = self._blob_path(key, dest.suffix)

        if blob.exists():
            self._link_or_copy(blob, dest)
            self._bump("hit")
            return {"hit": True, "key": key, "path": str(dest),
                    "bytes": blob.stat().st_size}

        dest.parent.mkdir(parents=True, exist_ok=True)
        produce(dest)
        if dest.exists():
            self._link_or_copy(dest, blob)
            self._bump("miss")
            return {"hit": False, "key": key, "path": str(dest),
                    "bytes": dest.stat().st_size}
        # producer wrote nothing — don't poison the cache
        self._bump("miss")
        return {"hit": False, "key": key, "path": str(dest), "bytes": 0}

    # ── observability ────────────────────────────────────────────────────────
    def _bump(self, kind: str) -> None:
        s = self.stats()
        s[kind] = s.get(kind, 0) + 1
        s["updated"] = int(time.time())
        try:
            self._stats_path.write_text(json.dumps(s, indent=2), encoding="utf-8")
        except Exception:
            pass

    def stats(self) -> dict:
        try:
            return json.loads(self._stats_path.read_text(encoding="utf-8"))
        except Exception:
            return {"hit": 0, "miss": 0}

    def disk(self) -> tuple[int, int]:
        """(blob_count, total_bytes) of cached artifacts."""
        n = b = 0
        for f in self.root.rglob("*"):
            if f.is_file() and f.name != "stats.json":
                n += 1
                b += f.stat().st_size
        return n, b

    def clear(self) -> int:
        n, _ = self.disk()
        for sub in self.root.iterdir():
            if sub.is_dir():
                shutil.rmtree(sub, ignore_errors=True)
        if self._stats_path.exists():
            self._stats_path.unlink()
        return n


def _print() -> None:
    c = RenderCache()
    s = c.stats()
    hits, miss = s.get("hit", 0), s.get("miss", 0)
    total = hits + miss
    rate = (hits / total * 100) if total else 0.0
    n, b = c.disk()
    mb = b / (1024 * 1024)
    print("\033[1mRender cache\033[0m")
    print(f"  store      {c.root}")
    print(f"  artifacts  {n} blob(s), {mb:.1f} MB")
    print(f"  hit rate   {rate:.0f}%  ({hits} hit / {miss} miss)")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(prog="render_cache")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("stats", help="show cache size + hit rate")
    sub.add_parser("clear", help="delete all cached artifacts")
    a = ap.parse_args()
    if a.cmd == "clear":
        print(f"cleared {RenderCache().clear()} blob(s)")
    else:
        _print()
