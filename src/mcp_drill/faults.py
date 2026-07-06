"""Fault definitions injected into server -> client responses by the proxy.

Each fault maps a response message to an ``Injection``: an optional delay plus the payload to
emit (the possibly-mutated message, a raw line for malformed output, or DROP to swallow it).
Faults are deliberately small and deterministic so a CI run is reproducible with a fixed seed.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable

from . import jsonrpc

# Sentinel: emit nothing at all for this message (simulates a lost/never-arriving response).
DROP = object()


class Raw(str):
    """A raw line emitted verbatim (used to produce malformed, non-JSON output)."""


@dataclass
class Injection:
    delay: float
    payload: Any  # a dict to send, a Raw string, or DROP


# fault(message, params) -> Injection
FaultFn = Callable[[dict[str, Any], dict[str, Any]], Injection]
_REGISTRY: dict[str, FaultFn] = {}


def register(name: str) -> Callable[[FaultFn], FaultFn]:
    def deco(fn: FaultFn) -> FaultFn:
        _REGISTRY[name] = fn
        return fn
    return deco


def get(name: str) -> FaultFn:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(f"unknown fault {name!r}; known: {', '.join(sorted(_REGISTRY))}")


def names() -> list[str]:
    return sorted(_REGISTRY)


# -- individual faults -----------------------------------------------------------


@register("latency")
def latency(message: dict[str, Any], params: dict[str, Any]) -> Injection:
    """Forward the real response, but after an added delay."""
    return Injection(delay=float(params.get("seconds", 5.0)), payload=message)


@register("timeout")
def timeout(message: dict[str, Any], params: dict[str, Any]) -> Injection:
    """Never deliver the response (optionally after a delay) — the request appears to hang."""
    return Injection(delay=float(params.get("seconds", 0.0)), payload=DROP)


@register("truncate")
def truncate(message: dict[str, Any], params: dict[str, Any]) -> Injection:
    """Cut tool text content short, as if the stream was severed mid-response."""
    keep = int(params.get("keep", 16))
    out = copy.deepcopy(message)
    result = out.get("result")
    if isinstance(result, dict) and isinstance(result.get("content"), list):
        for block in result["content"]:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                block["text"] = block["text"][:keep]
    return Injection(delay=0.0, payload=out)


@register("corrupt")
def corrupt(message: dict[str, Any], params: dict[str, Any]) -> Injection:
    """Replace tool output with a well-formed but wrong payload (the silent-corruption case)."""
    token = str(params.get("token", "�CORRUPTED�"))
    out = copy.deepcopy(message)
    result = out.get("result")
    if isinstance(result, dict):
        if isinstance(result.get("content"), list):
            for block in result["content"]:
                if isinstance(block, dict) and "text" in block:
                    block["text"] = token
        if isinstance(result.get("structuredContent"), dict):
            for key in result["structuredContent"]:
                result["structuredContent"][key] = token
    return Injection(delay=0.0, payload=out)


@register("malformed")
def malformed(message: dict[str, Any], params: dict[str, Any]) -> Injection:
    """Emit a broken, non-parseable JSON line in place of the response."""
    rid = message.get("id")
    return Injection(delay=0.0, payload=Raw('{"jsonrpc":"2.0","id":%r,"result":' % rid))


@register("error")
def error(message: dict[str, Any], params: dict[str, Any]) -> Injection:
    """Replace the response with a synthetic JSON-RPC internal error."""
    code = int(params.get("code", jsonrpc.INTERNAL_ERROR))
    msg = str(params.get("message", "injected fault"))
    return Injection(delay=0.0, payload=jsonrpc.error(message.get("id"), code, msg))


@register("drop_tool")
def drop_tool(message: dict[str, Any], params: dict[str, Any]) -> Injection:
    """Remove one tool from a tools/list result (a capability vanishes at runtime)."""
    out = copy.deepcopy(message)
    result = out.get("result")
    if isinstance(result, dict) and isinstance(result.get("tools"), list) and result["tools"]:
        drop = params.get("name")
        result["tools"] = [
            t for i, t in enumerate(result["tools"])
            if (t.get("name") != drop if drop else i != 0)
        ]
    return Injection(delay=0.0, payload=out)


@dataclass
class FaultSpec:
    """A configured fault: its name, the resolved function, and its parameters."""
    name: str
    params: dict[str, Any]

    @property
    def fn(self) -> FaultFn:
        return get(self.name)

    @classmethod
    def parse(cls, spec: str) -> "FaultSpec":
        """Parse ``name`` or ``name:k=v,k=v`` into a FaultSpec."""
        name, _, rest = spec.partition(":")
        params: dict[str, Any] = {}
        for pair in filter(None, rest.split(",")):
            key, _, value = pair.partition("=")
            params[key.strip()] = _coerce(value.strip())
        return cls(name=name.strip(), params=params)


def _coerce(value: str) -> Any:
    for cast in (int, float):
        try:
            return cast(value)
        except ValueError:
            continue
    return value
