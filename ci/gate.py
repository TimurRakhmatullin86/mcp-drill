"""Summarise an ``mcp-drill scan --json`` result and optionally fail on a threshold.

Used by the GitHub Action; also runnable locally:

    python -m mcp_drill.cli scan --json -- npx -y some-server > s.json
    python ci/gate.py s.json --min-error-handling 1.0
"""
from __future__ import annotations

import argparse
import json
import sys


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--min-error-handling", default="")
    parser.add_argument("--min-output-schema", default="")
    args = parser.parse_args()

    with open(args.path, encoding="utf-8") as fh:
        s = json.load(fh)

    info = s.get("server_info") or {}
    name = info.get("name") or s.get("name")
    print(f"### mcp-drill scan — {name}\n")
    if not s.get("handshake_ok"):
        print("Server failed to start / initialize.")
        for note in s.get("notes") or []:
            print(f"- {note}")
        return 1
    print(f"- Tools: **{s.get('n_tools')}**")
    print(f"- Output-schema coverage: **{_pct(s.get('output_schema_coverage'))}**")
    print(f"- Enforceable output contracts: **{_pct(s.get('enforceable_rate'))}**")
    print(f"- Vacuous (of declared): **{_pct(s.get('corruption_acceptance_rate'))}**")
    print(f"- Error handling: **{_pct(s.get('error_handling_score'))}**")
    for probe, verdict in (s.get("probes") or {}).items():
        print(f"  - `{probe}`: {verdict}")

    failures: list[str] = []
    _check(failures, "error handling", s.get("error_handling_score"), args.min_error_handling)
    _check(failures, "output-schema coverage", s.get("output_schema_coverage"), args.min_output_schema)
    if failures:
        print("\n**Gate failed:**")
        for f in failures:
            print(f"- {f}")
        return 1
    return 0


def _check(failures: list[str], label: str, value: float | None, threshold: str) -> None:
    if not threshold:
        return
    minimum = float(threshold)
    actual = value or 0.0
    if actual < minimum:
        failures.append(f"{label} {_pct(actual)} is below the required {_pct(minimum)}")


if __name__ == "__main__":
    raise SystemExit(main())
