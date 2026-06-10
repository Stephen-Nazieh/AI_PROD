#!/usr/bin/env python3
"""
Anthropic ↔ OpenAI API Proxy for Claude Code CLI → Local MLX Models.

Accepts Anthropic Messages API requests on /v1/messages,
translates to OpenAI Chat Completions, forwards to MLX servers,
and translates responses back to Anthropic format.

Usage:
    python anthropic_openai_proxy.py --port 8003

Environment:
    MLX_QWEN7B_URL   → http://127.0.0.1:8002/v1  (default)
    MLX_QWEN32B_URL  → http://127.0.0.1:8001/v1  (default)
    MLX_LLAMA_URL    → http://127.0.0.1:8000/v1  (default)
"""

import argparse
import json
import os
import re
import sys
import time
import uuid
from typing import Any, AsyncGenerator

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

# ── Model routing ──────────────────────────────────────────────────────────

DEFAULT_BACKENDS = {
    "qwen7b": os.getenv("MLX_QWEN7B_URL", "http://127.0.0.1:8002/v1"),
    "qwen32b": os.getenv("MLX_QWEN32B_URL", "http://127.0.0.1:8001/v1"),
    "llama4": os.getenv("MLX_LLAMA_URL", "http://127.0.0.1:8000/v1"),
}

# backend key → the EXACT model name loaded on that server. mlx_lm.server loads
# whatever model the request names, so we MUST send the loaded name (else it tries
# to fetch a nonexistent model from HuggingFace → 404 / multi-GB download / hang).
# (:8000 now serves Qwen2.5-Coder-7B, not the impractically-slow Llama-4-Scout.)
BACKEND_MODEL_NAMES = {
    "qwen7b": "mlx-community/Qwen2.5-7B-Instruct-4bit",
    "qwen32b": "mlx-community/Qwen2.5-32B-Instruct-4bit",
    "llama4": "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit",
}

# Anthropic model name → backend key
MODEL_ALIASES = {
    # Default / catch-all → Qwen32B (always available)
    "default": "qwen32b",
    # Claude family → map to our best available
    "claude-sonnet": "qwen32b",
    "claude-sonnet-4": "qwen32b",
    "claude-haiku": "qwen7b",
    "claude-haiku-4": "qwen7b",
    # Opus maps to Qwen32B for now; Llama4 Scout on :8000 when downloaded
    "claude-opus": "qwen32b",
    "claude-opus-4": "qwen32b",
    "claude-opus-4-20250514": "qwen32b",
    "claude-sonnet-4-20250514": "qwen32b",
    "claude-haiku-4-20250514": "qwen7b",
}


def resolve_backend(model_name: str) -> tuple[str, str]:
    """Return (backend_key, backend_url) for a given Anthropic model name."""
    key = MODEL_ALIASES.get("default")
    for alias, bk in MODEL_ALIASES.items():
        if alias != "default" and model_name.lower().startswith(alias.lower()):
            key = bk
            break
    url = DEFAULT_BACKENDS.get(key, DEFAULT_BACKENDS["qwen32b"])
    return key, url


# ── Translation helpers ────────────────────────────────────────────────────


def anthropic_tools_to_openai(tools: list[dict]) -> list[dict]:
    """Anthropic `tools` → OpenAI `tools`."""
    out = []
    for t in tools:
        out.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        })
    return out


def openai_tools_to_anthropic(tools: list[dict]) -> list[dict]:
    """OpenAI `tools` → Anthropic `tools`."""
    out = []
    for t in tools:
        fn = t.get("function", {})
        out.append({
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return out


def anthropic_messages_to_openai(
    messages: list[dict], system: str | list | None
) -> list[dict]:
    """Anthropic messages + system → OpenAI messages."""
    out = []

    # System message
    if system:
        if isinstance(system, str):
            out.append({"role": "system", "content": system})
        elif isinstance(system, list):
            text = "\n".join(block.get("text", "") for block in system if block.get("type") == "text")
            if text:
                out.append({"role": "system", "content": text})

    for msg in messages:
        role = msg["role"]
        content = msg.get("content", "")

        if role == "user":
            if isinstance(content, list):
                # Handle content blocks: text, tool_result
                text_parts = []
                tool_results = []
                for block in content:
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_result":
                        tool_results.append({
                            "role": "tool",
                            "tool_call_id": block.get("tool_use_id", ""),
                            "content": block.get("content", ""),
                        })
                if text_parts:
                    out.append({"role": "user", "content": "\n".join(text_parts)})
                out.extend(tool_results)
            else:
                out.append({"role": "user", "content": content})

        elif role == "assistant":
            if isinstance(content, list):
                text_parts = []
                tool_calls = []
                for block in content:
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        tool_calls.append({
                            "id": block.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": block.get("name", ""),
                                "arguments": json.dumps(block.get("input", {})),
                            },
                        })
                assistant_msg: dict[str, Any] = {"role": "assistant"}
                if text_parts:
                    assistant_msg["content"] = "\n".join(text_parts)
                else:
                    assistant_msg["content"] = None
                if tool_calls:
                    assistant_msg["tool_calls"] = tool_calls
                out.append(assistant_msg)
            else:
                out.append({"role": "assistant", "content": content})

    return out


def openai_message_to_anthropic(message: dict) -> list[dict]:
    """OpenAI assistant message → Anthropic content blocks."""
    blocks = []
    content = message.get("content")
    if content:
        blocks.append({"type": "text", "text": content})

    for tc in message.get("tool_calls", []):
        fn = tc.get("function", {})
        args = fn.get("arguments", "{}")
        try:
            input_obj = json.loads(args)
        except json.JSONDecodeError:
            input_obj = {"raw": args}
        blocks.append({
            "type": "tool_use",
            "id": tc.get("id", ""),
            "name": fn.get("name", ""),
            "input": input_obj,
        })
    return blocks


def openai_finish_to_anthropic(finish_reason: str | None) -> str | None:
    mapping = {
        "stop": "end_turn",
        "tool_calls": "tool_use",
        "length": "max_tokens",
    }
    return mapping.get(finish_reason, finish_reason)


# ── FastAPI app ─────────────────────────────────────────────────────────────

app = FastAPI(title="Anthropic↔OpenAI Proxy")
http_client = httpx.AsyncClient(timeout=300.0)


@app.get("/health")
async def health():
    return {"status": "ok", "backends": {k: v for k, v in DEFAULT_BACKENDS.items()}}


@app.post("/v1/messages")
async def messages(request: Request):
    body = await request.json()

    # Extract Anthropic fields
    anthropic_model = body.get("model", "claude-sonnet-4")
    max_tokens = body.get("max_tokens", 4096)
    messages_anthropic = body.get("messages", [])
    system = body.get("system")
    tools = body.get("tools")
    stream = body.get("stream", False)
    temperature = body.get("temperature", 0.7)
    top_p = body.get("top_p", 1.0)
    top_k = body.get("top_k")
    stop_sequences = body.get("stop_sequences", [])

    # Resolve backend
    backend_key, backend_url = resolve_backend(anthropic_model)

    # Translate to OpenAI format
    openai_messages = anthropic_messages_to_openai(messages_anthropic, system)
    openai_tools = anthropic_tools_to_openai(tools) if tools else None

    openai_body: dict[str, Any] = {
        # send the loaded MLX model name so the server uses it instead of trying
        # to load the Anthropic name (which would 404/hang) — root-cause fix for
        # slow agent runs through claude-local → :8003 → MLX.
        "model": BACKEND_MODEL_NAMES.get(backend_key, "mlx-community/Qwen2.5-32B-Instruct-4bit"),
        "messages": openai_messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "stream": stream,
    }
    if openai_tools:
        openai_body["tools"] = openai_tools
        openai_body["tool_choice"] = "auto"
    if stop_sequences:
        openai_body["stop"] = stop_sequences
    if top_k is not None:
        openai_body["top_k"] = top_k

    if stream:
        return StreamingResponse(
            _stream_response(openai_body, backend_url, anthropic_model),
            media_type="text/event-stream",
        )
    else:
        return await _non_stream_response(openai_body, backend_url, anthropic_model)


async def _non_stream_response(
    openai_body: dict, backend_url: str, anthropic_model: str
) -> JSONResponse:
    url = f"{backend_url}/chat/completions"
    resp = await http_client.post(url, json=openai_body)
    resp.raise_for_status()
    oai = resp.json()

    choice = oai["choices"][0]
    msg = choice["message"]
    content_blocks = openai_message_to_anthropic(msg)
    usage = oai.get("usage", {})

    anthropic_resp = {
        "id": f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message",
        "role": "assistant",
        "model": anthropic_model,
        "content": content_blocks,
        "stop_reason": openai_finish_to_anthropic(choice.get("finish_reason")),
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
    }
    return JSONResponse(anthropic_resp)


async def _stream_response(
    openai_body: dict, backend_url: str, anthropic_model: str
) -> AsyncGenerator[str, None]:
    """Stream OpenAI SSE → Anthropic SSE."""
    url = f"{backend_url}/chat/completions"
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"

    # Send message_start
    yield f"event: message_start\ndata: {json.dumps({'type':'message_start','message':{'id':msg_id,'type':'message','role':'assistant','model':anthropic_model,'content':[],'stop_reason':None,'usage':{'input_tokens':0,'output_tokens':1}}})}\n\n"

    # content_block_start for text
    yield f"event: content_block_start\ndata: {json.dumps({'type':'content_block_start','index':0,'content_block':{'type':'text','text':''}})}\n\n"

    text_buffer = ""
    tool_calls_buffer: dict[int, dict] = {}
    finish_reason = None
    input_tokens = 0
    output_tokens = 0

    try:
        async with http_client.stream("POST", url, json=openai_body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line or line == "data: [DONE]":
                    if line == "data: [DONE]":
                        break
                    continue
                if not line.startswith("data: "):
                    continue
                data = json.loads(line[6:])

                # Usage from the final chunk (some servers send it)
                if "usage" in data and data["usage"]:
                    u = data["usage"]
                    input_tokens = u.get("prompt_tokens", input_tokens)
                    output_tokens = u.get("completion_tokens", output_tokens)

                delta = data.get("choices", [{}])[0].get("delta", {})

                # Text content
                if delta.get("content"):
                    text = delta["content"]
                    text_buffer += text
                    yield f"event: content_block_delta\ndata: {json.dumps({'type':'content_block_delta','index':0,'delta':{'type':'text_delta','text':text}})}\n\n"

                # Tool calls (buffered)
                for tc in delta.get("tool_calls", []):
                    idx = tc.get("index", 0)
                    if idx not in tool_calls_buffer:
                        tool_calls_buffer[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc.get("id"):
                        tool_calls_buffer[idx]["id"] = tc["id"]
                    if tc.get("function", {}).get("name"):
                        tool_calls_buffer[idx]["name"] = tc["function"]["name"]
                    if tc.get("function", {}).get("arguments"):
                        tool_calls_buffer[idx]["arguments"] += tc["function"]["arguments"]

                # Finish reason
                fr = data.get("choices", [{}])[0].get("finish_reason")
                if fr:
                    finish_reason = fr

    except Exception as e:
        yield f"event: error\ndata: {json.dumps({'type':'error','error':{'type':'api_error','message':str(e)}})}\n\n"
        return

    # content_block_stop for text
    yield f"event: content_block_stop\ndata: {json.dumps({'type':'content_block_stop','index':0})}\n\n"

    # Emit tool_use blocks if any
    if tool_calls_buffer:
        for idx, tc in sorted(tool_calls_buffer.items()):
            block_idx = idx + 1  # after text block
            try:
                input_obj = json.loads(tc["arguments"])
            except json.JSONDecodeError:
                input_obj = {"raw": tc["arguments"]}
            yield f"event: content_block_start\ndata: {json.dumps({'type':'content_block_start','index':block_idx,'content_block':{'type':'tool_use','id':tc['id'],'name':tc['name'],'input':input_obj}})}\n\n"
            yield f"event: content_block_stop\ndata: {json.dumps({'type':'content_block_stop','index':block_idx})}\n\n"

    # message_delta
    stop = openai_finish_to_anthropic(finish_reason)
    yield f"event: message_delta\ndata: {json.dumps({'type':'message_delta','delta':{'stop_reason':stop,'stop_sequence':None},'usage':{'output_tokens':max(len(text_buffer.split()),1)}})}\n\n"

    # message_stop
    yield f"event: message_stop\ndata: {json.dumps({'type':'message_stop'})}\n\n"


# ── Entrypoint ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Anthropic↔OpenAI proxy for local MLX")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8003)
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
