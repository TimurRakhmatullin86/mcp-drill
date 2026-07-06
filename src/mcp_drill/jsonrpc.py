"""JSON-RPC 2.0 helpers shared by the injector and the scorecard.

MCP frames messages as newline-delimited JSON over stdio: one JSON value per line, UTF-8,
with no embedded newlines. These helpers stay transport-agnostic; framing lives in the client.
"""
from __future__ import annotations

from typing import Any

# Standard JSON-RPC 2.0 error codes (see the spec) plus the MCP-relevant subset.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


def request(msg_id: Any, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    msg: dict[str, Any] = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        msg["params"] = params
    return msg


def notification(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    return msg


def error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def is_response(msg: dict[str, Any]) -> bool:
    """A response carries an id and exactly one of result/error."""
    return isinstance(msg, dict) and "id" in msg and ("result" in msg or "error" in msg)


def is_notification(msg: dict[str, Any]) -> bool:
    return isinstance(msg, dict) and "method" in msg and "id" not in msg


def has_error(msg: dict[str, Any]) -> bool:
    return isinstance(msg, dict) and isinstance(msg.get("error"), dict)


def error_code(msg: dict[str, Any]) -> int | None:
    err = msg.get("error") if isinstance(msg, dict) else None
    return err.get("code") if isinstance(err, dict) else None


def is_tool_error(msg: dict[str, Any]) -> bool:
    """MCP convention: a tool-level failure is a normal result with isError == true."""
    result = msg.get("result") if isinstance(msg, dict) else None
    return isinstance(result, dict) and result.get("isError") is True
