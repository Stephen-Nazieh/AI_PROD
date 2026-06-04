#!/usr/bin/env python3
import os
import json
import requests
from pathlib import Path

class UnderstandAnythingParser:
    """
    Universal ingestion engine. Transforms multi-format files into highly structured
    relational knowledge tracking manifests via local inference nodes.
    """
    def __init__(self, api_base: str = "http://127.0.0.1:8000/v1"):
        self.api_base = api_base
        self.headers = {"Authorization": "Bearer local_omlx_key_override", "Content-Type": "application/json"}

    def ingest_raw_source(self, file_path: str) -> dict:
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"Source file not located at: {file_path}")
            
        print(f"📥 [Understand-Anything] Deep parsing file: {p.name}")
        
        # Safe read context filter for structural files
        if p.suffix.lower() in ['.txt', '.md', '.json', '.py']:
            raw_content = p.read_text(encoding="utf-8")
        else:
            raw_content = f"[Metadata Asset Reference Block: {p.name}]"

        system_prompt = (
            "You are the 'understand-anything' context core. Analyze the input text "
            "and respond with a strict JSON object containing these precise keys: "
            "'title' (string), 'summary' (string summarizing core utility), "
            "'entities' (list of key terms), and 'dependencies' (list of prerequisite concepts)."
        )
        
        payload = {
            "model": "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Parse this content:\n\n{raw_content}"}
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }

        try:
            response = requests.post(f"{self.api_base}/chat/completions", headers=self.headers, json=payload, timeout=45)
            response.raise_for_status()
            return json.loads(response.json()['choices'][0]['message']['content'])
        except Exception as e:
            print(f"⚠️ [Understand-Anything] Local server connection skipped. Falling back to default: {e}")
            return {
                "title": p.stem,
                "summary": "Automatic parsing fallback triggered.",
                "entities": [p.stem],
                "dependencies": []
            }

if __name__ == "__main__":
    # Internal diagnostic verify checks
    parser = UnderstandAnythingParser()
    test_file = Path("01_SKILLS/understand_anything/diagnostic_run.txt")
    test_file.write_text("Central Limit Theorem maps sampling distributions. It depends on sample size n and variance.", encoding="utf-8")
    
    output = parser.ingest_raw_source(str(test_file))
    print(json.dumps(output, indent=2))
    test_file.unlink()