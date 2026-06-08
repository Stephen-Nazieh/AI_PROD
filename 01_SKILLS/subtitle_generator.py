#!/usr/bin/env python3
"""
subtitle_generator.py — Timed Subtitle Generation (SRT / VTT)

Generates subtitle files from dialogue text with estimated timing.
Uses audio duration for precise timing, falls back to text-based estimates.

Usage:
    python subtitle_generator.py generate <project_slug> --format srt
    python subtitle_generator.py generate <project_slug> --format vtt --episode EP01
"""

import argparse
import json
import math
import re
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


def words_to_duration(words: int, wpm: float = 150.0) -> float:
    """Estimate duration from word count at given WPM."""
    return (words / wpm) * 60.0


def format_srt_time(seconds: float) -> str:
    """Format time as HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def format_vtt_time(seconds: float) -> str:
    """Format time as HH:MM:SS.mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def generate_srt(shots: list, fps: float = 24.0) -> str:
    """Generate SRT subtitle file from shot dialogue."""
    lines = []
    cue_num = 1
    current_time = 0.0
    
    for shot in shots:
        dialogue = shot.get("dialogue", "")
        if not dialogue:
            current_time += shot.get("duration_seconds", 3.0)
            continue
        
        duration = shot.get("duration_seconds", words_to_duration(len(dialogue.split())))
        start = current_time
        end = current_time + duration
        
        lines.append(str(cue_num))
        lines.append(f"{format_srt_time(start)} --> {format_srt_time(end)}")
        lines.append(dialogue)
        lines.append("")
        
        cue_num += 1
        current_time = end
    
    return "\n".join(lines)


def generate_vtt(shots: list, fps: float = 24.0) -> str:
    """Generate WebVTT subtitle file."""
    lines = ["WEBVTT", ""]
    current_time = 0.0
    
    for shot in shots:
        dialogue = shot.get("dialogue", "")
        if not dialogue:
            current_time += shot.get("duration_seconds", 3.0)
            continue
        
        duration = shot.get("duration_seconds", words_to_duration(len(dialogue.split())))
        start = current_time
        end = current_time + duration
        
        lines.append(f"{format_vtt_time(start)} --> {format_vtt_time(end)}")
        lines.append(dialogue)
        lines.append("")
        
        current_time = end
    
    return "\n".join(lines)


def generate_for_project(project_slug: str, episode_id: str = None, fmt: str = "srt") -> dict:
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    
    if episode_id:
        shot_list_path = project_dir / "episodes" / episode_id / "shot-list.json"
        output_dir = project_dir / "episodes" / episode_id / "08-subtitles"
    else:
        shot_list_path = project_dir / "01-scripts" / "shot-list.json"
        output_dir = project_dir / "08-subtitles"
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if not shot_list_path.exists():
        return {"status": "error", "message": "Shot list not found"}
    
    shot_list = json.loads(shot_list_path.read_text(encoding="utf-8"))
    shots = shot_list.get("shots", [])
    
    if fmt == "srt":
        content = generate_srt(shots)
        ext = "srt"
    else:
        content = generate_vtt(shots)
        ext = "vtt"
    
    output_name = f"{episode_id or 'full'}_subtitles.{ext}"
    output_path = output_dir / output_name
    output_path.write_text(content, encoding="utf-8")
    
    # Count cues
    cues = content.strip().count("\n\n") + 1 if content.strip() else 0
    
    return {
        "status": "ok",
        "project": project_slug,
        "episode": episode_id,
        "format": fmt,
        "cues": cues,
        "output": str(output_path),
    }


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("generate")
    p.add_argument("project_slug")
    p.add_argument("--episode")
    p.add_argument("--format", default="srt", choices=["srt", "vtt"])
    args = parser.parse_args()
    
    if args.cmd == "generate":
        print(json.dumps(generate_for_project(args.project_slug, args.episode, args.format), indent=2))

if __name__ == "__main__":
    main()
