"""A minimal MCP client over the stdio transport, with no external dependencies.

Only what is needed to drive a server for reliability probing: spawn it as a subprocess,
run the initialize handshake, and exchange newline-delimited JSON-RPC messages with a hard
timeout so a hanging server never hangs the harness. No language model is involved anywhere.
"""
from __future__ import annotations

import json
import os
import selectors
import subprocess
import threading
import time
from typing import Any

from . import __version__, jsonrpc

# A recent MCP protocol revision; servers negotiate their own in the initialize result.
PROTOCOL_VERSION = "2025-06-18"


class DrillTimeout(TimeoutError):
    """No JSON-RPC line arrived within the deadline (the server hung)."""


class ServerCrashed(RuntimeError):
    """The server process exited or closed stdout unexpectedly."""


class StdioServer:
    """Spawns and speaks JSON-RPC to a single MCP server over stdio."""

    def __init__(self, command: list[str], env: dict[str, str] | None = None,
                 cwd: str | None = None) -> None:
        self.command = command
        self._env = {**os.environ, **(env or {})}
        self._cwd = cwd
        self.proc: subprocess.Popen[bytes] | None = None
        self._sel = selectors.DefaultSelector()
        self._buf = b""
        self._next_id = 0
        self._stderr_tail: list[str] = []

    # -- lifecycle ---------------------------------------------------------------

    def start(self) -> "StdioServer":
        self.proc = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self._env,
            cwd=self._cwd,
        )
        os.set_blocking(self.proc.stdout.fileno(), False)  # type: ignore[union-attr]
        self._sel.register(self.proc.stdout, selectors.EVENT_READ)
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        return self

    def close(self) -> None:
        if self.proc is None:
            return
        for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            try:
                stream.close()  # type: ignore[union-attr]
            except Exception:  # noqa: BLE001
                pass
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def __enter__(self) -> "StdioServer":
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.close()

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    @property
    def stderr_tail(self) -> str:
        return "\n".join(self._stderr_tail[-20:])

    def _drain_stderr(self) -> None:
        stderr = self.proc.stderr if self.proc else None
        if stderr is None:
            return
        try:
            for raw in stderr:
                self._stderr_tail.append(raw.decode("utf-8", "replace").rstrip("\n"))
                if len(self._stderr_tail) > 200:
                    del self._stderr_tail[:-200]
        except (ValueError, OSError):
            return  # the stream was closed under us (e.g. during close()); nothing more to drain

    def _why_dead(self) -> str:
        code = self.proc.poll() if self.proc else None
        tail = self.stderr_tail
        return f"exit={code}" + (f"; stderr: {tail}" if tail else "")

    # -- raw transport -----------------------------------------------------------

    def send_obj(self, obj: Any) -> None:
        """Send an arbitrary object as one JSON line (used for malformed probes too)."""
        if not self.alive():
            raise ServerCrashed(self._why_dead())
        line = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
        assert self.proc is not None and self.proc.stdin is not None
        try:
            self.proc.stdin.write(line)
            self.proc.stdin.flush()
        except (BrokenPipeError, ValueError):
            raise ServerCrashed(self._why_dead())

    def forward(self, raw: bytes) -> None:
        """Write raw bytes to the server's stdin verbatim (used by the proxy pump)."""
        if not self.alive():
            raise ServerCrashed(self._why_dead())
        assert self.proc is not None and self.proc.stdin is not None
        try:
            self.proc.stdin.write(raw if raw.endswith(b"\n") else raw + b"\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, ValueError):
            raise ServerCrashed(self._why_dead())

    def read_message(self, timeout: float) -> dict[str, Any]:
        """Return the next JSON message from stdout, or raise DrillTimeout/ServerCrashed."""
        deadline = time.monotonic() + timeout
        while True:
            msg = self._take_buffered_line()
            if msg is not None:
                return msg
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                if not self.alive():
                    raise ServerCrashed(self._why_dead())
                raise DrillTimeout(f"no message within {timeout:.1f}s")
            if not self._sel.select(timeout=remaining):
                continue
            chunk = self.proc.stdout.read()  # type: ignore[union-attr]
            if chunk is None:  # non-blocking pipe with nothing ready yet
                continue
            if chunk == b"":  # EOF
                buffered = self._take_buffered_line()
                if buffered is not None:
                    return buffered
                raise ServerCrashed("server closed stdout; " + self._why_dead())
            self._buf += chunk

    def _take_buffered_line(self) -> dict[str, Any] | None:
        while True:
            nl = self._buf.find(b"\n")
            if nl == -1:
                return None
            line = self._buf[:nl].strip()
            self._buf = self._buf[nl + 1:]
            if not line:
                continue
            try:
                return json.loads(line.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                # Some servers print non-protocol noise to stdout; skip it.
                continue

    # -- request/response --------------------------------------------------------

    def request(self, method: str, params: dict[str, Any] | None = None,
                timeout: float = 20.0) -> dict[str, Any]:
        """Send a request and return the response whose id matches; skip unrelated traffic."""
        self._next_id += 1
        rid = self._next_id
        self.send_obj(jsonrpc.request(rid, method, params))
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise DrillTimeout(f"no response to {method!r} (id={rid}) within {timeout:.1f}s")
            msg = self.read_message(remaining)
            if msg.get("id") == rid:
                return msg
            # Notifications / server-initiated requests / other ids: ignore while probing.

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self.send_obj(jsonrpc.notification(method, params))

    def initialize(self, timeout: float = 20.0) -> dict[str, Any]:
        if self.proc is None:
            self.start()
        resp = self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "mcp-drill", "version": __version__},
            },
            timeout=timeout,
        )
        self.notify("notifications/initialized")
        return resp

    def list_tools(self, timeout: float = 20.0) -> list[dict[str, Any]]:
        resp = self.request("tools/list", {}, timeout=timeout)
        result = resp.get("result") or {}
        tools = result.get("tools")
        return tools if isinstance(tools, list) else []
