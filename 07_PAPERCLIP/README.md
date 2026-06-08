# Paperclip Integration

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Paperclip Server (:3100)                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │ 245 Agents      │  │ 4 Projects      │  │ Cost Tracking   │             │
│  │ (process)       │  │                 │  │                 │             │
│  └────────┬────────┘  └─────────────────┘  └─────────────────┘             │
│           │                                                                  │
│           ▼ process adapter                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │              local_agent_runtime.py                                  │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────┐  │    │
│  │  │ ReAct Loop  │  │ Tool Engine │  │ MLX Client  │  │ Kimi      │  │    │
│  │  │             │  │ (file/bash/ │  │ (Local LLM) │  │ Fallback  │  │    │
│  │  │             │  │  git/edit)  │  │             │  │           │  │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └───────────┘  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  MLX Model Servers                                                      ││
│  │  ├── :8000 — Llama 4 Scout 109B (Executive, complex reasoning)         ││
│  │  ├── :8001 — Qwen2.5-32B (Standard, most tasks)                       ││
│  │  └── :8002 — Qwen2.5-Coder-7B (Fast, simple queries)                  ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  Bridge Server (:3101) — HTTP endpoints for external integration       ││
│  │  /health, /vault/search, /compile-lesson, /voiceover, etc.            ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

## Local LLM Model Stack

| Server | Port | Model | Params | RAM (4-bit) | Use Case |
|--------|------|-------|--------|-------------|----------|
| Primary | 8000 | Llama 4 Scout | 109B MoE | ~55GB | Executive, strategy, complex reasoning |
| Standard | 8001 | Qwen2.5-32B | 32B | ~18GB | Standard skill tasks |
| Fast | 8002 | Qwen2.5-Coder-7B | 7B | ~4GB | Quick queries, simple edits |

### Starting Model Servers

```bash
cd /Users/nazeera/Documents/AI_PRODUCER
./runtime/start_local_stack.sh
```

Or manually:
```bash
source env/bin/activate

# Fast (always available)
python3 -m mlx_lm.server --model mlx-community/Qwen2.5-Coder-7B-Instruct-4bit --port 8002

# Standard (when download complete)
python3 -m mlx_lm.server --model /Users/nazeera/.cache/huggingface/hub/Qwen2.5-32B-Instruct-4bit --port 8001

# Executive (when download complete)
python3 -m mlx_lm.server --model /Users/nazeera/.cache/huggingface/hub/Llama-4-Scout-17B-16E-Instruct-4bit --port 8000
```

## Agent Runtime

All 245 agents now use `local_agent_runtime.py` instead of Claude Code CLI.

### Features
- **ReAct loop**: Reason → Act (tool) → Observe → Repeat
- **Tool suite**: read_file, write_file, edit_file, list_dir, bash, git_status, git_commit, search_files
- **Model routing**: Simple tasks → 7B, standard tasks → 32B, complex tasks → 109B
- **Kimi 2.6 fallback**: Cloud fallback for tasks that exceed local model capabilities
- **Loop detection**: Auto-stops if agent gets stuck repeating same action
- **Cost tracking**: Reports symbolic cost events to Paperclip
- **Work products**: Attaches generated files to issues

### Environment Variables
```bash
MLX_PRIMARY_URL=http://127.0.0.1:8000/v1    # Llama 4 Scout
MLX_STANDARD_URL=http://127.0.0.1:8001/v1   # Qwen32B
MLX_FAST_URL=http://127.0.0.1:8002/v1       # Qwen7B
KIMI_API_KEY=your_key_here                   # Optional cloud fallback
```

## Files

| File | Purpose |
|------|---------|
| `runtime/agents/local_agent_runtime.py` | Main agent runtime (ReAct loop, tools, MLX) |
| `runtime/skills/migrate_to_local.py` | Batch migration tool (claude_local → process) |
| `runtime/startup/start_local_stack.sh` | One-command startup for all services |
| `runtime/agents/paperclip_bridge.py` | Active HTTP bridge server (:3101); auto-scaffolds 05_PROJECTS/ folders for new Paperclip projects |
| `solocorn-studios/.paperclip.yaml` | Source of truth for adapter configs |

## Cloud Fallback

Only Kimi 2.6 is configured as cloud fallback. To use it, set `KIMI_API_KEY` in the agent's adapter config env. Claude and other providers are not used.

## Reverting to Claude

Any agent can be switched back to Claude instantly:
```bash
curl -X PATCH "http://localhost:3100/api/agents/{agent_id}" \
  -d '{"adapterType":"claude_local","adapterConfig":{"model":"claude-sonnet-4-5-20250929","timeoutSec":1800}}'
```

## Current Status

- **Agents**: 245 on local MLX, 1 on OpenClaw
- **Budget**: $0.03/$500.00 (0.01%)
- **Local cost**: $0 (all inference on M5 Max)
- **Cloud cost**: $0 (Kimi fallback not yet triggered)
