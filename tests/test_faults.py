from mcp_drill import faults
from mcp_drill.faults import DROP, FaultSpec, Raw
from mcp_drill.scorecard import accepts_corruption


def _tool_response():
    return {"jsonrpc": "2.0", "id": 1,
            "result": {"content": [{"type": "text", "text": "hello world"}]}}


def test_fault_spec_parse_params():
    spec = FaultSpec.parse("latency:seconds=2,jitter=0.5")
    assert spec.name == "latency"
    assert spec.params == {"seconds": 2, "jitter": 0.5}


def test_fault_spec_parse_bare_name():
    spec = FaultSpec.parse("timeout")
    assert spec.name == "timeout" and spec.params == {}


def test_timeout_drops_response():
    inj = faults.get("timeout")(_tool_response(), {})
    assert inj.payload is DROP


def test_truncate_shortens_text():
    inj = faults.get("truncate")(_tool_response(), {"keep": 4})
    assert inj.payload["result"]["content"][0]["text"] == "hell"


def test_corrupt_replaces_text():
    inj = faults.get("corrupt")(_tool_response(), {"token": "XX"})
    assert inj.payload["result"]["content"][0]["text"] == "XX"


def test_malformed_is_raw_and_unparseable():
    import json
    inj = faults.get("malformed")(_tool_response(), {})
    assert isinstance(inj.payload, Raw)
    try:
        json.loads(str(inj.payload))
        assert False, "malformed payload should not parse"
    except json.JSONDecodeError:
        pass


def test_error_fault_builds_jsonrpc_error():
    inj = faults.get("error")(_tool_response(), {"code": -32000, "message": "boom"})
    assert inj.payload["error"]["code"] == -32000


def test_all_registered_faults_are_callable():
    for name in faults.names():
        inj = faults.get(name)(_tool_response(), {})
        assert inj is not None


def test_accepts_corruption_enforceable_vs_vacuous():
    enforceable = {"type": "object", "required": ["a"], "additionalProperties": False,
                   "properties": {"a": {"type": "string", "enum": ["x", "y"]}}}
    vacuous = {"type": "object", "required": ["a"], "properties": {"a": {"type": "string"}}}
    assert accepts_corruption(enforceable)[0] is False  # enum rejects a corrupted value
    assert accepts_corruption(vacuous)[0] is True        # type-only schema validates corruption
    assert accepts_corruption({})[0] is True             # empty schema constrains nothing


def test_accepts_corruption_numeric_bounds():
    bounded = {"type": "object", "required": ["n"],
               "properties": {"n": {"type": "integer", "minimum": 0, "maximum": 100}}}
    assert accepts_corruption(bounded)[0] is False  # -999999999 is out of range
