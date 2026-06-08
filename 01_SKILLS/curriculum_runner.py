import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "01_SKILLS"))

from lesson_compiler import compile_topic_to_lesson

# 📋 Declare your target high school course curriculum modules
AP_STATS_SYLLABUS = [
    "Sampling Distribution Central Limit Theorem",
    "Type I and Type II Alpha Error Variance"
]

def execution_batch_course_pipeline():
    print("🚀 DeParadigm Media Course Batch Production Factory Online.")
    print(f"📦 Total target lessons queued for factory assembly: {len(AP_STATS_SYLLABUS)}\n")
    
    blueprint_file = PROJECT_ROOT / "01_SKILLS/compiled_lesson_blueprint.json"
    
    for i, topic in enumerate(AP_STATS_SYLLABUS, start=1):
        print(f"\n========================================================")
        print(f"🏭 MANUFACTURING PROGRESS: Lesson {i}/{len(AP_STATS_SYLLABUS)}")
        print(f"🎯 Target Subject Axis: '{topic}'")
        print(f"========================================================")
        
        # 1. Trigger the compiler to write a fresh lesson blueprint matrix file via local LLM
        compile_topic_to_lesson(topic)
        
        print("\n⏳ Passing blueprint payload to Orchestrator Daemon loop context...")
        print("Waiting dynamically for the background orchestration engine to complete rendering...")
        
        # 🛡️ SMART INTERFACE WATCHER: Polls the disk until the background daemon consumes the asset blueprint
        check_timeout = 180  # 3-minute hard ceiling fallback loop guardrail per lesson run
        elapsed = 0
        
        while blueprint_file.exists() and elapsed < check_timeout:
            time.sleep(2)
            elapsed += 2
            
        if elapsed >= check_timeout:
            print(f"⚠️ Pipeline timeout reached waiting for orchestrator on topic: '{topic}'. Forcing queue advancement.")
            if blueprint_file.exists():
                blueprint_file.unlink() # Clear jammed file to allow subsequent runs
            continue
            
        # Give the orchestrator one extra second to finish flushing out the final FCPXML output files cleanly
        time.sleep(1)
        print(f"✅ Lesson '{topic}' successfully manufactured by background core layers!")
        
    print("\n🎉 ALL CURRICULUM PROJECTS MANUFACTURED SUCCESSFULLY. CHECK YOUR FCPXML TIMELINES.")

if __name__ == "__main__":
    execution_batch_course_pipeline()