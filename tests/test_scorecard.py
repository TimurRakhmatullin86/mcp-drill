import sys
from pathlib import Path

import pytest

from mcp_drill.scorecard import scan_server

FAKE = str(Path(__file__).parent / "fake_server.py")


def _scan(monkeypatch, mode):
    monkeypatch.setenv("MCP_DRILL_FAKE_MODE", mode)
    return scan_server(f"fake-{mode}", [sys.executable, FAKE], timeout=10.0)


def test_good_server_handles_bad_input(monkeypatch):
    score = _scan(monkeypatch, "good")
    assert score.handshake_ok
    assert score.protocol_version == "2025-06-18"
    assert score.n_tools == 1
    assert score.probes["unknown_method"] == "jsonrpc_error"
    assert score.probes["unknown_tool"] == "jsonrpc_error"
    assert score.probes["missing_required_args"] == "jsonrpc_error"
    assert score.error_handling_score == 1.0
    assert score.output_schema_coverage == 1.0
    assert score.enforceable_rate == 1.0  # enum-constrained schema rejects corruption
    assert score.corruption_acceptance_rate == 0.0


def test_bad_server_silently_accepts_and_is_loose(monkeypatch):
    score = _scan(monkeypatch, "bad")
    assert score.handshake_ok
    # every invalid request is answered with a success result
    assert score.probes["unknown_method"] == "accepted"
    assert score.probes["unknown_tool"] == "accepted"
    assert score.probes["missing_required_args"] == "accepted"
    assert score.error_handling_score == 0.0
    assert score.output_schema_coverage == 1.0
    assert score.enforceable_rate == 0.0  # type-only schema cannot reject corruption
    assert score.corruption_acceptance_rate == 1.0


def test_scan_of_missing_binary_reports_failure(monkeypatch):
    score = scan_server("nope", ["this-binary-does-not-exist-xyz"], timeout=5.0)
    assert score.handshake_ok is False
    assert score.notes


def test_to_dict_is_json_serializable(monkeypatch):
    import json
    score = _scan(monkeypatch, "good")
    json.dumps(score.to_dict())  # must not raise
