#!/bin/bash
# Start the Content Engine MCP bridge (mcpo → OpenAPI on :8900) for Open WebUI.
cd "$(dirname "$0")/.."
exec env/bin/mcpo --port 8900 -- env/bin/python3 content_engine/mcp_server.py
