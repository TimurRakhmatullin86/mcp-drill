"""Run the model-free reliability scorecard across a list of MCP servers.

    python studies/pilot/run_pilot.py [servers.json]

Writes results.json (raw per-server scores) and SCORECARD.md (a shareable table) next to this
script. Every server is scanned in isolation; a server that fails to start is recorded, not fatal.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mcp_drill.scorecard import scan_server  # noqa: E402

HERE = Path(__file__).parent


def main() -> int:
    spec_path = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "servers.json"
    servers = json.loads(spec_path.read_text(encoding="utf-8"))
    results = []
    for s in servers:
        print(f"[{s['name']}] scanning...", file=sys.stderr, flush=True)
        t0 = time.time()
        score = scan_server(s["name"], s["command"], timeout=s.get("timeout", 60.0))
        dt = round(time.time() - t0, 1)
        row = score.to_dict()
        row["scan_seconds"] = dt
        results.append(row)
        print(
            f"[{s['name']}] handshake={row['handshake_ok']} tools={row['n_tools']} "
            f"schema_cov={_pct(row['output_schema_coverage'])} "
            f"err_handling={_pct(row['error_handling_score'])} ({dt:.0f}s)",
            file=sys.stderr, flush=True,
        )
    out = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_servers": len(results),
        "servers": results,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_scorecard(out)
    print(f"\nwrote {HERE/'results.json'} and {HERE/'SCORECARD.md'}", file=sys.stderr)
    return 0


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def _write_scorecard(out: dict) -> None:
    rows = out["servers"]
    started = [r for r in rows if r["handshake_ok"]]
    lines = [
        "# MCP server reliability scorecard (pilot)",
        "",
        f"Generated {out['generated']} by mcp-drill. Deterministic and model-free: every number is a",
        "property of the server and the protocol, reproducible with `python studies/pilot/run_pilot.py`.",
        "",
        f"- Servers scanned: **{out['n_servers']}**; started cleanly: **{len(started)}**",
    ]
    notable: list[str] = []
    if started:
        total_tools = sum(r["n_tools"] for r in started)
        with_schema = sum(r["tools_with_output_schema"] for r in started)
        vacuous = sum(r["vacuous_output_schemas"] for r in started)
        enforceable = sum(r["enforceable_output_schemas"] for r in started)
        fastmcp = sum(r["fastmcp_wrapped_tools"] for r in started)
        imperfect_err = [r for r in started if (r["error_handling_score"] or 0) < 1.0]
        vac_servers = [r for r in started if (r["corruption_acceptance_rate"] or 0) > 0]
        if total_tools:
            lines.append(
                f"- **Only {_pct(enforceable / total_tools)} of tools ({enforceable}/{total_tools}) "
                f"declare an output contract that rejects a corrupted response.** For the rest, "
                f"schema validation cannot catch a well-typed but wrong result."
            )
            lines.append(
                f"- Tiers: **no schema {_pct(1 - with_schema / total_tools)}** "
                f"({total_tools - with_schema}/{total_tools}); **vacuous schema "
                f"{_pct(vacuous / total_tools)}** ({vacuous}/{total_tools}); **enforceable "
                f"{_pct(enforceable / total_tools)}** ({enforceable}/{total_tools})"
            )
            if fastmcp:
                lines.append(
                    f"- SDK-auto-wrapped (`x-fastmcp-wrap-result`): **{fastmcp}/{total_tools}** tools — "
                    f"a vacuous default inherited from the MCP Python SDK / FastMCP"
                )
        lines += [
            f"- Error handling: **{len(started) - len(imperfect_err)}/{len(started)}** servers handled "
            f"every invalid-input probe correctly",
            f"- Declare output schemas that stay valid under corruption: **{len(vac_servers)}/{len(started)}** servers",
        ]
        for r in imperfect_err:
            bad = [f"`{k}`={v}" for k, v in r["probes"].items() if v not in ("jsonrpc_error", "tool_error", "skipped")]
            notable.append(f"- `{r['name']}` mishandled: {', '.join(bad)}")
        for r in vac_servers:
            if (r["corruption_acceptance_rate"] or 0) == 1.0:
                notable.append(
                    f"- `{r['name']}` — 100% of its declared output schemas validate a corrupted payload"
                    + (" (SDK-auto-wrapped)" if r["fastmcp_wrapped_tools"] else ""))
    lines += [
        "",
        "| Server | Started | Tools | Schema coverage | Enforceable | Vacuous-of-declared | Error handling |",
        "|---|:--:|--:|--:|--:|--:|--:|",
    ]
    for r in rows:
        lines.append(
            f"| `{r['name']}` | {'yes' if r['handshake_ok'] else 'NO'} | "
            f"{r['n_tools'] or ''} | {_pct(r['output_schema_coverage'])} | "
            f"{_pct(r['enforceable_rate'])} | {_pct(r['corruption_acceptance_rate'])} | "
            f"{_pct(r['error_handling_score'])} |"
        )
    if notable:
        lines += ["", "## Notable", ""] + notable
    lines += [
        "",
        "**Columns.** *Schema coverage* = share of tools declaring an `outputSchema`. *Enforceable* =",
        "share of all tools whose declared schema rejects a corrupted (well-typed but wrong) response.",
        "*Vacuous-of-declared* = of tools that declare a schema, the share that still validate the",
        "corrupted payload. *Error handling* = share of invalid-input probes (unknown method, unknown",
        "tool, missing required args) answered with a JSON-RPC error or an MCP tool error rather than a",
        "false success, a hang, or a crash.",
        "",
    ]
    (HERE / "SCORECARD.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
