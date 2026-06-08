#!/usr/bin/env python3
import sys
import time
import json
import re
import requests
import subprocess
import shutil
from pathlib import Path
from gtts import gTTS

# Establish absolute machines paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT / "01_SKILLS"))
sys.path.append(str(PROJECT_ROOT / "05_GOVERNANCE"))
sys.path.append(str(PROJECT_ROOT / "06_SPATIAL"))

from understand_anything.parser_core import UnderstandAnythingParser
from graphify.knowledge_graph import GraphifyEngine
from paperclip.governance_core import PaperclipEnterpriseGovernor
from understand_anything.claude_interface import ClaudeCodeAutomationBridge
from vtuber_twin.twin_bridge import DeParadigm MediaSpatialBridge

print("🪐 [Orchestrator V9.1] Sovereign Multi-Part Curriculum Engine Online.")
print("🎙️ [Neural Transformer Voice Active] 📚 [Syllabus Splitter Engaged]")
print("Scanning for full-length multi-part course notes...\n")

SCOUTER_SINK = PROJECT_ROOT / "02_CURRICULUM/raw_sources"
SCOUTER_SINK.mkdir(parents=True, exist_ok=True)

def generate_transformer_voiceover(lesson_title: str, script_text: str) -> Path:
    """Track 3: Generates a deep-neural transformer voice track via cloud-weights."""
    print(f"🎙️ [Neural Audio] Generating expressive voice performance for: '{lesson_title}'...")
    audio_dir = PROJECT_ROOT / "media" / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    output_path = audio_dir / f"{lesson_title}.mp3"
    
    # Generate high-fidelity academic voice narration
    tts = gTTS(text=script_text, lang='en', tld='co.uk', slow=False) # Premium British academic cadence
    tts.save(str(output_path))
    
    print(f"✨ [Neural Audio] Expressive transformer track written to disk: {output_path.name}")
    return output_path

def split_syllabus_into_chapters(file_path: Path) -> list:
    """Track 1: Automatically parses a structured syllabus note into a multi-part playlist queue."""
    content = file_path.read_text(encoding="utf-8")
    # Finds markdown headers matching '## Chapter X:' or '## Lesson X:'
    chapters = re.split(r'(?m)^##\s+', content)
    
    queue = []
    chapter_index = 1
    
    for block in chapters:
        if not block.strip():
            continue
        lines = block.strip().split('\n')
        title_line = lines[0]
        body_content = "\n".join(lines[1:]).strip()
        
        if body_content:
            # Clean title formatting for safe filenames
            clean_title = re.sub(r'[^a-zA-Z0-9]', '', title_line.replace(' ', '_'))
            if not clean_title:
                clean_title = f"CourseModule_{chapter_index}"
                
            queue.append({
                "index": chapter_index,
                "title": f"Part{chapter_index}_{clean_title}",
                "summary": body_content
            })
            chapter_index += 1
            
    return queue

def process_incoming_vault_stream():
    incoming_files = sorted(list(SCOUTER_SINK.rglob("*.md")) + list(SCOUTER_SINK.rglob("*.txt")))
    
    if not incoming_files:
        return
        
    parser = UnderstandAnythingParser()
    graph_engine = GraphifyEngine()
    governor = PaperclipEnterpriseGovernor()
    claude_bridge = ClaudeCodeAutomationBridge()
    spatial_bridge = DeParadigm MediaSpatialBridge()
    manim_path = shutil.which("manim")
    ffmpeg_path = shutil.which("ffmpeg")
    
    for target_path in incoming_files:
        if ".docker" in target_path.parts or "compiled_wiki" in target_path.parts:
            continue
            
        print(f"\n⚡ [Orchestrator] Intercepted Syllabus Stream Note: {target_path.name}")
        time.sleep(0.5)

        # Track 1: Split the master file into separate sequentially-ordered sub-lessons automatically!
        lesson_queue = split_syllabus_into_chapters(target_path)
        print(f"📚 [Syllabus Splitter] Successfully carved file into a {len(lesson_queue)}-Part Course Playlist Queue!")

        for lesson in lesson_queue:
            lesson_title = lesson["title"]
            lesson_summary = lesson["summary"]
            print(f"\n🎬 [Playlist Queue] Executing production run for module {lesson['index']}: '{lesson_title}'")

            # Phase 1: Ledger Accounting Audit
            governor.record_operational_expense("DeParadigm Media LLC", "multi_part_pipeline_tick", 1, 0.25)
            
            # Phase 2: Knowledge Graph Indexing
            graph_engine.map_extracted_manifest({"title": lesson_title, "summary": lesson_summary, "elements": []})
            
            # Track 3: High-Fidelity Transformer Audio Synthesis Pass
            voice_mp3 = generate_transformer_voiceover(lesson_title, lesson_summary)
            
            # Phase 4: Autonomous Code Animation Generation
            target_scene_class = claude_bridge.execute_agentic_script_generation(lesson_title, lesson_summary)
            
            # Phase 5: Vector Media Production Pass
            render_status = "SKIPPED"
            if target_scene_class and manim_path:
                print(f"🎬 [Render Core] Compiling vector grids for: `{target_scene_class}`")
                
                # 🛡️ CACHE PROTECTION: Invalidate stale compiled bytecode states to prevent IndentationErrors
                pycache_dir = PROJECT_ROOT / "01_SKILLS/__pycache__"
                if pycache_dir.exists():
                    shutil.rmtree(pycache_dir)
                
                # Allow the macOS storage engine 0.5 seconds to commit script updates fully to disk storage
                time.sleep(0.5)
                
                render_args = [manim_path, "-ql", "01_SKILLS/render_scenes.py", target_scene_class]
                
                try:
                    subprocess.run(render_args, check=True)
                    render_status = "SUCCESS"
                    
                    silent_output_video = PROJECT_ROOT / f"media/videos/render_scenes/480p15/{target_scene_class}.mp4"
                    
                    # FFmpeg Muxer: Seamless audio/video asset blending
                    if silent_output_video.exists() and voice_mp3.exists() and ffmpeg_path:
                        final_output_path = PROJECT_ROOT / f"media/videos/render_scenes/480p15/{target_scene_class}_PRODUCTION.mp4"
                        
                        if final_output_path.exists():
                            final_output_path.unlink()
                            
                        mux_command = [
                            ffmpeg_path, "-y",
                            "-i", str(silent_output_video),
                            "-i", str(voice_mp3),
                            "-c:v", "copy",
                            "-c:a", "aac",
                            "-shortest",
                            str(final_output_path)
                        ]
                        subprocess.run(mux_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                        print(f"🎉 [FFmpeg Muxer] Master Production Asset finalized: {final_output_path.name}")
                        subprocess.run(["open", str(final_output_path)])
                    
                except subprocess.CalledProcessError as e:
                    print(f"❌ [Render Core] Target skipped due to compilation boundaries: {e}")
                    render_status = "FAILED"
                    
            # Phase 6: Interactive 3D Spatial Performance Pass
            if render_status == "SUCCESS":
                print(f"📡 [3D Digital Twin] Streaming Inverse Kinematics tracing signals...")
                for tick in range(20):
                    angle = (tick / 20.0) * 3.14159
                    gesture_x = 0.3 + (math.cos(angle) * 0.25)
                    gesture_y = 1.1 + (math.sin(angle) * 0.35)
                    mouth_state = 0.8 if (tick % 2 == 0) else 0.15
                    
                    spatial_bridge.synchronize_twin_state(
                        actor_id="3D_Stephen_Twin",
                        x=gesture_x, y=gesture_y, z=0.0,
                        expressions={"mouthOpen": mouth_state, "blink": 0.0}
                    )
                    time.sleep(0.09)
                spatial_bridge.synchronize_twin_state("3D_Stephen_Twin", 0.0, 1.5, 0.0, {"mouthOpen": 0.0, "blink": 0.0})

        # Archive complete syllabus when all sub-parts finish processing
        archive_path = PROJECT_ROOT / "02_CURRICULUM/compiled_wiki" / target_path.name
        target_path.rename(archive_path)
        print(f"\n📦 [Course Complete] Master syllabus completely compiled and vaulted: {archive_path.name}")

if __name__ == "__main__":
    import math
    while True:
        try:
            process_incoming_vault_stream()
            time.sleep(2)
        except KeyboardInterrupt:
            print("\n👋 Control plane shutting down safely. Runways preserved.")
            break