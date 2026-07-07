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
from mcp_drill.scorecard import scan_http, scan_server  # noqa: E402

HERE = Path(__file__).parent


def main() -> int:
    spec_path = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "servers.json"
    servers = json.loads(spec_path.read_text(encoding="utf-8"))
    results = []
    for s in servers:
        print(f"[{s['name']}] scanning...", file=sys.stderr, flush=True)
        t0 = time.time()
        if s.get("url"):
            score = scan_http(s["name"], s["url"], headers=s.get("headers"),
                              timeout=s.get("timeout", 60.0))
        else:
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
    _write_html_page(out)
    print(f"\nwrote {HERE/'results.json'}, {HERE/'SCORECARD.md'} and docs/index.html", file=sys.stderr)
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
        "| Server | Transport | Started | Tools | Schema coverage | Enforceable | Vacuous-of-declared | Error handling |",
        "|---|:--:|:--:|--:|--:|--:|--:|--:|",
    ]
    for r in rows:
        lines.append(
            f"| `{r['name']}` | {r.get('transport', 'stdio')} | {'yes' if r['handshake_ok'] else 'NO'} | "
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


def _write_html_page(out: dict) -> None:
    """Render a self-contained scorecard page for GitHub Pages (repo /docs/index.html)."""
    import html

    rows = out["servers"]
    started = [r for r in rows if r["handshake_ok"]]
    total = sum(r["n_tools"] for r in started) or 1
    with_schema = sum(r["tools_with_output_schema"] for r in started)
    vacuous = sum(r["vacuous_output_schemas"] for r in started)
    enforceable = sum(r["enforceable_output_schemas"] for r in started)
    err_clean = sum(1 for r in started if (r["error_handling_score"] or 0) == 1.0)
    no_schema = total - with_schema

    def pct(n: int) -> str:
        return f"{n / total * 100:.0f}%"

    trows = []
    for r in rows:
        started_cell = "yes" if r["handshake_ok"] else "no"
        trows.append(
            "<tr>"
            f"<td>{html.escape(r['name'])}</td>"
            f"<td class=c>{r.get('transport', 'stdio')}</td>"
            f"<td class=c>{started_cell}</td>"
            f"<td class=n>{r['n_tools'] or ''}</td>"
            f"<td class=n>{_pct(r['enforceable_rate'])}</td>"
            f"<td class=n>{_pct(r['corruption_acceptance_rate'])}</td>"
            f"<td class=n>{_pct(r['error_handling_score'])}</td>"
            "</tr>"
        )

    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MCP Reliability Scorecard — mcp-drill</title>
<meta name="description" content="A model-free reliability scan of popular Model Context Protocol servers: only {pct(enforceable)} of tools declare an output contract that rejects a corrupted response.">
<style>
  :root {{ color-scheme: light dark; --bg:#fff; --fg:#1a1a1a; --muted:#666; --line:#e5e5e5; --accent:#6b3fa0; --card:#faf9fc; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg:#14141a; --fg:#eee; --muted:#9a9aa5; --line:#2a2a33; --accent:#b79ae0; --card:#1c1c24; }} }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--fg); font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
  .wrap {{ max-width:940px; margin:0 auto; padding:2.5rem 1.25rem 4rem; }}
  h1 {{ font-size:1.9rem; margin:0 0 .3rem; letter-spacing:-.02em; }}
  .sub {{ color:var(--muted); margin:0 0 2rem; }}
  .lede {{ font-size:1.35rem; line-height:1.4; margin:0 0 2rem; }}
  .lede b {{ color:var(--accent); }}
  .tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:1rem; margin:0 0 2.5rem; }}
  .tile {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:1.1rem 1.2rem; }}
  .tile .big {{ font-size:2rem; font-weight:700; letter-spacing:-.02em; }}
  .tile .lbl {{ color:var(--muted); font-size:.85rem; margin-top:.2rem; }}
  .scroll {{ overflow-x:auto; border:1px solid var(--line); border-radius:12px; }}
  table {{ border-collapse:collapse; width:100%; font-size:.9rem; }}
  th,td {{ padding:.5rem .7rem; border-bottom:1px solid var(--line); text-align:left; white-space:nowrap; }}
  th {{ position:sticky; top:0; background:var(--card); font-weight:600; }}
  td.n,th.n {{ text-align:right; font-variant-numeric:tabular-nums; }}
  td.c,th.c {{ text-align:center; }}
  tr:last-child td {{ border-bottom:0; }}
  h2 {{ font-size:1.2rem; margin:2.5rem 0 .6rem; }}
  code {{ background:var(--card); border:1px solid var(--line); border-radius:6px; padding:.1rem .35rem; font-size:.85em; }}
  pre {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:1rem; overflow-x:auto; }}
  a {{ color:var(--accent); }}
  footer {{ color:var(--muted); font-size:.85rem; margin-top:3rem; border-top:1px solid var(--line); padding-top:1rem; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>MCP Reliability Scorecard</h1>
  <p class="sub">A model-free reliability scan of popular Model Context Protocol servers, by
    <a href="https://github.com/TimurRakhmatullin86/mcp-drill">mcp-drill</a>. Generated {out['generated']}.</p>

  <p class="lede">Across {len(started)} popular MCP servers ({total} tools), only
    <b>{pct(enforceable)} of tools declare an output contract that would reject a corrupted response.</b>
    For the rest, schema validation cannot catch a well-typed but wrong result.</p>

  <div class="tiles">
    <div class="tile"><div class="big">{pct(enforceable)}</div><div class="lbl">enforceable contract ({enforceable}/{total} tools)</div></div>
    <div class="tile"><div class="big">{pct(vacuous)}</div><div class="lbl">vacuous schema ({vacuous}/{total})</div></div>
    <div class="tile"><div class="big">{pct(no_schema)}</div><div class="lbl">no schema at all ({no_schema}/{total})</div></div>
    <div class="tile"><div class="big">{err_clean}/{len(started)}</div><div class="lbl">servers handle bad input correctly</div></div>
  </div>

  <div class="scroll">
  <table>
    <thead><tr><th>Server</th><th class=c>Transport</th><th class=c>Started</th><th class=n>Tools</th>
      <th class=n>Enforceable</th><th class=n>Vacuous</th><th class=n>Error&nbsp;handling</th></tr></thead>
    <tbody>
    {''.join(trows)}
    </tbody>
  </table>
  </div>

  <h2>What this measures (no language model involved)</h2>
  <p>Every number is a property of the server and the protocol, not of any agent. For each tool that
    declares an <code>outputSchema</code>, we build a payload that keeps the declared structure and
    types but corrupts every value, then check whether the server's own schema still validates it. A
    schema that validates the corruption is <em>vacuous</em>; one that rejects it is <em>enforceable</em>.
    We also send invalid requests to check whether the server returns a proper error.</p>

  <h2>Reproduce</h2>
  <pre>pip install "mcp-drill[scan] @ git+https://github.com/TimurRakhmatullin86/mcp-drill"
python studies/pilot/run_pilot.py studies/pilot/servers.json</pre>

  <footer>
    mcp-drill is open source (Apache-2.0). Server list, raw results, and methodology are in the
    <a href="https://github.com/TimurRakhmatullin86/mcp-drill">repository</a>.
  </footer>
</div>
</body>
</html>
"""
    docs = HERE.resolve().parents[1] / "docs"  # repo-root/docs
    docs.mkdir(exist_ok=True)
    (docs / "index.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
