# Content Engine — MCP Setup

The Content Engine is exposed as **MCP tools** (`content_engine/mcp_server.py`): `health`,
`list_channels`, `new_channel`, `write_script`, `produce`, `run_status`, `make`. The brain and
all production stay **local**; these tools just trigger the local pipeline.

## Recommended client: Open WebUI (fully local)
Open WebUI runs on **:3000** and uses your local **mlx** models — no cloud. It talks to MCP
tools through **mcpo** (an MCP→OpenAPI bridge).

1. **Start the bridge** (serves the tools as OpenAPI on `:8900`):
   ```bash
   content_engine/start_mcp.sh        # or: env/bin/mcpo --port 8900 -- env/bin/python3 content_engine/mcp_server.py
   ```
   Verify: open http://localhost:8900/docs — you'll see all 7 tools.
2. **Connect in Open WebUI:** open http://localhost:3000 → **Settings → Tools** (or
   *Admin Panel → Settings → Tools*) → **+ Add Tool Server** → URL `http://localhost:8900` →
   Save. The tools now appear in chat (toggle them on under the prompt's ⚙/Tools).
3. **Use it:** pick a local model (your mlx Qwen), enable the Content Engine tools, and ask e.g.
   *"List my channels," "Write a 1-min horror short for midnight-tales about …," "Produce run X."*
   - ⚠️ **Tool-calling caveat:** local 4-bit models don't always auto-decide to call tools.
     If a request doesn't trigger a tool, call it explicitly from the Tools panel, or use the
     deterministic CLI (`engine.py`) which never needs tool-calling.

## This Claude Code CLI (already wired)
Registered via `claude mcp add content-engine …` → **✔ Connected**. The tools are callable from
this CLI now (orchestration uses Claude; all script/voice/render still runs locally).
Manage with `claude mcp list` / `claude mcp remove content-engine`.

## Claude Desktop (optional, strong tool-calling)
The same stdio server works in Claude Desktop. Add to
`~/Library/Application Support/Claude/claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "content-engine": {
      "command": "/Users/nazeera/Documents/AI_PRODUCER/env/bin/python3",
      "args": ["/Users/nazeera/Documents/AI_PRODUCER/content_engine/mcp_server.py"]
    }
  }
}
```
Restart Claude Desktop. (Orchestration is cloud; production stays local.)

## Notes
- `make`/`produce` are long-running: they start in the background and return immediately —
  poll with `run_status(run)`.
- The bridge isn't auto-started on boot; run `start_mcp.sh` (or add it to your studio launcher).
