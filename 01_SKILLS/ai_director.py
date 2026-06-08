#!/usr/bin/env python3
"""
ai_director.py — AI Creative Director via MLX Qwen

Reads the full screenplay, analyzes narrative structure, and generates
creative director's notes: shot type recommendations, lighting changes,
music mood shifts, pacing adjustments, and emotional beats.

Usage:
    python ai_director.py direct <project_slug>
    python ai_director.py direct <project_slug> --apply
    python ai_director.py notes <project_slug>

Output:
    01-scripts/director_notes.json
    Modified shot-list.json (if --apply)
"""

import argparse
import json
import os
import re
import textwrap
import urllib.request
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MLX_URL = os.environ.get("MLX_URL", "http://127.0.0.1:8001")
DEFAULT_MLX_MODEL = os.environ.get("MLX_MODEL", "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit")

SYSTEM_PROMPT = textwrap.dedent("""\
    You are a film director with 30 years of experience. You analyze screenplays
    and generate creative notes that improve cinematic storytelling.
    
    Rules:
    - Respond ONLY with valid JSON.
    - No explanations outside the JSON.
    - Be specific about shot types, camera angles, lighting, and pacing.
    - Consider emotional arcs and visual storytelling.
    - End cleanly. No <|im_end|> tokens.
""")


def call_mlx(prompt: str, temperature: float = 0.3, max_tokens: int = 1200) -> str:
    req = urllib.request.Request(
        f"{DEFAULT_MLX_URL}/v1/chat/completions",
        data=json.dumps({
            "model": DEFAULT_MLX_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def extract_json(text: str) -> dict:
    """Extract JSON from markdown fences or raw text."""
    # Try fenced code block
    match = re.search(r"```json\n(.*?)```", text, re.DOTALL)
    if match:
        json_text = match.group(1)
    else:
        match = re.search(r"```\n(.*?)```", text, re.DOTALL)
        if match:
            json_text = match.group(1)
        else:
            json_text = text
    
    # Clean trailing tokens
    json_text = re.sub(r"<\|im_end\|>.*", "", json_text, flags=re.DOTALL).strip()
    
    # Try to find JSON object/array
    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        # Try to extract first JSON object
        brace_match = re.search(r"\{.*\}", json_text, re.DOTALL)
        if brace_match:
            return json.loads(brace_match.group(0))
        raise


def build_director_prompt(shot_list: dict) -> str:
    """Build a prompt from the full shot list."""
    scenes = shot_list.get("scenes", [])
    shots = shot_list.get("shots", [])
    
    scene_text = []
    for scene in scenes:
        scene_text.append(f"SCENE {scene['scene_id']}: {scene.get('heading', '')}\n{scene.get('description', '')}")
    
    shot_text = []
    for shot in shots:
        shot_text.append(
            f"{shot['shot_id']}: {shot.get('shot_type', 'medium')} shot, "
            f"movement={shot.get('camera_movement', 'static')}, "
            f"action='{shot.get('action', '')}', "
            f"dialogue='{shot.get('dialogue', '')}'"
        )
    
    return f"""Analyze this screenplay and generate director's notes.

Scenes:
{'\n'.join(scene_text)}

Shots:
{'\n'.join(shot_text)}

Generate a JSON object with these fields:
- "overall_pacing": string (too_fast / good / too_slow)
- "emotional_arc": array of objects with scene_id, mood, intensity_1_to_10
- "shot_recommendations": array of objects with shot_id, suggested_changes (array of strings), reason
- "lighting_notes": array of objects with scene_id, suggested_lighting, mood
- "music_cues": array of objects with scene_id, mood, intensity, instrument_suggestion
- "pacing_adjustments": array of objects with shot_id, suggested_duration_sec, reason

Respond ONLY with the JSON object.
"""


class AIDirector:
    def __init__(self, project_slug: str):
        self.project_slug = project_slug
        self.project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
        self.shot_list = self._load_json(self.project_dir / "01-scripts" / "shot-list.json")
        self.notes_path = self.project_dir / "01-scripts" / "director_notes.json"
    
    def _load_json(self, path: Path) -> dict:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}
    
    def direct(self, apply: bool = False) -> dict:
        prompt = build_director_prompt(self.shot_list)
        print("🎬 AI Director analyzing screenplay...")
        
        try:
            raw = call_mlx(prompt)
            notes = extract_json(raw)
        except Exception as e:
            return {"status": "error", "phase": "generation", "error": str(e)}
        
        # Save notes
        self.notes_path.parent.mkdir(parents=True, exist_ok=True)
        self.notes_path.write_text(json.dumps(notes, indent=2), encoding="utf-8")
        
        # Optionally apply to shot-list
        modified = False
        if apply:
            modified = self._apply_notes(notes)
        
        return {
            "status": "ok",
            "project": self.project_slug,
            "notes_path": str(self.notes_path),
            "applied": apply,
            "modified": modified,
            "notes": notes,
        }
    
    def _apply_notes(self, notes: dict) -> bool:
        """Apply director's notes to shot-list.json."""
        modified = False
        
        # Apply pacing adjustments
        for adj in notes.get("pacing_adjustments", []):
            shot_id = adj.get("shot_id", "")
            new_duration = adj.get("suggested_duration_sec")
            
            for shot in self.shot_list.get("shots", []):
                if shot["shot_id"] == shot_id and new_duration is not None:
                    shot["duration_seconds"] = new_duration
                    modified = True
        
        # Apply shot recommendations
        for rec in notes.get("shot_recommendations", []):
            shot_id = rec.get("shot_id", "")
            changes = rec.get("suggested_changes", [])
            
            for shot in self.shot_list.get("shots", []):
                if shot["shot_id"] == shot_id:
                    for change in changes:
                        if "close up" in change.lower() or "close-up" in change.lower():
                            shot["shot_type"] = "close_up"
                            modified = True
                        elif "wide" in change.lower():
                            shot["shot_type"] = "wide"
                            modified = True
                        elif "medium" in change.lower():
                            shot["shot_type"] = "medium"
                            modified = True
        
        if modified:
            shot_list_path = self.project_dir / "01-scripts" / "shot-list.json"
            shot_list_path.write_text(json.dumps(self.shot_list, indent=2), encoding="utf-8")
        
        return modified


def main():
    parser = argparse.ArgumentParser(description="AI Director")
    sub = parser.add_subparsers(dest="command", required=True)
    
    p_direct = sub.add_parser("direct", help="Generate director's notes")
    p_direct.add_argument("project_slug")
    p_direct.add_argument("--apply", action="store_true", help="Apply notes to shot-list.json")
    
    p_notes = sub.add_parser("notes", help="Show existing director notes")
    p_notes.add_argument("project_slug")
    
    args = parser.parse_args()
    
    director = AIDirector(args.project_slug)
    
    if args.command == "direct":
        result = director.direct(apply=args.apply)
        print(json.dumps(result, indent=2))
    elif args.command == "notes":
        notes = director._load_json(director.notes_path)
        if notes:
            print(json.dumps(notes, indent=2))
        else:
            print("No director notes found. Run: ai_director.py direct <project>")


if __name__ == "__main__":
    main()
