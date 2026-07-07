"""Model-free reliability scoring for a single MCP server.

Everything here is deterministic and involves no language model, so the results are properties
of the server and the protocol rather than of whichever agent calls it. Two axes are measured:

1. Error conformance — how the server answers deliberately invalid requests (a spec JSON-RPC
   error and an MCP tool error both count as handled; a normal success, a hang, or a crash do not).
2. Output-contract enforceability — of the tools that declare an ``outputSchema``, how many would
   actually **reject a corrupted response**. For each such schema we build an instance that keeps
   the declared structure and types but carries corrupted leaf values, then check whether it still
   validates. A schema that validates the corruption is *vacuous*: downstream validation gives no
   protection against a well-typed but wrong response. This is an outcome, not a style judgement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import __version__, jsonrpc
from .stdio_client import DrillTimeout, ServerCrashed, StdioServer

try:  # enforceability needs a validator; degrade to a structural check if it is absent
    import jsonschema

    _HAVE_JSONSCHEMA = True
except Exception:  # noqa: BLE001
    _HAVE_JSONSCHEMA = False

# How a server answered a bad request.
HANDLED = {"jsonrpc_error", "tool_error"}  # acceptable
MISHANDLED = {"accepted", "timeout", "crash", "unexpected"}  # not acceptable

_ABSENT_TOOL = "__mcp_drill_absent_tool__"

# Sentinels used to corrupt a response's leaf values while preserving its declared types.
_CORRUPT_STRING = "mcp-drill-corruption"
_CORRUPT_INT = -999999999
_CORRUPT_NUMBER = -1.5e308
_VALUE_CONSTRAINTS = {
    "enum", "const", "pattern", "format", "minimum", "maximum", "exclusiveMinimum",
    "exclusiveMaximum", "minLength", "maxLength", "multipleOf", "minItems", "maxItems",
}


@dataclass
class ServerScore:
    name: str
    command: list[str]
    transport: str = "stdio"
    handshake_ok: bool = False
    server_info: dict[str, Any] = field(default_factory=dict)
    protocol_version: str | None = None
    n_tools: int = 0
    tools_with_output_schema: int = 0
    enforceable_output_schemas: int = 0  # declares a schema that rejects a corrupted payload
    vacuous_output_schemas: int = 0      # declares a schema that still validates a corrupted payload
    fastmcp_wrapped_tools: int = 0       # schema carries the x-fastmcp-wrap-result marker
    probes: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def output_schema_coverage(self) -> float | None:
        return (self.tools_with_output_schema / self.n_tools) if self.n_tools else None

    @property
    def enforceable_rate(self) -> float | None:
        """Share of ALL tools whose declared output contract rejects a corrupted response."""
        return (self.enforceable_output_schemas / self.n_tools) if self.n_tools else None

    @property
    def corruption_acceptance_rate(self) -> float | None:
        """Of tools that declare a schema, the share that still validate a corrupted payload."""
        n = self.tools_with_output_schema
        return (self.vacuous_output_schemas / n) if n else None

    @property
    def error_handling_score(self) -> float | None:
        graded = [v for v in self.probes.values() if v != "skipped"]
        if not graded:
            return None
        return sum(v in HANDLED for v in graded) / len(graded)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "command": self.command,
            "transport": self.transport,
            "handshake_ok": self.handshake_ok,
            "server_info": self.server_info,
            "protocol_version": self.protocol_version,
            "n_tools": self.n_tools,
            "tools_with_output_schema": self.tools_with_output_schema,
            "output_schema_coverage": self.output_schema_coverage,
            "enforceable_output_schemas": self.enforceable_output_schemas,
            "vacuous_output_schemas": self.vacuous_output_schemas,
            "enforceable_rate": self.enforceable_rate,
            "corruption_acceptance_rate": self.corruption_acceptance_rate,
            "fastmcp_wrapped_tools": self.fastmcp_wrapped_tools,
            "error_handling_score": self.error_handling_score,
            "probes": self.probes,
            "notes": self.notes,
            "jsonschema_available": _HAVE_JSONSCHEMA,
            "tool_version": __version__,
        }


def _classify(result_or_exc: Any) -> str:
    if isinstance(result_or_exc, DrillTimeout):
        return "timeout"
    if isinstance(result_or_exc, ServerCrashed):
        return "crash"
    if isinstance(result_or_exc, Exception):
        return "unexpected"
    msg = result_or_exc
    if jsonrpc.has_error(msg):
        return "jsonrpc_error"
    if jsonrpc.is_tool_error(msg):
        return "tool_error"
    if isinstance(msg, dict) and "result" in msg:
        return "accepted"  # server treated an invalid request as valid
    return "unexpected"


def _probe(server: StdioServer, send, timeout: float) -> str:
    try:
        return _classify(send())
    except (DrillTimeout, ServerCrashed) as exc:
        return _classify(exc)
    except Exception as exc:  # noqa: BLE001
        return _classify(exc)


def scan_server(name: str, command: list[str], timeout: float = 20.0) -> ServerScore:
    """Scan a server launched over stdio (command = the process argv)."""
    return _scan(ServerScore(name=name, command=command, transport="stdio"),
                 StdioServer(command), timeout)


def scan_http(name: str, url: str, headers: dict[str, str] | None = None,
              timeout: float = 20.0) -> ServerScore:
    """Scan a remote server over the Streamable-HTTP transport."""
    from .http_client import HttpServer

    return _scan(ServerScore(name=name, command=[url], transport="http"),
                 HttpServer(url, headers), timeout)


def _scan(score: ServerScore, server: Any, timeout: float) -> ServerScore:
    try:
        try:
            init = server.initialize(timeout=timeout)
        except (DrillTimeout, ServerCrashed, OSError) as exc:
            score.notes.append(f"initialize failed: {exc}")
            return score
        if jsonrpc.has_error(init):
            score.notes.append(f"initialize returned error: {init.get('error')}")
            return score
        score.handshake_ok = True
        result = init.get("result") or {}
        score.server_info = result.get("serverInfo") or {}
        score.protocol_version = result.get("protocolVersion")

        try:
            tools = server.list_tools(timeout=timeout)
        except (DrillTimeout, ServerCrashed) as exc:
            score.notes.append(f"tools/list failed: {exc}")
            tools = []
        _score_tools(score, tools)
        _run_probes(score, server, tools, timeout)
    finally:
        server.close()
    return score


def _score_tools(score: ServerScore, tools: list[dict[str, Any]]) -> None:
    score.n_tools = len(tools)
    for tool in tools:
        out_schema = tool.get("outputSchema")
        if not isinstance(out_schema, dict):
            continue
        score.tools_with_output_schema += 1
        if _is_fastmcp_wrapped(out_schema):
            score.fastmcp_wrapped_tools += 1
        if accepts_corruption(out_schema)[0]:
            score.vacuous_output_schemas += 1
        else:
            score.enforceable_output_schemas += 1


def _run_probes(score: ServerScore, server: StdioServer, tools: list[dict[str, Any]],
                timeout: float) -> None:
    # 1. Unknown method should be a JSON-RPC "method not found".
    score.probes["unknown_method"] = _probe(
        server, lambda: server.request("drill/nonexistent_method", {}, timeout=timeout), timeout)

    # 2. Calling a tool that does not exist should error, not succeed.
    score.probes["unknown_tool"] = _probe(
        server,
        lambda: server.request("tools/call", {"name": _ABSENT_TOOL, "arguments": {}}, timeout=timeout),
        timeout,
    )

    # 3. Calling a real tool with its required arguments missing should error, not succeed.
    target = _tool_with_required_args(tools)
    if target is None:
        score.probes["missing_required_args"] = "skipped"
        score.notes.append("no tool declares required arguments; missing-args probe skipped")
    else:
        score.probes["missing_required_args"] = _probe(
            server,
            lambda: server.request("tools/call", {"name": target, "arguments": {}}, timeout=timeout),
            timeout,
        )


def _tool_with_required_args(tools: list[dict[str, Any]]) -> str | None:
    for tool in tools:
        schema = tool.get("inputSchema")
        if isinstance(schema, dict) and schema.get("required"):
            return tool.get("name")
    return None


# -- output-contract enforceability ----------------------------------------------


def _is_fastmcp_wrapped(schema: dict[str, Any]) -> bool:
    """Detect the MCP Python SDK / FastMCP auto-wrapped-result marker (a vacuous default)."""
    return schema.get("x-fastmcp-wrap-result") is True


def accepts_corruption(schema: dict[str, Any]) -> tuple[bool, str]:
    """Return (accepts, reason). accepts=True means a corrupted-but-well-typed payload still
    validates against the schema — the declared contract cannot catch a wrong response."""
    if not isinstance(schema, dict) or not schema:
        return True, "no schema"
    if not _HAVE_JSONSCHEMA:
        return (not _has_value_constraint(schema)), "structural (no validator)"
    instance = _corruption_instance(schema)
    try:
        jsonschema.validate(instance, schema)
        return True, "corrupted payload validates against the declared schema"
    except jsonschema.ValidationError:
        return False, "declared schema rejects the corrupted payload"
    except Exception:  # noqa: BLE001 - a schema we cannot even compile enforces nothing
        return True, "schema is not a compilable JSON Schema"


def _corruption_instance(node: Any) -> Any:
    """Build a value that satisfies the schema's declared structure/types but corrupts every leaf,
    so only a value-level constraint (enum/const/pattern/format/bounds) can reject it."""
    if not isinstance(node, dict):
        return _CORRUPT_STRING
    for comb in ("allOf", "anyOf", "oneOf"):
        options = node.get(comb)
        if isinstance(options, list) and options:
            return _corruption_instance(options[0])
    t = node.get("type")
    if isinstance(t, list):
        t = next((x for x in t if x != "null"), t[0] if t else None)
    if t == "object" or "properties" in node:
        props = node.get("properties") or {}
        required = node.get("required") or list(props.keys())
        return {key: _corruption_instance(props.get(key, {})) for key in required}
    if t == "array":
        items = node.get("items")
        return [_corruption_instance(items)] if isinstance(items, dict) else []
    if t == "integer":
        return _CORRUPT_INT
    if t == "number":
        return _CORRUPT_NUMBER
    if t == "boolean":
        return False
    if t == "null":
        return None
    return _CORRUPT_STRING


def _has_value_constraint(node: Any) -> bool:
    """Structural fallback: does the schema constrain any value beyond its type/structure?"""
    if not isinstance(node, dict):
        return False
    if _VALUE_CONSTRAINTS & set(node):
        return True
    for key in ("properties", "$defs", "definitions"):
        sub = node.get(key)
        if isinstance(sub, dict) and any(_has_value_constraint(v) for v in sub.values()):
            return True
    for key in ("items", "additionalProperties"):
        if _has_value_constraint(node.get(key)):
            return True
    for key in ("allOf", "anyOf", "oneOf"):
        opts = node.get(key)
        if isinstance(opts, list) and any(_has_value_constraint(v) for v in opts):
            return True
    return False
