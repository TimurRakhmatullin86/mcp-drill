# mcp-drill

[![MCP output contracts](https://img.shields.io/endpoint?url=https://timurrakhmatullin86.github.io/mcp-drill/badge.json)](https://timurrakhmatullin86.github.io/mcp-drill/)
[![CI](https://github.com/TimurRakhmatullin86/mcp-drill/actions/workflows/tests.yml/badge.svg)](https://github.com/TimurRakhmatullin86/mcp-drill/actions)

**Fault injection and reliability testing for MCP servers and AI agents.**
Wrap any Model Context Protocol server in one command; inject timeouts, malformed JSON-RPC,
truncated and corrupted-but-valid tool outputs; measure whether the server degrades cleanly —
and whether your agent *notices* or silently acts on the garbage.

```bash
uvx mcp-drill wrap --faults timeout,corrupt -- npx -y @modelcontextprotocol/server-filesystem /tmp
```

MCP is JSON-RPC over stdio/SSE with bidirectional notifications, so ordinary HTTP fault-injectors
and chaos tools don't fit. `mcp-drill` speaks MCP: it sits transparently between an MCP client and
a backend server and perturbs the traffic, so you can test failure paths in CI without a live LLM.

> **Finding:** across 31 popular MCP servers (including Microsoft Learn, Hugging Face, Cloudflare and
> DeepWiki), only **3% of tools declare an output contract that would reject a corrupted response**.
> See the [live scorecard](https://timurrakhmatullin86.github.io/mcp-drill/).

## Why

Real MCP deployments fail in ways integration tests never cover: a tool times out, a server
returns a well-formed-but-wrong payload, a response is truncated mid-stream. Most agents were
never exercised against these paths. `mcp-drill` makes them reproducible:

- 🧪 **Fault injection** — deterministically inject timeouts, malformed/oversized/truncated
  responses, corrupted-but-schema-valid payloads, dropped tools, and latency.
- 🎬 **CI-first** — a CLI and a GitHub Action; no live model or API keys required in the loop.
- 📊 **Reliability scorecard** — a model-free scan that grades how a server responds to bad
  input and how machine-checkable its tool output contracts are.

## Install

```bash
pip install mcp-drill[scan]        # or: pipx install mcp-drill[scan]
uvx mcp-drill scan -- --help       # no install, run once
npm i -g mcp-drill                 # shim: prints version + points to PyPI
```

[![PyPI](https://img.shields.io/pypi/v/mcp-drill)](https://pypi.org/project/mcp-drill/)
[![Downloads](https://img.shields.io/pypi/dm/mcp-drill)](https://pypistats.org/packages/mcp-drill)

## Quickstart

```bash
# wrap a server and inject faults into its responses
mcp-drill wrap --faults timeout,truncate -- npx -y @modelcontextprotocol/server-everything

# score a local (stdio) server's fault handling and output-schema hygiene (no LLM involved)
mcp-drill scan -- npx -y @modelcontextprotocol/server-filesystem /tmp

# score a remote server over Streamable HTTP (add --header for auth if needed)
mcp-drill scan --url https://mcp.deepwiki.com/mcp

# emit a shields.io badge for a server's output-contract grade
mcp-drill scan --badge --url https://mcp.deepwiki.com/mcp
```

## What it measures (model-free)

The `scan` command is deterministic and involves no language model, so its numbers are properties
of the server and the protocol — not of whichever agent happens to call it:

1. **Error conformance** — on invalid requests (unknown method, unknown tool, missing required
   arguments), does the server return a spec-compliant JSON-RPC error, a proper tool error, or
   does it hang / crash / answer as if nothing was wrong?
2. **Output-contract coverage** — what fraction of a server's tools declare a machine-checkable
   `outputSchema` at all? Tools without one give downstream validators nothing to check.
3. **Output-contract enforceability** — of the tools that declare an `outputSchema`, how many would
   actually *reject* a corrupted (well-typed but wrong) response? Many declared schemas validate
   shape only, so a corrupted payload still passes the server's own contract.

## Status

Early development. The proxy/injector core is pure-stdlib; schema scoring uses `jsonschema`
(the `scan` extra). Telemetry is **off** — the tool never phones home.
See [vs mcp-scan](https://timurrakhmatullin86.github.io/mcp-drill/vs-mcp-scan/) for how
`mcp-drill` (contract compliance) differs from `mcp-scan` (security).

## License

Apache-2.0 (see `LICENSE`).
