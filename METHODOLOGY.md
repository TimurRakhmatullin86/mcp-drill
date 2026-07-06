# Methodology — MCP server reliability scorecard

This document specifies exactly how `mcp-drill scan` measures a server, so that every published
number is reproducible and defensible. The guiding constraint: **measure only properties of the
server and the protocol, never the behaviour of a language model.** No LLM is in the loop; the same
inputs produce the same outputs on every run.

## What is measured

For each server, `mcp-drill` performs the standard MCP initialize handshake over stdio, requests
`tools/list`, and then runs a fixed battery of deterministic probes. Three axes are reported.

### 1. Output-contract coverage
The share of a server's tools that declare an `outputSchema`. MCP allows a tool to declare a JSON
Schema for its structured output; without one, a client has **nothing to machine-check** a tool
result against. Coverage is `tools_with_outputSchema / total_tools`.

*Framing note:* `outputSchema` is optional in the MCP specification. A 0% score is therefore a
**contract-hygiene observation, not a spec violation.** The claim we make is precisely: "this tool
provides no machine-checkable output contract," which is verifiable and neutral — not "this tool is
broken."

### 2. Output-contract enforceability (corruption acceptance)
Of the tools that declare an `outputSchema`, the share whose schema would actually **reject a
corrupted response**. This is an *outcome* test, not a style judgement about how the schema is
written. Operationalised deterministically:

1. From the declared schema, build a "corrupted" instance that preserves the schema's declared
   structure and types but replaces every leaf value with a sentinel wrong value (a nonsense string,
   an out-of-range number, a negated boolean). A plausible content corruption keeps the type — a
   wrong URL is still a string, a wrong result is still a number — so only a **value-level**
   constraint can catch it.
2. Validate the corrupted instance against the schema (JSON Schema, via `jsonschema`; when the
   validator is unavailable, fall back to checking whether the schema declares any value-level
   constraint at all — `enum`, `const`, `pattern`, `format`, numeric bounds, length/size bounds).
3. **Vacuous** = the corrupted instance still validates (the contract cannot detect the wrong
   response). **Enforceable** = the schema rejects it (an `enum`/`const`/`pattern`/`format`/bound
   caught the corruption).

Tools fall into three tiers: **no schema** (nothing to validate against), **vacuous schema**
(validates a corrupted response — e.g. a `{ "result": string }` wrapper that type-checks a single
string and describes none of the actual content), and **enforceable schema**. We also flag the
`x-fastmcp-wrap-result` marker, which deterministically identifies output schemas auto-wrapped by the
MCP Python SDK / FastMCP — a vacuous default inherited by any server that does not override it.

*Framing note:* the claim is an outcome — "the declared schema validates a payload we corrupted, so
it cannot detect that corruption" — never "the schema is authored in a bad style." Absence of a
schema is likewise reported as absence of a machine-checkable contract, not as a spec violation.

### 3. Error conformance
How the server answers deliberately invalid requests. Three probes, each classified independently:

| Probe | Request | Handled (good) | Mishandled (bad) |
|---|---|---|---|
| `unknown_method` | a request for a method that does not exist | JSON-RPC error (`-32601`) | success result / hang / crash |
| `unknown_tool` | `tools/call` with a non-existent tool name | JSON-RPC error **or** `result.isError=true` | success result / hang / crash |
| `missing_required_args` | `tools/call` on a real tool with required args omitted | JSON-RPC error **or** `result.isError=true` | success result / hang / crash |

Classification is mechanical:
- **`jsonrpc_error`** — the response carries a top-level `error` object → *handled*.
- **`tool_error`** — the response is a normal result with `isError: true` (the MCP tool-error
  convention) → *handled*.
- **`accepted`** — the server returned an ordinary success result to an invalid request → *mishandled*
  (it silently accepted bad input).
- **`timeout`** — no response arrived within the per-request budget → *mishandled* (the server hung).
- **`crash`** — the server process exited or closed stdout → *mishandled*.
- **`skipped`** — the probe was not applicable (e.g. no tool declares required arguments); excluded
  from the score, not counted as a pass.

`error_handling_score = handled / (handled + mishandled)`, over the applicable probes.

## Reproducibility

```bash
pip install -e ".[scan]"
python studies/pilot/run_pilot.py studies/pilot/servers.json
```

`results.json` records, per server, the negotiated protocol version, `serverInfo`, tool count, the
raw per-probe verdicts, the tool version, and whether a JSON Schema validator was active. The server
list, versions, and timestamps are committed alongside the scorecard so any third party can re-run
the exact study.

## Threats to validity (read before citing any number)

1. **Server selection.** Results describe the specific servers scanned, at their scanned versions,
   on the scanned date. A scorecard is only as representative as its list; the list is published in
   full. First-party/reference servers are typically well-behaved on error handling — a fragility
   signal there is more likely to come from the long tail of community servers, which must be
   sampled explicitly rather than assumed.
2. **Version drift.** Servers are moving targets. Every result is pinned to a resolved version and a
   date; re-runs are expected to differ as servers improve.
3. **`outputSchema` is optional.** See the framing note above — absence is reported as absence of a
   machine-checkable contract, never as a defect.
4. **Looseness heuristic.** The check targets the most common and most consequential looseness
   (unrestricted additional properties on object schemas). It does not exhaustively model every way a
   schema can be permissive; it under-counts rather than over-claims.
5. **Transport scope.** The current harness covers the stdio transport. Streamable HTTP / SSE servers
   are out of scope for this edition and are marked as not-scanned rather than scored.
6. **What this deliberately does NOT measure.** Whether an *agent* notices a fault is a property of
   the model and the agent scaffold, not of the server, so it is excluded from the scorecard on
   purpose. Any agent-facing experiment is reported separately and never mixed into these numbers.

## Ethics

Findings about third-party servers follow coordinated disclosure (see `SECURITY.md`): concrete,
reproducible issues go to maintainers first, aggregate grades are published second, and the framing
is "grade and fix," never "gotcha." The aim is a more reliable ecosystem.
