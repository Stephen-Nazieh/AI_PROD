import sys
import json
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "01_SKILLS"))

def compile_topic_to_lesson(topic_name: str) -> Path:
    """
    Queries the running local MLX model to expand a raw topic into a fully
    structured, multi-scene production script configuration.
    """
    url = "http://127.0.0.1:8000/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    
    prompt = f"""
    Create a 2-scene educational production script for an EdTech video about: '{topic_name}'.
    Format the output as a strict JSON object with NO markdown wrapping block code text.
    The schema must follow this structure exactly:
    {{
      "track_name": "ap_stats_movie",
      "scenes": [
        {{
          "scene_number": 1,
          "scene_class": "EmpiricalRuleScene",
          "narration": "Let's examine why Z-scores are vital for standardizing normal curves.",
          "asset_output": "03_ASSETS/scene_1_voice.wav"
        }},
        {{
          "scene_number": 2,
          "scene_class": "ShiftingStandardDeviationScene",
          "narration": "Notice how expanding our standard deviation flattens the distribution tail map.",
          "asset_output": "03_ASSETS/scene_2_voice.wav"
        }}
      ]
    }}
    """

    data = {
        "model": "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2
    }
    
    print(f"🧠 Querying local brain to compile master outline for: '{topic_name}'...")
    
    req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers=headers)
    try:
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode('utf-8'))
            raw_text = res['choices'][0]['message']['content'].strip()
            
            # 🛡️ Resilient JSON Extraction: Strip conversational noise outside the object hooks
            import re
            json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if json_match:
                cleaned_json = json_match.group(0)
            else:
                cleaned_json = raw_text

            output_file = PROJECT_ROOT / "01_SKILLS/compiled_lesson_blueprint.json"
            output_file.write_text(cleaned_json, encoding="utf-8")
            print(f"📝 Master Lesson configuration saved to 01_SKILLS/{output_file.name}")
            return output_file
    except Exception as e:
        print(f"❌ Blueprint generation hit a block: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    compile_topic_to_lesson("AP Statistics Variance Shift")