"""A tiny MCP stdio server used as a deterministic test fixture (no network, no LLM).

MCP_DRILL_FAKE_MODE=good  -> handles bad input with proper errors, strict output schema.
MCP_DRILL_FAKE_MODE=bad   -> silently accepts invalid input, declares a loose output schema.
"""
import json
import os
import sys

MODE = os.environ.get("MCP_DRILL_FAKE_MODE", "good")

STRICT_TOOL = {
    "name": "echo",
    "description": "Echo text back.",
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
        "additionalProperties": False,
    },
    "outputSchema": {
        "type": "object",
        "properties": {"echoed": {"type": "string", "enum": ["hello", "world"]}},
        "required": ["echoed"],
        "additionalProperties": False,
    },
}
LOOSE_TOOL = {
    "name": "echo",
    "description": "Echo text back.",
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
    "outputSchema": {"type": "object"},  # no properties, additionalProperties allowed => loose
}


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def ok(mid, result):
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def err(mid, code, message):
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def handle(msg):
    mid = msg.get("id")
    method = msg.get("method")
    if method == "initialize":
        return ok(mid, {
            "protocolVersion": "2025-06-18",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "fake-mcp", "version": "0.0.1"},
        })
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return ok(mid, {"tools": [LOOSE_TOOL if MODE == "bad" else STRICT_TOOL]})
    if method == "tools/call":
        params = msg.get("params") or {}
        name, args = params.get("name"), (params.get("arguments") or {})
        if MODE == "bad":
            return ok(mid, {"content": [{"type": "text", "text": "ok"}]})
        if name != "echo":
            return err(mid, -32602, f"unknown tool: {name}")
        if "text" not in args:
            return err(mid, -32602, "missing required argument: text")
        return ok(mid, {
            "content": [{"type": "text", "text": args["text"]}],
            "structuredContent": {"echoed": args["text"]},
        })
    if MODE == "bad":
        return ok(mid, {"note": "accepted unknown method"})
    return err(mid, -32601, f"method not found: {method}")


def main():
    while True:
        line = sys.stdin.readline()
        if line == "":
            break
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            send(err(None, -32700, "parse error"))
            continue
        resp = handle(msg)
        if resp is not None:
            send(resp)


if __name__ == "__main__":
    main()
