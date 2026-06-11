#!/usr/bin/env python3
"""
episode_manager.py — Episodic Production Support (15-min episodes)

Splits a full screenplay into episodes, tracks per-episode progress,
manages episode-level rendering, assembly, and delivery.

Usage:
    python episode_manager.py split <project_slug> --duration 15
    python episode_manager.py status <project_slug> --episode EP01
    python episode_manager.py render <project_slug> --episode EP01
    python episode_manager.py assemble <project_slug> --episode EP01

Episode structure:
    05_PROJECTS/<slug>/
    ├── episodes/
    │   ├── EP01/
    │   │   ├── 01-scripts/
    │   │   ├── 03-layout/
    │   │   ├── 04-raw_renders/
    │   │   └── episode_manifest.json
    │   ├── EP02/
    │   └── ...
"""

import argparse
import json
import shutil
import subprocess
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EPISODE_DURATION = 15.0  # minutes
DEFAULT_FPS = 24.0


def split_into_episodes(project_slug: str, target_duration_min: float = 15.0) -> dict:
    """Split shot list into episodes of approximately target duration."""
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    shot_list_path = project_dir / "01-scripts" / "shot-list.json"
    
    if not shot_list_path.exists():
        return {"status": "error", "message": "Shot list not found"}
    
    shot_list = json.loads(shot_list_path.read_text(encoding="utf-8"))
    shots = shot_list.get("shots", [])
    scenes = shot_list.get("scenes", [])
    
    if not shots:
        return {"status": "error", "message": "No shots found"}
    
    target_frames = int(target_duration_min * 60 * DEFAULT_FPS)
    
    episodes = []
    current_episode = {"shots": [], "scenes": set(), "duration_frames": 0}
    episode_num = 1
    
    for shot in shots:
        shot_duration = int(shot.get("duration_seconds", 3.0) * DEFAULT_FPS)
        scene_id = shot.get("scene_id", "")
        
        # If adding this shot would exceed target, start new episode
        if current_episode["duration_frames"] + shot_duration > target_frames and current_episode["shots"]:
            episodes.append(current_episode)
            current_episode = {"shots": [], "scenes": set(), "duration_frames": 0}
            episode_num += 1
        
        current_episode["shots"].append(shot)
        current_episode["scenes"].add(scene_id)
        current_episode["duration_frames"] += shot_duration
    
    # Don't forget the last episode
    if current_episode["shots"]:
        episodes.append(current_episode)
    
    # Create episode directories and manifests
    episodes_dir = project_dir / "episodes"
    episodes_dir.mkdir(parents=True, exist_ok=True)
    
    created = []
    for i, ep in enumerate(episodes, 1):
        ep_id = f"EP{i:02d}"
        ep_dir = episodes_dir / ep_id
        ep_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy relevant scenes
        ep_scenes = [s for s in scenes if s["scene_id"] in ep["scenes"]]
        
        manifest = {
            "episode_id": ep_id,
            "project": project_slug,
            "episode_number": i,
            "total_episodes": len(episodes),
            "shot_count": len(ep["shots"]),
            "scene_count": len(ep_scenes),
            "duration_frames": ep["duration_frames"],
            "duration_seconds": round(ep["duration_frames"] / DEFAULT_FPS, 2),
            "duration_minutes": round(ep["duration_frames"] / DEFAULT_FPS / 60, 2),
            "shots": [s["shot_id"] for s in ep["shots"]],
            "scenes": ep_scenes,
        }
        
        manifest_path = ep_dir / "episode_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        
        # Copy shot-list subset
        ep_shot_list = {
            "project": project_slug,
            "episode_id": ep_id,
            "scenes": ep_scenes,
            "shots": ep["shots"],
        }
        (ep_dir / "shot-list.json").write_text(json.dumps(ep_shot_list, indent=2), encoding="utf-8")
        
        # Create subdirectories
        for subdir in ["03-layout", "04-raw_renders", "06-audio", "07-editing", "08-subtitles"]:
            (ep_dir / subdir).mkdir(parents=True, exist_ok=True)
        
        created.append(ep_id)
    
    # Write master episode manifest
    master_manifest = {
        "project": project_slug,
        "target_duration_min": target_duration_min,
        "total_episodes": len(episodes),
        "episodes": created,
        "total_shots": len(shots),
        "total_duration_frames": sum(e["duration_frames"] for e in episodes),
        "total_duration_minutes": round(sum(e["duration_frames"] for e in episodes) / DEFAULT_FPS / 60, 2),
    }
    (episodes_dir / "master_manifest.json").write_text(json.dumps(master_manifest, indent=2), encoding="utf-8")
    
    return {
        "status": "ok",
        "project": project_slug,
        "total_episodes": len(episodes),
        "episodes": created,
        "target_duration_min": target_duration_min,
    }


def get_episode_status(project_slug: str, episode_id: str) -> dict:
    """Check episode production status."""
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    ep_dir = project_dir / "episodes" / episode_id
    manifest_path = ep_dir / "episode_manifest.json"
    
    if not manifest_path.exists():
        return {"status": "error", "message": f"Episode {episode_id} not found"}
    
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    shots = manifest.get("shots", [])
    
    # Check render status
    renders_dir = ep_dir / "04-raw_renders"
    rendered_shots = []
    for shot_id in shots:
        shot_dir = renders_dir / shot_id
        if shot_dir.exists() and any(shot_dir.glob("*.png")):
            rendered_shots.append(shot_id)
    
    # Check audio status
    audio_dir = ep_dir / "06-audio"
    has_audio = any(audio_dir.rglob("*.wav"))
    
    # Check edit status
    edit_dir = ep_dir / "07-editing"
    has_edl = any(edit_dir.glob("*.edl"))
    
    return {
        "status": "ok",
        "episode_id": episode_id,
        "total_shots": len(shots),
        "rendered_shots": len(rendered_shots),
        "render_progress": f"{len(rendered_shots)}/{len(shots)}",
        "has_audio": has_audio,
        "has_edl": has_edl,
        "complete": len(rendered_shots) == len(shots) and has_audio and has_edl,
    }


def render_episode(project_slug: str, episode_id: str, engine: str = "eevee") -> dict:
    """Render all shots for an episode."""
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    ep_dir = project_dir / "episodes" / episode_id
    manifest_path = ep_dir / "episode_manifest.json"
    
    if not manifest_path.exists():
        return {"status": "error", "message": f"Episode {episode_id} not found"}
    
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    shots = manifest.get("shots", [])
    
    # Use the episode's layout file
    layout_path = ep_dir / "03-layout" / "layout.blend"
    if not layout_path.exists():
        # Copy master layout if episode layout doesn't exist
        master_layout = project_dir / "03-layout" / "layout.blend"
        if master_layout.exists():
            layout_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(str(master_layout), str(layout_path))
    
    results = []
    for shot_id in shots:
        # This would call blender_render_dispatcher per shot
        # For now, return status
        results.append({"shot_id": shot_id, "status": "queued"})
    
    return {
        "status": "ok",
        "episode_id": episode_id,
        "shots_queued": len(results),
        "results": results,
    }


def assemble_episode(project_slug: str, episode_id: str, fps: float = 24.0) -> dict:
    """Assemble rendered shots into an episode video."""
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    ep_dir = project_dir / "episodes" / episode_id
    renders_dir = ep_dir / "04-raw_renders"
    project_renders_dir = project_dir / "04-raw_renders"
    output_dir = ep_dir / "09-deliver"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    manifest_path = ep_dir / "episode_manifest.json"
    if not manifest_path.exists():
        # Auto-create a single-episode manifest from shot list
        shot_list_path = project_dir / "01-scripts" / "shot-list.json"
        if shot_list_path.exists():
            shot_list = json.loads(shot_list_path.read_text(encoding="utf-8"))
            shots_data = shot_list.get("shots", [])
            manifest = {
                "episode_id": episode_id,
                "shots": [s["shot_id"] for s in shots_data],
                "duration_seconds": sum(s.get("duration_sec", 5) for s in shots_data),
            }
            ep_dir.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        else:
            return {"status": "error", "message": "No episode manifest and no shot list found"}
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    shots = manifest.get("shots", [])
    
    graded_dir = project_dir / "04-raw_renders_graded_advanced"
    audio_dir = project_dir / "06-audio"

    def _shot_frames(shot_id: str) -> list[Path]:
        """Best available frame SEQUENCE for a shot (graded > smooth > raw)."""
        # episode-specific renders first
        d = renders_dir / shot_id
        if d.exists() and (p := sorted(d.glob("*.png"))):
            return p
        # color-graded full sequence (preferred when present)
        for sub in (graded_dir / shot_id / "2d_frames_smooth",
                    graded_dir / shot_id / "2d_frames", graded_dir / shot_id):
            if sub.exists() and (p := sorted(sub.glob("frame_*.png"))):
                return p
        # 2D composite/interpolated frames
        for sub in ("2d_frames_smooth", "2d_frames"):
            d = project_renders_dir / shot_id / sub
            if d.exists() and (p := sorted(d.glob("*.png"))):
                return p
        # 3D flat renders
        d = project_renders_dir / shot_id
        if d.exists() and (p := sorted(d.glob("frame_[0-9]*.png"))):
            return p
        return []

    def _shot_audio(shot_id: str) -> Path | None:
        w = audio_dir / "dialogue" / f"{shot_id}.wav"
        return w if w.exists() else None

    import tempfile
    output_path = output_dir / f"{episode_id}_master.mp4"
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        segments = []
        for idx, shot_id in enumerate(shots):
            frames = _shot_frames(shot_id)
            if not frames:
                continue
            # stage frames as a gap-free sequence so -i frame_%06d.png is safe
            seqdir = tmp / f"seq_{idx:03d}"; seqdir.mkdir()
            for i, f in enumerate(frames):
                (seqdir / f"f_{i:06d}.png").symlink_to(f.resolve())
            wav = _shot_audio(shot_id)
            seg = tmp / f"seg_{idx:03d}.mp4"
            cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                   "-framerate", str(fps), "-i", str(seqdir / "f_%06d.png")]
            if wav:
                cmd += ["-i", str(wav)]
            else:
                cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
            # video length is the reference; pad/trim audio to it (-shortest)
            cmd += ["-vf", "format=yuv420p", "-c:v", "libx264", "-preset", "medium",
                    "-crf", "18", "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
                    "-shortest", str(seg)]
            try:
                subprocess.run(cmd, capture_output=True, check=True)
                segments.append(seg)
            except subprocess.CalledProcessError:
                continue

        if not segments:
            return {"status": "error", "message": "No renders found to assemble"}

        # concat the uniformly-encoded segments
        concat_path = output_dir / "concat_list.txt"
        concat_path.write_text("\n".join(f"file '{s}'" for s in segments), encoding="utf-8")
        joined = tmp / "joined.mp4"
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-f", "concat", "-safe", "0", "-i", str(concat_path),
                        "-c", "copy", str(joined)], capture_output=True, check=True)

        # mix a music bed under the dialogue if one exists (ducked, low gain)
        music = sorted((audio_dir / "music").glob("*_music.wav")) if (audio_dir / "music").exists() else []
        if music:
            subprocess.run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(joined), "-i", str(music[0]),
                "-filter_complex",
                "[1:a]volume=0.18[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=2[a]",
                "-map", "0:v", "-map", "[a]", "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k", "-shortest", str(output_path),
            ], capture_output=True, check=True)
        else:
            shutil.copy(str(joined), str(output_path))

    return {
        "status": "ok",
        "episode_id": episode_id,
        "output": str(output_path),
        "shots": len(shots),
        "segments": len(segments),
        "music_bed": bool(music),
    }


def main():
    parser = argparse.ArgumentParser(description="Episode Manager")
    sub = parser.add_subparsers(dest="command", required=True)

    p_split = sub.add_parser("split", help="Split project into episodes")
    p_split.add_argument("project_slug")
    p_split.add_argument("--duration", type=float, default=15.0)

    p_status = sub.add_parser("status", help="Check episode status")
    p_status.add_argument("project_slug")
    p_status.add_argument("--episode", required=True)

    p_render = sub.add_parser("render", help="Render episode shots")
    p_render.add_argument("project_slug")
    p_render.add_argument("--episode", required=True)
    p_render.add_argument("--engine", default="eevee")

    p_assemble = sub.add_parser("assemble", help="Assemble episode video")
    p_assemble.add_argument("project_slug")
    p_assemble.add_argument("--episode", required=True)
    p_assemble.add_argument("--fps", type=float, default=24.0)

    p_list = sub.add_parser("list", help="List all episodes")
    p_list.add_argument("project_slug")

    args = parser.parse_args()

    if args.command == "split":
        print(json.dumps(split_into_episodes(args.project_slug, args.duration), indent=2))
    elif args.command == "status":
        print(json.dumps(get_episode_status(args.project_slug, args.episode), indent=2))
    elif args.command == "render":
        print(json.dumps(render_episode(args.project_slug, args.episode, args.engine), indent=2))
    elif args.command == "assemble":
        print(json.dumps(assemble_episode(args.project_slug, args.episode, args.fps), indent=2))
    elif args.command == "list":
        project_dir = WORKSPACE_ROOT / "05_PROJECTS" / args.project_slug
        master_path = project_dir / "episodes" / "master_manifest.json"
        if master_path.exists():
            manifest = json.loads(master_path.read_text(encoding="utf-8"))
            print(json.dumps(manifest, indent=2))
        else:
            print(json.dumps({"status": "error", "message": "No episodes found"}))


if __name__ == "__main__":
    main()
