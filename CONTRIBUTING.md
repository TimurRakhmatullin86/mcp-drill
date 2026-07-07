# Contributing to mcp-drill

Thanks for your interest. mcp-drill is a small, focused tool; contributions that keep it that way
are the easiest to merge.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,http,scan]"
pytest
```

The proxy/injector core is pure-stdlib. `jsonschema` is used only for schema scoring (the `scan`
extra) and `httpx` only for the Streamable-HTTP transport (the `http` extra); keep the core free of
required third-party dependencies.

## Guidelines

- Add a test for any behaviour change; keep the suite deterministic (no live network in unit tests —
  use the fake server fixture).
- Match the existing style; comments in English, explaining *why* rather than *what*.
- New fault types go in `faults.py` with a one-line registration; new scan checks go in `scorecard.py`
  and must stay **model-free** (no LLM in the loop) and deterministic.
- If you add a server to the pilot list, pin how it is launched and prefer servers that start without
  credentials so the study stays reproducible.

## Reporting reliability findings about other servers

See `SECURITY.md`: report concrete issues to the server's maintainers first, publish grades and
methodology, and never frame a finding as a gotcha.

## License

By contributing you agree that your contributions are licensed under the Apache License 2.0.
