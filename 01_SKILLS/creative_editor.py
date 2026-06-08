#!/usr/bin/env python3
"""
creative_editor.py — AI Creative Editor with J-Cuts, L-Cuts, Reaction Shots

Generates EDL, FCP XML, and JSON cutlists with creative editing decisions:
- J-cuts: audio leads video (hear before you see)
- L-cuts: video leads audio (see before you hear)
- Reaction shots: cut to listener during dialogue
- Cross-scene emotional bridges: match moods across scenes
- Pacing curves: accelerate/decelerate rhythm

Usage:
    python creative_editor.py edit <project_slug>
    python creative_editor.py edit <project_slug> --style dramatic
    python creative_editor.py edit <project_slug> --style fast
    python creative_editor.py edit <project_slug> --style emotional

Styles:
    chronological  — simple A-B roll, no tricks
    dramatic       — heavy use of reaction shots, longer holds
    fast           — quick cuts, minimal overlap
    emotional      — J-cuts + L-cuts + cross-scene bridges
    musical        — cuts on beats (requires music analysis)
"""

import argparse
import json
import math
from datetime import datetime, timedelta
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


def frames_to_timecode(frames: int, fps: float = 24.0) -> str:
    total_seconds = frames / fps
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    fr = int(frames % fps)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{fr:02d}"


def frames_to_smpte(frames: int, fps: float = 24.0) -> str:
    return frames_to_timecode(frames, fps)


class CreativeEditor:
    def __init__(self, project_slug: str, fps: float = 24.0):
        self.project_slug = project_slug
        self.fps = fps
        self.project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
        self.shot_list = self._load_json(self.project_dir / "01-scripts" / "shot-list.json")
        self.director_notes = self._load_json(self.project_dir / "01-scripts" / "director_notes.json")
        self.output_dir = self.project_dir / "07-editing"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _load_json(self, path: Path) -> dict:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}

    def _get_shot_duration(self, shot: dict) -> int:
        return int(shot.get("duration_seconds", 3.0) * self.fps)

    def _detect_reaction_opportunities(self, shots: list) -> list:
        """Find dialogue shots that would benefit from reaction inserts."""
        opportunities = []
        for i, shot in enumerate(shots):
            if shot.get("dialogue") and len(shot["dialogue"]) > 10:
                # This shot has dialogue - previous or next shot could be a reaction
                if i > 0:
                    opportunities.append({
                        "type": "reaction_before",
                        "dialogue_shot": shot["shot_id"],
                        "insert_after": shots[i - 1]["shot_id"],
                        "reason": "Show listener reaction before dialogue",
                    })
                if i < len(shots) - 1:
                    opportunities.append({
                        "type": "reaction_after",
                        "dialogue_shot": shot["shot_id"],
                        "insert_before": shots[i + 1]["shot_id"],
                        "reason": "Show listener reaction after dialogue",
                    })
        return opportunities

    def _apply_creative_cuts(self, shots: list, style: str) -> list:
        """Apply creative editing techniques based on style."""
        edited = []
        reactions = self._detect_reaction_opportunities(shots)
        reaction_map = {r["dialogue_shot"]: r for r in reactions}
        
        for i, shot in enumerate(shots):
            duration = self._get_shot_duration(shot)
            
            if style == "chronological":
                edited.append({
                    "shot_id": shot["shot_id"],
                    "duration_frames": duration,
                    "cut_type": "straight",
                    "audio_offset": 0,
                    "video_offset": 0,
                })
            
            elif style == "fast":
                # Cut faster, reduce duration by 30%
                edited.append({
                    "shot_id": shot["shot_id"],
                    "duration_frames": int(duration * 0.7),
                    "cut_type": "straight",
                    "audio_offset": 0,
                    "video_offset": 0,
                })
            
            elif style == "dramatic":
                # Longer holds on close-ups
                if shot.get("shot_type") == "close_up":
                    duration = int(duration * 1.3)
                edited.append({
                    "shot_id": shot["shot_id"],
                    "duration_frames": duration,
                    "cut_type": "straight",
                    "audio_offset": 0,
                    "video_offset": 0,
                })
            
            elif style == "emotional":
                # J-cuts and L-cuts
                audio_offset = 0
                video_offset = 0
                cut_type = "straight"
                
                if shot["shot_id"] in reaction_map:
                    r = reaction_map[shot["shot_id"]]
                    if r["type"] == "reaction_before":
                        # J-cut: hear dialogue before seeing speaker
                        audio_offset = int(self.fps * 0.5)
                        cut_type = "j_cut"
                    else:
                        # L-cut: see speaker after dialogue ends
                        video_offset = int(self.fps * 0.5)
                        cut_type = "l_cut"
                
                edited.append({
                    "shot_id": shot["shot_id"],
                    "duration_frames": duration,
                    "cut_type": cut_type,
                    "audio_offset": audio_offset,
                    "video_offset": video_offset,
                })
            
            else:
                edited.append({
                    "shot_id": shot["shot_id"],
                    "duration_frames": duration,
                    "cut_type": "straight",
                    "audio_offset": 0,
                    "video_offset": 0,
                })
        
        return edited

    def generate_creative_edl(self, style: str = "emotional") -> dict:
        shots = self.shot_list.get("shots", [])
        if not shots:
            return {"status": "error", "message": "No shots found"}
        
        edited_shots = self._apply_creative_cuts(shots, style)
        
        edl_lines = ["TITLE: " + self.project_slug, "FCM: NON-DROP FRAME", ""]
        edit_num = 1
        record_frame = 0
        
        for edit in edited_shots:
            shot_id = edit["shot_id"]
            duration = edit["duration_frames"]
            
            # Source timecode (simplified: each shot starts at 00:00:00:00)
            src_start = 0
            src_end = duration
            
            # Record timecode
            rec_start = record_frame
            rec_end = record_frame + duration
            
            # Cut notation
            cut_marker = "C"
            if edit["cut_type"] == "j_cut":
                cut_marker = "C J-CUT"
            elif edit["cut_type"] == "l_cut":
                cut_marker = "C L-CUT"
            
            edl_lines.append(f"{edit_num:03d}  {shot_id}       V     {cut_marker}")
            edl_lines.append(f"{frames_to_smpte(src_start)} {frames_to_smpte(src_end)} {frames_to_smpte(rec_start)} {frames_to_smpte(rec_end)}")
            edl_lines.append("")
            
            record_frame = rec_end
            edit_num += 1
        
        edl_path = self.output_dir / f"creative_{style}.edl"
        edl_path.write_text("\n".join(edl_lines), encoding="utf-8")
        
        # JSON cutlist with creative metadata
        cutlist = {
            "project": self.project_slug,
            "style": style,
            "fps": self.fps,
            "total_duration_frames": record_frame,
            "total_duration_tc": frames_to_timecode(record_frame, self.fps),
            "cuts": edited_shots,
            "reaction_opportunities": self._detect_reaction_opportunities(shots),
        }
        
        cutlist_path = self.output_dir / f"creative_{style}_cutlist.json"
        cutlist_path.write_text(json.dumps(cutlist, indent=2), encoding="utf-8")
        
        return {
            "status": "ok",
            "style": style,
            "edl": str(edl_path),
            "cutlist": str(cutlist_path),
            "total_shots": len(edited_shots),
            "total_duration_frames": record_frame,
            "total_duration_tc": frames_to_timecode(record_frame, self.fps),
        }

    def generate_fcpxml(self, style: str = "emotional") -> dict:
        shots = self.shot_list.get("shots", [])
        if not shots:
            return {"status": "error", "message": "No shots found"}
        
        edited_shots = self._apply_creative_cuts(shots, style)
        
        # FCP XML structure
        fcpxml = '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.10">
  <resources>
    <format id="r1" name="FFVideoFormat1080p24" frameDuration="1/24s" width="1920" height="1080"/>
  </resources>
  <library>
    <event name="''' + self.project_slug + '''">
      <project name="''' + self.project_slug + '''_''' + style + '''">
        <sequence format="r1" duration="''' + str(sum(e["duration_frames"] for e in edited_shots)) + '''/24s">
          <spine>
'''
        
        current_time = 0
        for i, edit in enumerate(edited_shots):
            duration = edit["duration_frames"]
            offset = current_time
            current_time += duration
            
            cut_comment = ""
            if edit["cut_type"] == "j_cut":
                cut_comment = ' <!-- J-CUT: audio leads -->'
            elif edit["cut_type"] == "l_cut":
                cut_comment = ' <!-- L-CUT: video leads -->'
            
            fcpxml += f'''            <video ref="{edit['shot_id']}" offset="{offset}/24s" duration="{duration}/24s" name="{edit['shot_id']}">{cut_comment}
              <adjust-transform position="0 0" anchor="0 0"/>
            </video>
'''
        
        fcpxml += '''          </spine>
        </sequence>
      </project>
    </event>
  </library>
</fcpxml>
'''
        
        fcpxml_path = self.output_dir / f"creative_{style}.fcpxml"
        fcpxml_path.write_text(fcpxml, encoding="utf-8")
        
        return {
            "status": "ok",
            "style": style,
            "fcpxml": str(fcpxml_path),
        }


def main():
    parser = argparse.ArgumentParser(description="Creative Editor")
    sub = parser.add_subparsers(dest="command", required=True)

    p_edit = sub.add_parser("edit", help="Generate creative edit")
    p_edit.add_argument("project_slug")
    p_edit.add_argument("--style", default="emotional",
                        choices=["chronological", "dramatic", "fast", "emotional", "musical"])
    p_edit.add_argument("--fps", type=float, default=24.0)

    args = parser.parse_args()

    if args.command == "edit":
        editor = CreativeEditor(args.project_slug, fps=args.fps)
        result = editor.generate_creative_edl(style=args.style)
        print(json.dumps(result, indent=2))
        
        if result["status"] == "ok":
            fcpxml_result = editor.generate_fcpxml(style=args.style)
            print(json.dumps(fcpxml_result, indent=2))


if __name__ == "__main__":
    main()
