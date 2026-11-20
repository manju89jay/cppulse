"""The actual MCP public consumer must preserve the public rule metadata view."""
from pathlib import Path

from cppulse.tooling import load_rule_registry
from cppulse.run_store import RunStore
from test_mcp_server import call, init, session, value


def test_actual_stdio_rule_metadata_does_not_expose_native_bindings(tmp_path: Path) -> None:
    """Read every rule, keeping private C++ construction metadata out of MCP."""
    public = load_rule_registry()["rules"]
    raw = load_rule_registry(include_native_bindings=True)["rules"]
    assert len(public) == len(raw) == 22
    assert all("x-cppulse-native" in row["configuration_schema"] for row in raw)
    requests = [init(), *[call("documentation", {"kind": "rule", "id": row["id"]}, index)
                         for index, row in enumerate(public, start=2)]]
    store = tmp_path / "store"
    RunStore(store)
    before = {p.relative_to(store): p.read_bytes() for p in store.rglob("*") if p.is_file()}
    replies = session(store, requests)
    assert len(replies) == len(requests)
    documents = [value(response) for response in replies[1:]]
    assert all(row["origin"] == "packaged-rule-registry" for row in documents)
    observed = [row["document"] for row in documents]
    assert [row["id"] for row in observed] == [row["id"] for row in public]
    leaking = [row["id"] for row in observed
               if "x-cppulse-native" in row["configuration_schema"]]
    assert not leaking, f"Public MCP exposes private native metadata for: {leaking}"
    assert observed == public
    assert before == {p.relative_to(store): p.read_bytes()
                      for p in store.rglob("*") if p.is_file()}
