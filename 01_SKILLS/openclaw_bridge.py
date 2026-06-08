import json
import os
import time
import glob

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SESSIONS_DIR = os.path.expanduser("~/.openclaw/agents/main/sessions")
TARGET_STAGE_PATH = os.path.join(PROJECT_ROOT, "02_CURRICULUM", "raw_sources", "web_ingest", "incoming_syllabus.md")

last_known_mtime = 0


def extract_text_from_message(message_obj):
    if not message_obj:
        return ""
    content = message_obj.get("content", "")
    if isinstance(content, list):
        content = "".join([str(c) for c in content])
    if isinstance(content, str) and content.strip():
        return content
    if "tool_calls" in message_obj:
        for tool in message_obj["tool_calls"]:
            try:
                args = json.loads(tool["function"]["arguments"])
                for key in ["content", "text", "code"]:
                    if key in args and str(args[key]).strip():
                        return str(args[key])
            except:
                pass
    return ""


def main():
    print("📡 OpenClaw JSONL Tracking Bridge is active (Format Normalization Mode)...")
    global last_known_mtime
    while True:
        try:
            jsonl_files = glob.glob(os.path.join(SESSIONS_DIR, "*.jsonl"))
            if jsonl_files:
                active_log = max(jsonl_files, key=os.path.getmtime)
                current_mtime = os.path.getmtime(active_log)

                if current_mtime > last_known_mtime:
                    with open(active_log, 'r') as f:
                        lines = f.readlines()

                    if not lines:
                        continue

                    raw_line_text = lines[-1].strip()

                    if "<|im_end|>" not in raw_line_text and '"arguments"' not in raw_line_text and not raw_line_text.endswith("}"):
                        time.sleep(0.5)
                        continue

                    time.sleep(2)
                    last_known_mtime = os.path.getmtime(active_log)
                    best_content_found = ""

                    for line in lines:
                        if not line.strip():
                            continue
                        try:
                            line_data = json.loads(line.strip())
                            msg = line_data.get("message", {})
                            extracted = extract_text_from_message(msg)
                            if len(extracted) > len(best_content_found):
                                best_content_found = extracted
                        except:
                            pass

                    if best_content_found.strip() and len(best_content_found) > 100:
                        # CRITICAL NORMALIZATION: Convert literal string "\n" into true file line breaks
                        processed_text = best_content_found.replace('\\n', '\n').replace('\\"', '"')

                        # Ensure it has a strong header for your orchestrator's regex to latch onto
                        if not processed_text.startswith("#"):
                            processed_text = "## Lesson 1: Squeeze Theorem\n" + processed_text

                        print(f"✨ Stream finalized! Normalizing text formatting...")
                        os.makedirs(os.path.dirname(TARGET_STAGE_PATH), exist_ok=True)

                        with open(TARGET_STAGE_PATH, "w") as out:
                            out.write(processed_text)

                        print(f"✅ Properly formatted markdown written to: {TARGET_STAGE_PATH}")

        except Exception as e:
            print(f"⚠️ Stream check skip: {e}")

        time.sleep(1)


if __name__ == "__main__":
    main()
