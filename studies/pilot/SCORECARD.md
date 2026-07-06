# MCP server reliability scorecard (pilot)

Generated 2026-07-06T16:43:34Z by mcp-drill. Deterministic and model-free: every number is a
property of the server and the protocol, reproducible with `python studies/pilot/run_pilot.py`.

- Servers scanned: **30**; started cleanly: **26**
- **Only 2% of tools (6/244) declare an output contract that rejects a corrupted response.** For the rest, schema validation cannot catch a well-typed but wrong result.
- Tiers: **no schema 55%** (133/244); **vacuous schema 43%** (105/244); **enforceable 2%** (6/244)
- SDK-auto-wrapped (`x-fastmcp-wrap-result`): **7/244** tools — a vacuous default inherited from the MCP Python SDK / FastMCP
- Error handling: **25/26** servers handled every invalid-input probe correctly
- Declare output schemas that stay valid under corruption: **11/26** servers

| Server | Started | Tools | Schema coverage | Enforceable | Vacuous-of-declared | Error handling |
|---|:--:|--:|--:|--:|--:|--:|
| `everything` | yes | 13 | 8% | 0% | 100% | 100% |
| `filesystem` | yes | 14 | 100% | 7% | 93% | 100% |
| `memory` | yes | 9 | 100% | 0% | 100% | 100% |
| `sequential-thinking` | yes | 1 | 100% | 0% | 100% | 100% |
| `desktop-commander` | yes | 26 | 0% | 0% | n/a | 100% |
| `context7` | yes | 2 | 0% | 0% | n/a | 100% |
| `mcp-server-chart` | yes | 27 | 0% | 0% | n/a | 100% |
| `git-mcp-server` | yes | 28 | 100% | 18% | 82% | 100% |
| `mcp-server-commands` | yes | 1 | 0% | 0% | n/a | 100% |
| `playwright` | yes | 23 | 0% | 0% | n/a | 100% |
| `time` | yes | 2 | 0% | 0% | n/a | 100% |
| `fetch` | yes | 1 | 0% | 0% | n/a | 100% |
| `git` | yes | 12 | 0% | 0% | n/a | 100% |
| `sqlite` | yes | 6 | 0% | 0% | n/a | 67% |
| `duckduckgo` | yes | 2 | 100% | 0% | 100% | 100% |
| `calculator` | yes | 1 | 100% | 0% | 100% | 100% |
| `wikipedia` | yes | 22 | 100% | 0% | 100% | 100% |
| `arxiv` | yes | 5 | 100% | 0% | 100% | 100% |
| `taskmanager` | yes | 10 | 0% | 0% | n/a | 100% |
| `datetime` | NO |  | n/a | n/a | n/a | n/a |
| `nixos` | yes | 2 | 100% | 0% | 100% | 100% |
| `pandoc` | yes | 1 | 0% | 0% | n/a | 100% |
| `pubmed` | NO |  | n/a | n/a | n/a | n/a |
| `youtube-transcript` | yes | 5 | 0% | 0% | n/a | 100% |
| `hackernews` | NO |  | n/a | n/a | n/a | n/a |
| `youtube-transcript2` | yes | 1 | 0% | 0% | n/a | 100% |
| `text-editor` | yes | 2 | 0% | 0% | n/a | 100% |
| `tree-sitter` | yes | 26 | 100% | 0% | 100% | 100% |
| `requests` | NO |  | n/a | n/a | n/a | n/a |
| `json-mcp` | yes | 2 | 0% | 0% | n/a | 100% |

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

**Columns.** *Schema coverage* = share of tools declaring an `outputSchema`. *Enforceable* =
share of all tools whose declared schema rejects a corrupted (well-typed but wrong) response.
*Vacuous-of-declared* = of tools that declare a schema, the share that still validate the
corrupted payload. *Error handling* = share of invalid-input probes (unknown method, unknown
tool, missing required args) answered with a JSON-RPC error or an MCP tool error rather than a
false success, a hang, or a crash.
