"""Transparent stdio fault-injecting proxy: `mcp-drill wrap -- <server cmd>`.

The proxy speaks MCP on both sides. It relays the client's requests to the real server
verbatim and applies configured faults to the server's responses on the way back, so an
MCP client (an agent, an IDE, a test) exercises failure paths without changing any code.

    MCP client <== our stdin/stdout ==> [ mcp-drill ] <== child stdio ==> real MCP server

Only responses to targeted methods (tools/call by default) are perturbed; the initialize
handshake and everything else pass through untouched.
"""
from __future__ import annotations

import json
import random
import sys
import threading
import time
from typing import Any, BinaryIO

from . import faults
from .faults import DROP, FaultSpec, Injection, Raw
from .stdio_client import StdioServer


class FaultProxy:
    def __init__(
        self,
        server_command: list[str],
        specs: list[FaultSpec],
        target_methods: tuple[str, ...] = ("tools/call",),
        probability: float = 1.0,
        seed: int | None = None,
    ) -> None:
        self.server = StdioServer(server_command)
        self.specs = specs
        self.target_methods = target_methods
        self.probability = probability
        self._rng = random.Random(seed)
        self._pending: dict[Any, str] = {}  # request id -> method (from client -> server)
        self._pending_lock = threading.Lock()
        self._out: BinaryIO = sys.stdout.buffer
        self._out_lock = threading.Lock()

    # -- pumps -------------------------------------------------------------------

    def _pump_client_to_server(self, client_in: BinaryIO) -> None:
        for line in client_in:
            text = line.strip()
            if text:
                try:
                    msg = json.loads(text)
                    if isinstance(msg, dict) and "id" in msg and "method" in msg:
                        with self._pending_lock:
                            self._pending[msg["id"]] = msg["method"]
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass  # forward opaque lines unchanged
            try:
                self.server.forward(line)
            except Exception:  # noqa: BLE001 - server gone; stop pumping
                break

    def _pump_server_to_client(self) -> None:
        while True:
            try:
                msg = self.server.read_message(timeout=3600.0)
            except Exception:  # noqa: BLE001 - EOF/crash: nothing more to relay
                break
            injection = self._maybe_fault(msg)
            if injection is None:
                self._emit(msg)
                continue
            if injection.delay > 0:
                time.sleep(injection.delay)
            if injection.payload is DROP:
                continue
            if isinstance(injection.payload, Raw):
                self._emit_raw(str(injection.payload))
            else:
                self._emit(injection.payload)

    def _maybe_fault(self, msg: dict[str, Any]) -> Injection | None:
        if not self.specs or "id" not in msg:
            return None
        with self._pending_lock:
            method = self._pending.pop(msg["id"], None)
        if method not in self.target_methods:
            return None
        if self._rng.random() > self.probability:
            return None
        spec = self._rng.choice(self.specs)
        return spec.fn(msg, spec.params)

    # -- output ------------------------------------------------------------------

    def _emit(self, obj: Any) -> None:
        self._emit_raw(json.dumps(obj, ensure_ascii=False))

    def _emit_raw(self, line: str) -> None:
        with self._out_lock:
            self._out.write(line.encode("utf-8") + b"\n")
            self._out.flush()

    # -- run ---------------------------------------------------------------------

    def run(self) -> int:
        self.server.start()
        reader = threading.Thread(target=self._pump_server_to_client, daemon=True)
        reader.start()
        try:
            self._pump_client_to_server(sys.stdin.buffer)
        finally:
            self.server.close()
        return 0


def build_specs(spec_strings: list[str]) -> list[FaultSpec]:
    specs = [FaultSpec.parse(s) for s in spec_strings if s]
    for spec in specs:  # validate names up front so we fail fast
        faults.get(spec.name)
    return specs
