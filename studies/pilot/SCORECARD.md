# MCP server reliability scorecard (pilot)

Generated 2026-07-07T06:31:43Z by mcp-drill. Deterministic and model-free: every number is a
property of the server and the protocol, reproducible with `python studies/pilot/run_pilot.py`.

- Servers scanned: **31**; started cleanly: **31**
- **Only 3% of tools (7/265) declare an output contract that rejects a corrupted response.** For the rest, schema validation cannot catch a well-typed but wrong result.
- Tiers: **no schema 56%** (148/265); **vacuous schema 42%** (110/265); **enforceable 3%** (7/265)
- SDK-auto-wrapped (`x-fastmcp-wrap-result`): **10/265** tools — a vacuous default inherited from the MCP Python SDK / FastMCP
- Error handling: **30/31** servers handled every invalid-input probe correctly
- Declare output schemas that stay valid under corruption: **13/31** servers

| Server | Transport | Started | Tools | Schema coverage | Enforceable | Vacuous-of-declared | Error handling |
|---|:--:|:--:|--:|--:|--:|--:|--:|
| `everything` | stdio | yes | 13 | 8% | 0% | 100% | 100% |
| `filesystem` | stdio | yes | 14 | 100% | 7% | 93% | 100% |
| `memory` | stdio | yes | 9 | 100% | 0% | 100% | 100% |
| `sequential-thinking` | stdio | yes | 1 | 100% | 0% | 100% | 100% |
| `desktop-commander` | stdio | yes | 26 | 0% | 0% | n/a | 100% |
| `context7` | stdio | yes | 2 | 0% | 0% | n/a | 100% |
| `mcp-server-chart` | stdio | yes | 27 | 0% | 0% | n/a | 100% |
| `git-mcp-server` | stdio | yes | 28 | 100% | 18% | 82% | 100% |
| `mcp-server-commands` | stdio | yes | 1 | 0% | 0% | n/a | 100% |
| `playwright` | stdio | yes | 23 | 0% | 0% | n/a | 100% |
| `time` | stdio | yes | 2 | 0% | 0% | n/a | 100% |
| `fetch` | stdio | yes | 1 | 0% | 0% | n/a | 100% |
| `git` | stdio | yes | 12 | 0% | 0% | n/a | 100% |
| `sqlite` | stdio | yes | 6 | 0% | 0% | n/a | 67% |
| `duckduckgo` | stdio | yes | 2 | 100% | 0% | 100% | 100% |
| `calculator` | stdio | yes | 1 | 100% | 0% | 100% | 100% |
| `wikipedia` | stdio | yes | 22 | 100% | 0% | 100% | 100% |
| `arxiv` | stdio | yes | 5 | 100% | 0% | 100% | 100% |
| `taskmanager` | stdio | yes | 10 | 0% | 0% | n/a | 100% |
| `nixos` | stdio | yes | 2 | 100% | 0% | 100% | 100% |
| `pandoc` | stdio | yes | 1 | 0% | 0% | n/a | 100% |
| `youtube-transcript` | stdio | yes | 5 | 0% | 0% | n/a | 100% |
| `youtube-transcript2` | stdio | yes | 1 | 0% | 0% | n/a | 100% |
| `text-editor` | stdio | yes | 2 | 0% | 0% | n/a | 100% |
| `tree-sitter` | stdio | yes | 26 | 100% | 0% | 100% | 100% |
| `json-mcp` | stdio | yes | 2 | 0% | 0% | n/a | 100% |
| `deepwiki (remote)` | http | yes | 3 | 100% | 0% | 100% | 100% |
| `microsoft-learn (remote)` | http | yes | 3 | 67% | 0% | 100% | 100% |
| `huggingface (remote)` | http | yes | 8 | 12% | 12% | 0% | 100% |
| `gitmcp (remote)` | http | yes | 5 | 0% | 0% | n/a | 100% |
| `cloudflare-docs (remote)` | http | yes | 2 | 0% | 0% | n/a | 100% |

## Notable

- `sqlite` mishandled: `unknown_tool`=accepted
- `everything` — 100% of its declared output schemas validate a corrupted payload
- `memory` — 100% of its declared output schemas validate a corrupted payload
- `sequential-thinking` — 100% of its declared output schemas validate a corrupted payload
- `duckduckgo` — 100% of its declared output schemas validate a corrupted payload
- `calculator` — 100% of its declared output schemas validate a corrupted payload
- `wikipedia` — 100% of its declared output schemas validate a corrupted payload
- `arxiv` — 100% of its declared output schemas validate a corrupted payload (SDK-auto-wrapped)
- `nixos` — 100% of its declared output schemas validate a corrupted payload (SDK-auto-wrapped)
- `tree-sitter` — 100% of its declared output schemas validate a corrupted payload
- `deepwiki (remote)` — 100% of its declared output schemas validate a corrupted payload (SDK-auto-wrapped)
- `microsoft-learn (remote)` — 100% of its declared output schemas validate a corrupted payload

**Columns.** *Schema coverage* = share of tools declaring an `outputSchema`. *Enforceable* =
share of all tools whose declared schema rejects a corrupted (well-typed but wrong) response.
*Vacuous-of-declared* = of tools that declare a schema, the share that still validate the
corrupted payload. *Error handling* = share of invalid-input probes (unknown method, unknown
tool, missing required args) answered with a JSON-RPC error or an MCP tool error rather than a
false success, a hang, or a crash.
