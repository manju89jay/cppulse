"""Public configuration effects and retained configuration across reader surfaces."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess

import pytest

from cppulse.cli import main
from cppulse.config import effective_config
from cppulse.contracts import validate
from cppulse.errors import ContractError
from cppulse.mcp_server import Reader
from cppulse.presentation import build_snapshot_view, render_snapshot_html
from cppulse.rulesets import bind_collection_ruleset, clang_tidy_arguments, resolve_ruleset
from cppulse.run_store import RunStore
from cppulse.workflows import collect_request
from test_rulesets import pack


def test_public_config_native_output_and_cli_precedence(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    selected = pack(tmp_path / "review.json", native={"rules": {"CPP-CX-001": {"warning_threshold": 20}}})
    target = tmp_path / "native.json"
    assert main(["config", "--repo", str(tmp_path), "--ruleset", str(selected),
                 "--rule-option", "CPP-CX-001.warning_threshold=2", "--profile", "safety-critical",
                 "--native-output", str(target)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert json.loads(target.read_bytes()) == result["settings"]
    assert json.loads(target.with_name("native.json.identity.json").read_bytes()) == result
    assert result["settings"]["rules"]["CPP-CX-001"]["warning_threshold"] == 2
    assert result["settings"]["profile"] == "safety-critical"
    assert main(["config", "--repo", str(tmp_path), "--native-output", str(target)]) == 2


def test_predictor_profile_override_retains_command_origin_and_rejects_wrong_sidecar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import cppulse.predictor.main as predictor
    from cppulse.identities import digest_json

    (tmp_path / ".cppulserc.json").write_text('{"profile":"safety-critical"}')
    selected = effective_config(tmp_path, tmp_path / "out", ruleset=pack(tmp_path / "review.json"))
    assert selected.ruleset["origins"]["native.profile"] == "config"
    native = tmp_path / "native.json"
    native.write_text(json.dumps(selected.settings))
    sidecar = native.with_name(native.name + ".identity.json")
    sidecar.write_text(json.dumps(selected.as_dict()))
    output = tmp_path / "out"
    output.mkdir()
    calls = []
    monkeypatch.setattr(predictor, "run", lambda **kw: calls.append(kw))
    monkeypatch.setattr(sys, "argv", ["predictor", "--input", str(tmp_path), "--output", str(output),
                                     "--config", str(native), "--profile", "default"])
    predictor.main()
    retained = json.loads((output / "effective_config.json").read_bytes())
    assert calls[0]["profile"] == "default"
    assert retained["profile_source"] == "command"
    identity = retained["ruleset"]
    assert identity["origins"]["native.profile"] == "command"
    assert identity["effective_native"]["profile"] == "default"
    assert identity["digest"] == digest_json({k: v for k, v in identity.items() if k != "digest"})
    broken = selected.as_dict()
    broken["settings"]["max_file_bytes"] = 1
    sidecar.write_text(json.dumps(broken))
    with pytest.raises(ContractError, match="sidecar"):
        predictor.main()
    assert len(calls) == 1, "Conflicting retained identity fails before prediction"


@pytest.mark.parametrize("mode", ["legacy", "bounded"])
def test_real_native_pack_selection_and_historical_readers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    """Same actual native effect in both modes; later live packs cannot rewrite it."""
    assert os.environ.get("CPPULSE_ANALYZER"), "Exact native binary is required for this acceptance gate"
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.cpp").write_text("int value(int n) { if(n) return 1; return 0; }\n")
    selected = pack(repo / "review.json", native={"select": ["CPP-CX-001"], "rules": {
        "CPP-CX-001": {"warning_threshold": 0, "error_threshold": 100}}})
    output = tmp_path / "out"
    args = ["analyze", "--repo", str(repo), "--ruleset", str(selected),
            "--execution", mode, "--no-history", "--format", "json", "--output", str(output)]
    if mode == "bounded":
        args += ["--work-directory", str(tmp_path / "persistent")]
    status = main(args)
    assert status in {0, 3}, "Missing/failed producer is not a successful configured run"
    raw = json.loads((output / "findings.json").read_bytes())
    assert len(raw["findings"]) == 1
    assert raw["findings"][0]["rule_id"] == "CPP-CX-001"
    store = RunStore.open_existing(output)
    snapshot = store.resolve_latest_attempt()
    view = build_snapshot_view(snapshot)
    configuration = view["configuration"]
    assert configuration is not None and view["assessment"] is None
    original_digest = configuration["document"]["ruleset"]["digest"]
    assert configuration["document"]["settings"]["rules"]["CPP-MEM-001"]["enabled"] is False
    assert "Selected retained configuration" in render_snapshot_html(view)
    # Live changes affect a future invocation, never a pinned historical reader.
    selected.write_text(selected.read_text() + "\n")
    changed = effective_config(repo, output, ruleset=selected)
    assert changed.ruleset["digest"] != original_digest
    assert build_snapshot_view(snapshot)["configuration"] == configuration
    pin = {"run_id": snapshot.run_id, "manifest_sha256": snapshot.manifest_sha256}
    assert Reader(output).call("run_status", pin)["configuration"] == configuration
    from fastapi.testclient import TestClient
    from cppulse.report_engine.api import app
    monkeypatch.setenv("DATA_DIR", str(output))
    with TestClient(app) as client:
        response = client.get("/api/v1/view", params=pin)
        assert response.status_code == 200, response.text
        assert response.json()["configuration"] == configuration
    if mode == "bounded":
        pointer = tmp_path / "persistent/latest_execution.json"
        before = json.loads(pointer.read_bytes())
        assert main([*args, "--resume"]) in {0, 3}
        after = json.loads(pointer.read_bytes())
        assert after["signature"] != before["signature"]
        assert after["attempt"] != before["attempt"], "Changed pack identity cannot reuse the earlier execution receipts"
    broken = deepcopy(view)
    broken["configuration"]["document"]["settings"]["profile"] = "forged"
    with pytest.raises(ContractError):
        validate("snapshot_view", broken)


def _pack_request(tmp_path: Path, case_id: str) -> tuple[dict, Path]:
    from test_clang_tidy19_families import _live_request, CASES
    tool = Path(os.environ["CPPULSE_TIDY19_TOOL"]).resolve(strict=True)
    case = next(c for c in CASES["cases"] if c["id"] == case_id)
    request = _live_request(tmp_path, case, tool)
    options = {}
    for key, value in case["options"].items():
        name = key.removeprefix(case["check"] + ".")
        options[name] = value.split(";") if isinstance(value, str) and value else [] if value == "" else value
    if case["check"] == "bugprone-dangling-handle":
        options["HandleClasses"] = ["std::basic_string_view", "std::experimental::basic_string_view"]
    if case["check"] == "bugprone-unused-return-value":
        options.setdefault("AllowCastToVoid", False)
    check = {"enabled": True, **({"options": options} if options else {})}
    value = {"version": "19.1.7", "scope_files": ["source.cpp"], "checks": {case["check"]: check}}
    selected = pack(tmp_path / "review.json", providers={"clang-tidy": value})
    arguments = clang_tidy_arguments(value)
    step = next(s for s in request["plan"]["recipe"]["steps"] if s["id"] == "tidy")
    step["argv"] = [a for a in step["argv"] if not a.startswith(("--checks=", "--config="))]
    where = step["argv"].index("--")
    step["argv"][where:where] = arguments
    step["inputs"].append("review.json")
    for context in request["contexts"]:
        if context["id"] == "tidy-context":
            from cppulse.identities import context_identity
            context["argv"] = step["argv"]
            context.update(context_identity(context))
    request["source"]["files"].append("review.json")
    request["ruleset"] = "review.json"
    return request, selected


@pytest.mark.parametrize("case_id", ["move-positive", "dangling-temporary-owner", "unused-void-false", "unused-void-true"])
def test_actual_provider_uses_resolved_pack_through_public_collector(tmp_path: Path, case_id: str) -> None:
    from test_collection import documents
    request, selected = _pack_request(tmp_path, case_id)
    original = deepcopy(request)
    result = collect_request(request, workspace=tmp_path, store=tmp_path / "store")
    assert request == original, "Explicit caller recipe is never silently rewritten"
    assert result["exit_code"] == (3 if case_id == "unused-void-true" else 0)
    pin = result["final_run"]
    snapshot = RunStore.open_existing(tmp_path / "store").open_run(pin["run_id"], manifest_sha256=pin["manifest_sha256"])
    facts = documents(snapshot, "external_analysis_facts")
    assert len(facts) == 1 and len(facts[0]["observations"]) == (0 if case_id == "unused-void-true" else 1)
    assert facts[0]["origin"] == "import" and facts[0]["scope_completeness"] == "unverified"
    assert facts[0]["receipt_id"] is None and facts[0]["proof_receipt_ids"] == []
    view = build_snapshot_view(snapshot)
    retained = view["configuration"]["document"]["resolved_ruleset"]
    assert retained["packs"][0]["raw_json"] == selected.read_text()
    assert view["assessment"] is None
    assert all(not group["independent_confirmation"] for group in view.get("external_relationships", []))
    selected.write_text(selected.read_text() + "\n")
    assert build_snapshot_view(snapshot)["configuration"]["document"]["resolved_ruleset"] == retained


@pytest.mark.parametrize("violation", ["scope", "version", "options", "alias", "response", "undeclared-pack", "generated-claim"])
def test_pack_recipe_mismatch_rejected_before_execution(tmp_path: Path, violation: str) -> None:
    request, _ = _pack_request(tmp_path, "unused-void-false")
    if violation == "scope": request["normalizers"][0]["scope_files"] = []
    elif violation == "version": request["normalizers"][0]["producer"]["version"] = "20"
    elif violation == "undeclared-pack": request["source"]["files"].remove("review.json")
    elif violation == "generated-claim": request["resolved_ruleset"] = {"digest": "forged"}
    else:
        argv = next(s for s in request["plan"]["recipe"]["steps"] if s["id"] == "tidy")["argv"]
        argv.insert(argv.index("--"), "@override.rsp" if violation == "response" else "-checks=*" if violation == "alias" else "--checks=*")
    with pytest.raises(ContractError):
        bind_collection_ruleset(request, tmp_path)
    assert not (tmp_path / "main.o").exists()


@pytest.mark.parametrize("stage", ["analyzer-core", "predictor"])
def test_container_entrypoints_forward_same_config_and_reject_profile_mismatch(tmp_path: Path, stage: str) -> None:
    """Real shell argv forwarding control; does not claim Docker/image execution."""
    root = Path(__file__).resolve().parents[1]
    exe = tmp_path / ("cppulse-analyzer" if stage == "analyzer-core" else "python3")
    exe.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    exe.chmod(0o755)
    env = {**os.environ, "PATH": str(tmp_path) + ":" + os.environ["PATH"],
           "CPPULSE_CONFIG": "/output/native.json", "CPPULSE_PROFILE": ""}
    result = subprocess.run(["sh", str(root / stage / "docker-entrypoint.sh"), "--output", "/output"], env=env, capture_output=True, text=True)
    assert result.returncode == 0
    args = result.stdout.splitlines()
    assert args[-2:] == ["--output", "/output"]
    assert args[args.index("--config") + 1] == "/output/native.json"
    assert "--profile" not in args
    env["CPPULSE_PROFILE"] = "safety-critical"
    assert subprocess.run(["sh", str(root / stage / "docker-entrypoint.sh")], env=env, capture_output=True).returncode == 2
    env["CPPULSE_PROFILE"] = ""
    env["CPPULSE_CONFIG"] = "relative.json"
    assert subprocess.run(["sh", str(root / stage / "docker-entrypoint.sh")], env=env, capture_output=True).returncode == 2
    repo = tmp_path / "repo"
    repo.mkdir()
    only = repo / ".cppulserc.yml"
    only.write_text("profile: safety-critical\n")
    env["CPPULSE_CONFIG"] = ""
    env["CPPULSE_REPO_ROOT"] = str(repo)
    discovered = subprocess.run(["sh", str(root / stage / "docker-entrypoint.sh")], env=env, capture_output=True, text=True)
    assert discovered.returncode == 0
    assert discovered.stdout.splitlines()[-2:] == ["--config", str(only)]
    (repo / ".cppulserc.json").write_text('{}')
    assert subprocess.run(["sh", str(root / stage / "docker-entrypoint.sh")], env=env, capture_output=True).returncode == 2


def test_actual_native_container_entrypoint_accepts_shared_resolved_config(tmp_path: Path) -> None:
    """Actual unchanged native binary, not the shell argv mock or a Docker claim."""
    from cppulse.predictor.main import _load_profile_from_config
    root = Path(__file__).resolve().parents[1]
    binary = Path(os.environ["CPPULSE_ANALYZER"]).resolve(strict=True)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.cpp").write_text("int value(int n) { if (n) return 1; return 0; }\n")
    selected = pack(repo / "review.json", native={"select": ["CPP-CX-001"], "rules": {
        "CPP-CX-001": {"warning_threshold": 0, "error_threshold": 100}}})
    config = effective_config(repo, tmp_path / "out", ruleset=selected, profile="safety-critical")
    settings = tmp_path / "native.json"
    settings.write_text(json.dumps(config.settings))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "cppulse-analyzer").symlink_to(binary)
    env = {**os.environ, "PATH": str(bin_dir) + ":" + os.environ["PATH"],
           "CPPULSE_CONFIG": str(settings), "CPPULSE_PROFILE": "", "CPPULSE_REPO_ROOT": str(repo)}
    output = tmp_path / "native-out"
    argv = ["sh", str(root / "analyzer-core/docker-entrypoint.sh"), "--repo", str(repo), "--output", str(output),
            "--resource-dir", os.environ["CPPULSE_CLANG_RESOURCE_DIR"]]
    result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    raw = json.loads((output / "findings.json").read_bytes())
    assert len(raw["findings"]) == 1 and raw["findings"][0]["rule_id"] == "CPP-CX-001"
    assert _load_profile_from_config(settings) == "safety-critical"
    assert config.settings["profile"] == "safety-critical"
    invalid = tmp_path / "invalid-profile.json"
    invalid.write_text(json.dumps({**config.settings, "profile": "unknown"}))
    bad_env = {**env, "CPPULSE_CONFIG": str(invalid)}
    bad_output = tmp_path / "invalid-native-out"
    bad_argv = [a if a != str(output) else str(bad_output) for a in argv]
    rejected = subprocess.run(bad_argv, env=bad_env, capture_output=True, text=True, timeout=30)
    assert rejected.returncode != 0 and not (bad_output / "findings.json").exists()
