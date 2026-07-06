"""Command-line entry point: `mcp-drill wrap|scan|faults|version`."""
from __future__ import annotations

import argparse
import json
import sys

from . import __version__, faults
from .proxy import FaultProxy, build_specs
from .scorecard import ServerScore, scan_server


def _split_server_command(argv: list[str]) -> tuple[list[str], list[str]]:
    """Everything after a standalone ``--`` is the server command to launch."""
    if "--" in argv:
        i = argv.index("--")
        return argv[:i], argv[i + 1:]
    return argv, []


def _parse_fault_list(spec: str) -> list[str]:
    spec = spec.strip()
    if not spec:
        return []
    parts = spec.split(";") if ":" in spec else spec.split(",")
    return [p.strip() for p in parts if p.strip()]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcp-drill",
        description="Fault injection and reliability scoring for MCP servers.",
        epilog="Put the server command after `--`, e.g. mcp-drill scan -- npx -y some-mcp-server",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    wrap = sub.add_parser("wrap", help="proxy a server and inject faults into its responses")
    wrap.add_argument("--faults", default="", metavar="LIST",
                      help="faults to inject, e.g. 'timeout,corrupt' or 'latency:seconds=2;truncate'")
    wrap.add_argument("--only", default="tools/call", metavar="METHODS",
                      help="comma-separated methods whose responses may be faulted")
    wrap.add_argument("-p", "--probability", type=float, default=1.0,
                      help="probability [0..1] that a targeted response is faulted")
    wrap.add_argument("--seed", type=int, default=None, help="RNG seed for reproducible runs")

    scan = sub.add_parser("scan", help="score a server's fault handling and schema hygiene (no LLM)")
    scan.add_argument("--json", action="store_true", help="emit the full score as JSON")
    scan.add_argument("--timeout", type=float, default=20.0, help="per-request timeout in seconds")
    scan.add_argument("--name", default=None, help="label for the server in the report")

    sub.add_parser("faults", help="list the available fault types")
    sub.add_parser("version", help="print the version")
    return parser


def _print_report(score: ServerScore) -> None:
    info = score.server_info or {}
    label = info.get("name") or score.name
    print(f"mcp-drill scan — {label} {info.get('version', '')}".rstrip())
    print(f"  handshake        : {'ok' if score.handshake_ok else 'FAILED'}"
          + (f" (protocol {score.protocol_version})" if score.protocol_version else ""))
    if not score.handshake_ok:
        for note in score.notes:
            print(f"  note             : {note}")
        return
    cov = score.output_schema_coverage
    enf = score.enforceable_rate
    ca = score.corruption_acceptance_rate
    ehs = score.error_handling_score
    print(f"  tools            : {score.n_tools}")
    print(f"  output-schema    : {_pct(cov)} of tools declare one"
          f" ({score.tools_with_output_schema}/{score.n_tools})")
    print(f"  enforceable      : {_pct(enf)} of tools declare a schema that rejects a corrupted"
          f" response ({score.enforceable_output_schemas}/{score.n_tools})")
    if score.tools_with_output_schema:
        print(f"  vacuous schemas  : {_pct(ca)} of declared schemas still validate a corrupted"
              f" payload ({score.vacuous_output_schemas}/{score.tools_with_output_schema})")
    if score.fastmcp_wrapped_tools:
        print(f"  fastmcp-wrapped  : {score.fastmcp_wrapped_tools} tool(s) carry x-fastmcp-wrap-result")
    print(f"  error handling   : {_pct(ehs)} of bad-input probes handled cleanly")
    for probe, verdict in score.probes.items():
        print(f"      - {probe:<22}: {verdict}")
    for note in score.notes:
        print(f"  note             : {note}")


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    argv, server_cmd = _split_server_command(argv)
    args = _build_parser().parse_args(argv)

    if args.cmd == "version":
        print(__version__)
        return 0
    if args.cmd == "faults":
        print("\n".join(faults.names()))
        return 0

    if not server_cmd:
        print("error: provide the server command after `--`", file=sys.stderr)
        return 2

    if args.cmd == "wrap":
        specs = build_specs(_parse_fault_list(args.faults))
        proxy = FaultProxy(
            server_cmd,
            specs,
            target_methods=tuple(m.strip() for m in args.only.split(",") if m.strip()),
            probability=args.probability,
            seed=args.seed,
        )
        return proxy.run()

    if args.cmd == "scan":
        score = scan_server(args.name or server_cmd[-1], server_cmd, timeout=args.timeout)
        if args.json:
            print(json.dumps(score.to_dict(), indent=2, ensure_ascii=False))
        else:
            _print_report(score)
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
