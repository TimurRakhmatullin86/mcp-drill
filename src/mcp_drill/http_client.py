"""An MCP client over the Streamable-HTTP transport, for scanning remote servers.

Only what the scanner needs: the initialize handshake, `tools/list`, and request/response, with a
hard timeout. Presents the same surface as ``StdioServer`` (initialize / list_tools / request /
close) so the scorecard is transport-agnostic. Requires the optional ``http`` extra (httpx).

Enforceability and error-conformance are read from the protocol layer (initialize + tools/list +
malformed calls), so many remote servers can be scored without credentials even when invoking their
tools would require OAuth; a server that demands auth for the handshake is recorded as not-scanned.
"""
from __future__ import annotations

import json
from typing import Any

from . import __version__, jsonrpc
from .stdio_client import PROTOCOL_VERSION, DrillTimeout, ServerCrashed


class HttpServer:
    """Speaks JSON-RPC to a remote MCP server over Streamable HTTP (POST + optional SSE)."""

    def __init__(self, url: str, headers: dict[str, str] | None = None) -> None:
        import httpx  # imported lazily so the core package stays dependency-free

        self.url = url
        self._extra_headers = headers or {}
        self.session_id: str | None = None
        self._next_id = 0
        self._client = httpx.Client(follow_redirects=True)
        self._httpx = httpx

    # -- lifecycle ---------------------------------------------------------------

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:  # noqa: BLE001
            pass

    def __enter__(self) -> "HttpServer":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- transport ---------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
            **self._extra_headers,
        }
        if self.session_id:
            h["Mcp-Session-Id"] = self.session_id
        return h

    def _post(self, message: dict[str, Any], timeout: float) -> dict[str, Any] | None:
        try:
            resp = self._client.post(self.url, json=message, headers=self._headers(), timeout=timeout)
        except self._httpx.TimeoutException as exc:
            raise DrillTimeout(f"HTTP timeout for {message.get('method')}") from exc
        except self._httpx.HTTPError as exc:
            raise ServerCrashed(f"HTTP transport error: {exc}") from exc

        sid = resp.headers.get("mcp-session-id")
        if sid:
            self.session_id = sid
        if resp.status_code in (401, 403):
            raise ServerCrashed(f"authentication required (HTTP {resp.status_code})")
        if resp.status_code == 202:  # accepted notification, no body
            return None
        if resp.status_code >= 400:
            raise ServerCrashed(f"HTTP {resp.status_code}")

        content_type = resp.headers.get("content-type", "")
        expect_id = message.get("id")
        if "text/event-stream" in content_type:
            return _response_from_sse(resp.text, expect_id)
        text = resp.text.strip()
        if not text:
            return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ServerCrashed("non-JSON response body") from exc
        if isinstance(data, list):  # a batch; pick the matching response
            return _match(data, expect_id)
        return data

    # -- request/response --------------------------------------------------------

    def request(self, method: str, params: dict[str, Any] | None = None,
                timeout: float = 20.0) -> dict[str, Any]:
        self._next_id += 1
        rid = self._next_id
        resp = self._post(jsonrpc.request(rid, method, params), timeout=timeout)
        if resp is None:
            raise ServerCrashed(f"empty response to {method!r}")
        return resp

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self._post(jsonrpc.notification(method, params), timeout=20.0)

    def initialize(self, timeout: float = 20.0) -> dict[str, Any]:
        resp = self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "mcp-drill", "version": __version__},
            },
            timeout=timeout,
        )
        try:
            self.notify("notifications/initialized")
        except (DrillTimeout, ServerCrashed):
            pass  # some servers don't accept the notification post-init; not fatal for scanning
        return resp

    def list_tools(self, timeout: float = 20.0) -> list[dict[str, Any]]:
        resp = self.request("tools/list", {}, timeout=timeout)
        result = resp.get("result") or {}
        tools = result.get("tools")
        return tools if isinstance(tools, list) else []


def _match(messages: list[Any], expect_id: Any) -> dict[str, Any] | None:
    for msg in messages:
        if isinstance(msg, dict) and (msg.get("id") == expect_id or jsonrpc.is_response(msg)):
            return msg
    return None


def _response_from_sse(body: str, expect_id: Any) -> dict[str, Any] | None:
    """Parse an SSE body and return the JSON-RPC response matching expect_id (or the first response)."""
    fallback: dict[str, Any] | None = None
    for block in body.replace("\r\n", "\n").split("\n\n"):
        data_lines = [ln[5:].lstrip() for ln in block.split("\n") if ln.startswith("data:")]
        if not data_lines:
            continue
        try:
            msg = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            continue
        if isinstance(msg, dict):
            if msg.get("id") == expect_id:
                return msg
            if fallback is None and jsonrpc.is_response(msg):
                fallback = msg
    return fallback
