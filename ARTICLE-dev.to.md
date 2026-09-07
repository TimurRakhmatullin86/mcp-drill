# I tested 31 MCP servers for contract compliance. Only 3% passed.

**TL;DR:** MCP has `outputSchema` so agents can validate tool results. But does the schema actually *reject* a wrong answer? I built `mcp-drill` — a fault-injection harness that speaks MCP — and scanned 31 popular servers (265 tools) including **Microsoft Learn, Hugging Face, Cloudflare, DeepWiki**. Result: **only 3% declare a contract that would reject a corrupted response.** 56% declare *nothing*, 42% declare a schema that happily validates garbage. Your agent cannot tell a bad result from a good one.

- 🔗 Live scorecard: https://timurrakhmatullin86.github.io/mcp-drill/
- 📦 `pip install mcp-drill[scan]` · `uvx mcp-drill scan -- npx -y @modelcontextprotocol/server-filesystem /tmp` · GitHub Action + badge
- 🆚 How this differs from security scanning: https://timurrakhmatullin86.github.io/mcp-drill/vs-mcp-scan/

---

## Why I built this

MCP is JSON-RPC over stdio / Streamable HTTP with bidirectional notifications. Normal HTTP chaos tools don't speak it. And even when you test an MCP server, you usually test *your* agent, not whether the *server's contract* protects you.

Real failures I kept hitting:

- A tool returns a well-formed but truncated payload mid-stream — agent acts on half a JSON.
- A `fetch` tool returns `{"result": "ok"}` with status 200 even when the tool name is wrong — how does the agent know it failed?
- A server declares `outputSchema: {type: "object"}` — great, it validates *any* object, including a corrupted one. Zero protection.

I wanted one command to answer: **if I corrupt the response but keep its type, does your schema catch it?** And separately: **if I send you garbage input, do you tell me with a proper error?**

So I built `mcp-drill`:

- 🧪 **Fault injection proxy** — `mcp-drill wrap --faults timeout,corrupt,truncate,malformed -- npx ...` — sits between client and server, perturbs responses deterministically (seed-able).
- 📊 **Model-free scorecard** — `mcp-drill scan -- npx ...` or `mcp-drill scan --url https://...` — no LLM, deterministic, reproducible. Every number is a property of the server.

## What I measured (no LLM involved)

For each server, `mcp-drill` does the MCP handshake, lists tools, then runs fixed probes:

1. **Output-contract coverage** — % of tools that declare an `outputSchema` at all.
2. **Output-contract enforceability** — of those that declare one, % whose schema *rejects* a corrupted-but-well-typed payload. Corruption: keep structure + type, replace every leaf with `mcp-drill-corruption` / `-999999999` / out-of-range. If it still validates → **vacuous**. If it rejects → **enforceable**. This is an *outcome* test, not style policing.
3. **Error conformance** — 3 probes: unknown method, unknown tool, missing required args. Classified as `jsonrpc_error` / `tool_error` (good) vs `accepted` / `timeout` / `crash` (bad).

Repro: `pip install -e ".[scan]" && python studies/pilot/run_pilot.py studies/pilot/servers.json` — commits server list + raw `results.json`.

Full methodology: https://github.com/TimurRakhmatullin86/mcp-drill/blob/main/METHODOLOGY.md

## The headline number

**31 servers, 265 tools — 3% enforceable.**

| Tier | Share | Count | Meaning |
|------|-------|-------|---------|
| No schema | **56%** | 148/265 | Nothing to validate against |
| Vacuous schema | **42%** | 110/265 | Corrupted payload still validates — zero protection |
| Enforceable | **3%** | 7/265 | Schema rejects the corrupted payload |

- SDK-auto-wrapped (`x-fastmcp-wrap-result`): 10 tools — the default from the dominant MCP Python SDK (FastMCP) wraps a return as `{"result": string}` and calls it a contract. It's vacuous by construction.
- Error handling: **30/31 servers** handle bad input correctly — the *error* path is healthy. The *success* path is not.
- The number is stable: 3% at 18 servers → 3% at 22 → 2% at 26 → 3% at 31 (including remote marquee servers). Not a small-sample artefact.

![Scorecard tiles — 3% enforceable, 42% vacuous, 56% no schema](https://timurrakhmatullin86.github.io/mcp-drill/)

Some highlights from the table (full: https://timurrakhmatullin86.github.io/mcp-drill/):

- `everything` (reference server): 13 tools, 100% vacuous
- `filesystem` (14 tools): 7% enforceable — best of the stdio set
- `git-mcp-server` (28 tools): 18% enforceable — the outlier on the good side
- `microsoft-learn` (remote), `deepwiki` (remote), `cloudflare-docs` (remote): 0% enforceable — name-brand doesn't help
- `sqlite`: the one error-handling failure (`unknown_tool` → success) — likely a republished copy of the archived reference server, not systemic

## Why this matters for agents

Agents increasingly act on a tool result without a human in the loop: tool A's output becomes tool B's input. The only automatic guard is: *did the transport succeed + did the payload match `outputSchema`?* If the schema is vacuous, nothing guards a well-typed but wrong result, and the agent proceeds on bad data.

This is not what security scanners (like `mcp-scan`) catch. Those ask “can this server be abused to do something evil?” We ask “can this server be *trusted* when it returns a result?” See the VS page: https://timurrakhmatullin86.github.io/mcp-drill/vs-mcp-scan/

And coverage is a vanity metric here. Auto-generated schemas (FastMCP infers from return type hints) raise coverage toward 100% while enforceability stays near 0% — a vacuous default inherited by every server that doesn't override it. The gap widens as tooling improves, unless schemas add value-level constraints (`enum`, `pattern`, `format`, bounds).

## Try it on your own server (1 command)

```bash
# install
pip install "mcp-drill[scan]"        # or: pipx install mcp-drill[scan]
# or without install
uvx mcp-drill scan -- --help

# local stdio server
mcp-drill scan -- npx -y @modelcontextprotocol/server-filesystem /tmp
mcp-drill scan --json -- npx -y @modelcontextprotocol/server-filesystem /tmp > mcp-drill.json

# remote Streamable HTTP (with auth if needed)
mcp-drill scan --url https://mcp.deepwiki.com/mcp
mcp-drill scan --header "Authorization: Bearer $TOKEN" --url https://your-mcp.example.com/mcp

# badge (shields.io endpoint)
mcp-drill scan --badge --url https://mcp.deepwiki.com/mcp > badge.json

# fault injection proxy (deterministic, seed-able)
mcp-drill wrap --faults timeout,truncate -- npx -y @modelcontextprotocol/server-everything
mcp-drill wrap --faults corrupt --seed 42 -- npx -y @modelcontextprotocol/server-filesystem /tmp
mcp-drill faults  # list all: timeout, latency, truncate, corrupt, malformed, error, drop, oversized...
```

Gate in CI — GitHub Action (no LLM, no API key):

```yaml
- uses: TimurRakhmatullin86/mcp-drill@v0
  with:
    server: 'npx -y @modelcontextprotocol/server-filesystem /tmp'
    min-error-handling: '0.9'
    # min-output-schema: '0.1'  # uncomment to enforce contract hygiene
```

## What to do about it

- **If you build an MCP server:** declare `outputSchema`s that constrain *values*, not just shapes. Add `enum` / `pattern` / `format` / numeric bounds where semantics allow. `additionalProperties: false` helps, but alone it's not enough — a corrupted string is still a string. Test with `mcp-drill scan --json` in CI and gate on it.
- **If you consume MCP tools:** don't rely on `outputSchema` presence as safety. Validate semantically downstream or use `mcp-drill wrap` to exercise your agent's failure paths before prod.
- **If you review MCP proposals:** coverage will trend to 100% as generators spread. Ask for *enforceability*.

Repo: https://github.com/TimurRakhmatullin86/mcp-drill — Apache-2.0, telemetry off, 14 tests, Python 3.10+. Paper draft in `own/mcp-drill-internal/paper/DRAFT.md` (target arXiv cs.SE). PRs and issues welcome — especially if your server scores differently and you think the harness is wrong (repro is in the repo).

If you found this useful, a ⭐ on GitHub helps others find it, and running `mcp-drill scan` on your server and opening an issue with the JSON is even better.

---

*Method is model-free and deterministic — every number is a property of the server, not of whatever agent called it. The tool is the methodology, and it is released.*

