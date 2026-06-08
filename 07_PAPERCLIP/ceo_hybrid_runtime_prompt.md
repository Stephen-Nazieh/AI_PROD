# CEO Agent Directive: Agent Runtime Assignment

## Context

DeParadigm Media now has **three agent runtime options**. When creating or updating agents, you MUST assign the correct runtime based on the agent's primary function.

## The Three Runtimes

### 1. `hybrid_agent_runtime.py` — THINK + EXECUTE
**Best for**: Coding, creative work, file creation, technical implementation

- **THINK phase**: Claude Code CLI generates plans, code, and structured output
- **EXECUTE phase**: Local ToolExecutor writes files, runs bash, applies edits
- Claude outputs structured markdown:
  ```markdown
  ### FILE: path/to/file.py
  ```python
  <complete file content>
  ```

  ### BASH:
  ```bash
  <command to run>
  ```
  ```
- **Cost**: $0 (local MLX inference)
- **Adapter config**:
  ```yaml
  type: process
  config:
    command: /Users/nazeera/Documents/AI_PRODUCER/env/bin/python3
    args:
      - /Users/nazeera/Documents/AI_PRODUCER/runtime/hybrid_agent_runtime.py
    timeoutSec: 3600
    env:
      ANTHROPIC_BASE_URL: http://127.0.0.1:8003
      ANTHROPIC_AUTH_TOKEN: local
      ANTHROPIC_API_KEY: ""
  ```

### 2. `local_agent_runtime.py` — Full ReAct Loop
**Best for**: Research, analysis, strategy, operations, multi-step querying

- Direct MLX LLM calls with tool-use loop
- Best for agents that search, analyze data, check status, generate reports
- Handles 9 tools: read_file, write_file, edit_file, bash, git_status, git_commit, list_dir, search_files, done
- **Cost**: $0 (local MLX inference)
- **Adapter config**:
  ```yaml
  type: process
  config:
    command: /Users/nazeera/Documents/AI_PRODUCER/env/bin/python3
    args:
      - /Users/nazeera/Documents/AI_PRODUCER/runtime/local_agent_runtime.py
    timeoutSec: 3600
    env:
      MLX_PRIMARY_URL: http://127.0.0.1:8000/v1
      MLX_STANDARD_URL: http://127.0.0.1:8001/v1
      MLX_FAST_URL: http://127.0.0.1:8002/v1
  ```

### 3. `openclaw_gateway` — External Proxy
**Best for**: Agents requiring external cloud LLM access or specialized integrations

- Keep as-is for the single `OpenClaw Proxy Agent`
- **Cost**: Varies by external provider

## Decision Rules

Assign `hybrid_agent_runtime.py` when the agent's PRIMARY work involves:
- Writing code (any language)
- Creating files (docs, configs, scripts, assets)
- Building or modifying software/systems
- Creative production (content, media, design files)
- Technical architecture or engineering tasks

Assign `local_agent_runtime.py` when the agent's PRIMARY work involves:
- Research and analysis
- Strategy and planning
- Operations and monitoring
- Data querying and reporting
- Customer/service interactions
- Administrative tasks
- Social media management
- Financial analysis
- Compliance and auditing

Assign `openclaw_gateway` when:
- The agent specifically requires external cloud LLM capabilities
- The agent is the designated OpenClaw proxy

## Current Agent Distribution

| Runtime | Count | Examples |
|---------|-------|----------|
| Hybrid | 116 | AI Engineer, Frontend Developer, Content Creator, Game Designer, CTO, CEO |
| Local | 128 | Financial Analyst, UX Researcher, Social Media Strategist, Product Manager |
| OpenClaw | 1 | OpenClaw Proxy Agent |

## Action Required

When you create a new agent:
1. Determine its PRIMARY function using the rules above
2. Set the adapter in its Paperclip configuration
3. Document the choice in the agent's AGENTS.md file

When reviewing existing agents:
- If an agent is miscategorized, update its adapter
- Coding agents stuck on `local_agent_runtime` should move to `hybrid_agent_runtime`
- Strategy agents stuck on `hybrid_agent_runtime` should move to `local_agent_runtime`
