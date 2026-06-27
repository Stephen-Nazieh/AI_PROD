"""Content Engine — local LLM client (the "brain").

All agents call the local mlx-lm servers through here. Auto-discovers the served model
per port, routes tasks to the right tier, and never touches the cloud.

Tiers (discovered 2026-06-25):
  :8000  Qwen2.5-32B   → "smart"  (creative scriptwriting, directing, reasoning)
  :8002  Qwen2.5-7B    → "fast"   (summaries, extraction, quick passes)
  :8001  Qwen-Coder-7B → "code"   (config/JSON generation)
"""
import json, urllib.request, urllib.error

TIERS = {"smart": 8000, "fast": 8002, "code": 8001}
_MODEL_CACHE = {}

def _model_for(port):
    if port in _MODEL_CACHE:
        return _MODEL_CACHE[port]
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=4) as r:
            mid = json.load(r)["data"][0]["id"]
    except Exception:
        mid = "local-model"
    _MODEL_CACHE[port] = mid
    return mid

def chat(system, user, tier="smart", temperature=0.7, max_tokens=4096, port=None):
    """Single-turn chat completion against a local mlx server. Returns text (or 'ERROR: ...')."""
    port = port or TIERS.get(tier, 8000)
    payload = {
        "model": _model_for(port),
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
        # anti-repetition (4-bit models loop without these) — mlx-lm + OpenAI-compat params
        "repetition_penalty": 1.15,
        "frequency_penalty": 0.6,
        "presence_penalty": 0.4,
    }
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.load(r)["choices"][0]["message"]["content"].strip()
    except urllib.error.URLError as e:
        return f"ERROR: local LLM (:{port}) unreachable — is mlx-lm running? Details: {e}"
    except Exception as e:
        return f"ERROR: local LLM call failed: {e}"

def health():
    """Return {tier: model|None} for the three brain tiers."""
    out = {}
    for tier, port in TIERS.items():
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=3) as r:
                out[tier] = json.load(r)["data"][0]["id"]
        except Exception:
            out[tier] = None
    return out

if __name__ == "__main__":
    import sys
    print("brain health:", json.dumps(health(), indent=2))
    if len(sys.argv) > 1:
        print(chat("You are concise.", sys.argv[1], tier="fast", max_tokens=200))
