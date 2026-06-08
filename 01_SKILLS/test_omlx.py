#!/usr/bin/env python3
import sys
from pathlib import Path

# Temporarily append parent dir to path so we can borrow the media bridge's native oMLX driver
sys.path.append(str(Path(__file__).resolve().parent))
try:
    from solocorn_media_bridge import run_local_omlx_inference
except ImportError:
    print("❌ Critical: Could not locate solocorn_media_bridge.py path maps.")
    sys.exit(1)

def run_brain_diagnostic():
    print("🧠 Initiating hardware-accelerated local oMLX handshake...")
    
    prompt = "Generate a single 1-sentence educational hook about why Z-Scores matter in AP Statistics."
    system_instruction = "You are an elite, concise curriculum scriptwriter for DeParadigm Media EdTech."
    
    # Fire direct request to your local inference server
    response = run_local_omlx_inference(prompt, system_instruction)
    
    print("\n📬 Local Server Response Trace:")
    print("-" * 60)
    print(response)
    print("-" * 60)
    
    if "ERROR" in response:
        print("\n⚠️ Status: Offline. (This is expected if your local oMLX server isn't active on port 8000 yet.)")
    else:
        print("\n✅ Status: Online. Local model is fully integrated with your unified memory pool.")

if __name__ == "__main__":
    run_brain_diagnostic()