#!/usr/bin/env python3
"""
resolve_auto_editor.py — Auto-Edit Decision List (EDL) & FCP XML Generator

Generates CMX3600 EDL and Final Cut Pro XML from shot metadata for import
into DaVinci Resolve, Premiere Pro, or Final Cut Pro.

Usage:
    python resolve_auto_editor.py edl <project_slug> --fps 24
    python resolve_auto_editor.py fcpxml <project_slug> --fps 24
    python resolve_auto_editor.py cutlist <project_slug>

Output:
    07-edit/<project>.edl
    07-edit/<project>.fcpxml
    07-edit/<project>_cutlist.json
"""

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import timedelta

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


def _load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def frames_to_timecode(frames: int, fps: float = 24.0) -> str:
    """Convert frame count to HH:MM:SS:FF timecode."""
    total_seconds = frames / fps
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    ff = int(frames % fps)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{ff:02d}"


def frames_to_edl_timecode(frames: int, fps: float = 24.0) -> str:
    """Convert frame count to HH:MM:SS:FF for EDL."""
    return frames_to_timecode(frames, fps)


class EDLGenerator:
    def __init__(self, project_slug: str, fps: float = 24.0):
        self.project_slug = project_slug
        self.fps = fps
        self.project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
        self.shot_list = _load_json(self.project_dir / "01-scripts" / "shot-list.json")
        self.edit_dir = self.project_dir / "07-edit"
        self.edit_dir.mkdir(parents=True, exist_ok=True)

    def generate_edl(self) -> dict:
        """Generate CMX3600 EDL file."""
        shots = self.shot_list.get("shots", [])
        if not shots:
            return {"status": "error", "message": "No shots found"}

        lines = [
            "TITLE: {}".format(self.project_slug),
            "FCM: NON-DROP FRAME",
            "",
        ]

        record_frame = 0
        for i, shot in enumerate(shots, 1):
            sid = shot["shot_id"]
            duration = shot.get("duration_seconds", 3.0)
            if duration <= 0:
                duration = 3.0
            shot_frames = int(duration * self.fps)

            src_in = frames_to_edl_timecode(0, self.fps)
            src_out = frames_to_edl_timecode(shot_frames, self.fps)
            rec_in = frames_to_edl_timecode(record_frame, self.fps)
            rec_out = frames_to_edl_timecode(record_frame + shot_frames, self.fps)

            lines.append(f"{i:03d}  {sid}  V     C        {src_in} {src_out} {rec_in} {rec_out}")
            lines.append(f"* {shot.get('action', '')}")
            lines.append("")
            record_frame += shot_frames

        edl_path = self.edit_dir / f"{self.project_slug}.edl"
        edl_path.write_text("\n".join(lines), encoding="utf-8")

        return {
            "status": "ok",
            "format": "cmx3600",
            "path": str(edl_path),
            "total_shots": len(shots),
            "total_frames": record_frame,
            "duration_sec": round(record_frame / self.fps, 2),
        }

    def generate_fcpxml(self) -> dict:
        """Generate Final Cut Pro XML (simplified)."""
        shots = self.shot_list.get("shots", [])
        if not shots:
            return {"status": "error", "message": "No shots found"}

        fcpxml = ET.Element("fcpxml", {"version": "1.9"})
        resources = ET.SubElement(fcpxml, "resources")
        ET.SubElement(resources, "format", {
            "id": "r1",
            "name": "FFVideoFormat1080p24",
            "frameDuration": "1/24s",
            "width": "1920",
            "height": "1080",
        })

        library = ET.SubElement(fcpxml, "library")
        event = ET.SubElement(library, "event", {"name": self.project_slug})
        project = ET.SubElement(event, "project", {"name": self.project_slug})
        sequence = ET.SubElement(project, "sequence", {"format": "r1"})
        spine = ET.SubElement(sequence, "spine")

        record_time = 0
        for shot in shots:
            sid = shot["shot_id"]
            duration = shot.get("duration_seconds", 3.0)
            if duration <= 0:
                duration = 3.0
            frames = int(duration * self.fps)

            asset = ET.SubElement(resources, "asset", {
                "id": f"a_{sid}",
                "name": sid,
                "hasVideo": "1",
                "hasAudio": "1",
                "duration": f"{frames}/{int(self.fps)}s",
            })

            clip = ET.SubElement(spine, "clip", {
                "name": sid,
                "offset": f"{record_time}/{int(self.fps)}s",
                "duration": f"{frames}/{int(self.fps)}s",
                "start": "0/24s",
            })
            ET.SubElement(clip, "video", {"ref": f"a_{sid}"})
            record_time += frames

        xml_path = self.edit_dir / f"{self.project_slug}.fcpxml"
        ET.indent(fcpxml, space="  ")
        xml_path.write_bytes(ET.tostring(fcpxml, encoding="utf-8", xml_declaration=True))

        return {
            "status": "ok",
            "format": "fcpxml",
            "path": str(xml_path),
            "total_shots": len(shots),
            "total_frames": record_time,
        }

    def generate_cutlist(self) -> dict:
        """Generate JSON cut list for reference."""
        shots = self.shot_list.get("shots", [])
        cuts = []
        record_frame = 0
        for shot in shots:
            duration = shot.get("duration_seconds", 3.0)
            if duration <= 0:
                duration = 3.0
            frames = int(duration * self.fps)
            cuts.append({
                "shot_id": shot["shot_id"],
                "scene_id": shot.get("scene_id", ""),
                "action": shot.get("action", ""),
                "dialogue": shot.get("dialogue", ""),
                "frame_in": record_frame,
                "frame_out": record_frame + frames,
                "timecode_in": frames_to_timecode(record_frame, self.fps),
                "timecode_out": frames_to_timecode(record_frame + frames, self.fps),
                "duration_sec": round(duration, 2),
            })
            record_frame += frames

        cutlist_path = self.edit_dir / f"{self.project_slug}_cutlist.json"
        cutlist_path.write_text(json.dumps(cuts, indent=2), encoding="utf-8")

        return {
            "status": "ok",
            "format": "json",
            "path": str(cutlist_path),
            "total_shots": len(shots),
            "total_frames": record_frame,
            "duration_sec": round(record_frame / self.fps, 2),
            "cuts": cuts,
        }


def main():
    parser = argparse.ArgumentParser(description="Resolve Auto Editor")
    sub = parser.add_subparsers(dest="command", required=True)

    p_edl = sub.add_parser("edl", help="Generate CMX3600 EDL")
    p_edl.add_argument("project_slug")
    p_edl.add_argument("--fps", type=float, default=24.0)

    p_xml = sub.add_parser("fcpxml", help="Generate Final Cut Pro XML")
    p_xml.add_argument("project_slug")
    p_xml.add_argument("--fps", type=float, default=24.0)

    p_cut = sub.add_parser("cutlist", help="Generate JSON cut list")
    p_cut.add_argument("project_slug")
    p_cut.add_argument("--fps", type=float, default=24.0)

    args = parser.parse_args()
    gen = EDLGenerator(args.project_slug, fps=args.fps)

    if args.command == "edl":
        result = gen.generate_edl()
        print(json.dumps(result, indent=2))
    elif args.command == "fcpxml":
        result = gen.generate_fcpxml()
        print(json.dumps(result, indent=2))
    elif args.command == "cutlist":
        result = gen.generate_cutlist()
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
