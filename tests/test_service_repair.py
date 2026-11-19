"""Separate trusted ELF lane: real tools, explicit synthetic service inspector.

The controlled inspector tests contract/supervision behavior. Actual MongoDB/Poco
observations live in the source-bound checkpoint and are not inferred from these
fixtures. No test changes the ordinary semantic-repair profile.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from cppulse.errors import ContractError, IntegrityError
from cppulse.execution import CancellationToken
from cppulse.service_repair import (
    _cases,
    _service,
    main,
    validate_report,
    validate_request,
    verify_service_proposal,
)


def pin(path: Path) -> dict:
    path = path.resolve()
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": path.stat().st_size,
    }


def _request(tmp_path: Path) -> dict:
    before = tmp_path / "before.cpp"
    after = tmp_path / "after.cpp"
    before.write_text('extern "C" int value() { return 0; }\n')
    after.write_text('extern "C" int value() { return 1; }\n')
    helper = tmp_path / "helper.cpp"
    helper.write_text('extern "C" int preserved() { return 7; }\n')
    obj = tmp_path / "helper.o"
    subprocess.run(["g++", "-fPIC", "-c", str(helper), "-o", str(obj)], check=True)
    dep_source = tmp_path / "dependency.cpp"
    dep_source.write_text('extern "C" int dependency() { return 3; }\n')
    dep = tmp_path / "libdependency.so.1"
    subprocess.run(
        [
            "g++",
            "-fPIC",
            "-shared",
            "-Wl,-soname,libdependency.so.1",
            str(dep_source),
            "-o",
            str(dep),
        ],
        check=True,
    )
    header = tmp_path / "expected.h"
    header.write_text("#define EXPECTED 1\n")
    probe = tmp_path / "probe.cpp"
    probe.write_text(
        r"""#include <cstdio>
#include "expected.h"
extern "C" int value();
extern "C" int preserved();
extern "C" int dependency();
int main(int argc, char** argv) {
 if(argc!=2) return 2;
 const bool behavior = value()==EXPECTED;
 const bool object = preserved()==7;
 const bool dep = dependency()==3;
 std::printf("{\"namespace\":\"%s\",\"cases\":{\"behavior\":%s,\"object\":%s,\"dependency\":%s},\"observations\":{}}\n",argv[1],behavior?"true":"false",object?"true":"false",dep?"true":"false");
 return behavior&&object&&dep?0:1;
}
"""
    )
    inspected = [
        {
            "Id": "1" * 64,
            "Image": "sha256:" + "2" * 64,
            "State": {"Running": True},
            "Config": {
                "Labels": {
                    "cppulse.task": "synthetic-unit-test",
                    "cppulse.fixture": "controlled-inspector",
                }
            },
            "NetworkSettings": {
                "Ports": {"27017/tcp": [{"HostIp": "127.0.0.1", "HostPort": "27017"}]}
            },
        }
    ]
    docker = tmp_path / "controlled-inspector"
    docker.write_text(
        "#!"
        + str(Path(sys.executable).resolve())
        + "\nprint("
        + repr(json.dumps(inspected))
        + ")\n"
    )
    docker.chmod(0o700)
    return {
        "version": "0.1.0",
        "profile": "cpp17-elf-relink-loopback-v1",
        "compiler": pin(Path("/usr/bin/g++")),
        "compiler_search_prefix": "/usr/libexec/gcc/x86_64-linux-gnu/14/",
        "compiler_library_prefix": "/usr/lib/gcc/x86_64-linux-gnu/14/",
        "compiler_system_include_directories": [
            "/usr/include/c++/14",
            "/usr/include/x86_64-linux-gnu/c++/14",
            "/usr/include/c++/14/backward",
            "/usr/lib/gcc/x86_64-linux-gnu/14/include",
            "/usr/include/x86_64-linux-gnu",
            "/usr/include",
        ],
        "docker": pin(docker),
        "supervisor_python": pin(Path("/usr/bin/python3")),
        "before_source": pin(before),
        "after_source": pin(after),
        "probe": pin(probe),
        "headers": [{"name": "expected.h", "file": pin(header)}],
        "objects": [{"name": "helper.o", "file": pin(obj)}],
        "libraries": [{"name": "libdependency.so.1", "file": pin(dep)}],
        "defines": [],
        "soname": "libselected.so.1",
        "required_cases": ["behavior", "object", "dependency"],
        "service": {
            "container_id": "1" * 64,
            "image_id": "sha256:" + "2" * 64,
            "host": "127.0.0.1",
            "port": 27017,
            "container_port": 27017,
            "task_label": "synthetic-unit-test",
            "fixture_label": "controlled-inspector",
        },
        "limits": {
            "step_wall_seconds": 10,
            "log_bytes": 16384,
            "input_bytes": 128 * 1024**2,
        },
    }


@pytest.fixture
def service_request(tmp_path: Path) -> dict:
    return _request(tmp_path)


@pytest.fixture(scope="module")
def verified(tmp_path_factory) -> tuple[dict, Path]:
    tmp_path = tmp_path_factory.mktemp("shared-actual-elf")
    service_request = _request(tmp_path)
    root = tmp_path / "verified"
    report = verify_service_proposal(
        service_request, root, execute_trusted_project=True
    )
    assert report["status"] == "verified_finite_regression"
    return report, root


def test_actual_disjoint_relink_and_finite_failure_pair(service_request, verified):
    report, root = verified
    service_request = json.loads((root / "request.json").read_bytes())
    validate_report(service_request, report, root)
    assert len(report["steps"]) == 10
    assert report["steps"][4]["outcome"]["returncode"] == 1
    assert report["steps"][8]["outcome"]["returncode"] == 0
    assert report["qualification"]["semantic_equivalence_established"] is False
    assert report["qualification"]["cpu_enforced"] is False
    assert report["qualification"]["memory_enforced"] is False
    for key in ("before_source", "after_source", "probe"):
        assert pin(Path(service_request[key]["path"])) == service_request[key]


def test_missing_explicit_execution_never_creates_output(service_request, tmp_path):
    output = tmp_path / "refused"
    with pytest.raises(ContractError, match="explicit trusted"):
        verify_service_proposal(service_request, output)
    assert not output.exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "parent",
        "absolute",
        "duplicate",
        "same_source",
        "duplicate_case",
        "limit",
        "soname_dependency",
    ],
)
def test_request_rejects_ambiguous_scope(service_request, mutation):
    if mutation == "parent":
        service_request["headers"][0]["name"] = "../expected.h"
    elif mutation == "absolute":
        service_request["headers"][0]["name"] = "/expected.h"
    elif mutation == "duplicate":
        service_request["headers"].append(deepcopy(service_request["headers"][0]))
    elif mutation == "same_source":
        service_request["after_source"] = deepcopy(service_request["before_source"])
    elif mutation == "duplicate_case":
        service_request["required_cases"].append("behavior")
    elif mutation == "limit":
        service_request["limits"]["input_bytes"] = 1
    else:
        service_request["soname"] = "libdependency.so.1"
    with pytest.raises(ContractError):
        validate_request(service_request)


def test_stale_input_refused_before_output(service_request, tmp_path):
    Path(service_request["after_source"]["path"]).write_text("stale")
    output = tmp_path / "refused"
    with pytest.raises(IntegrityError, match="stale"):
        verify_service_proposal(service_request, output, execute_trusted_project=True)
    assert not output.exists()


def test_symlink_material_refused_without_touching_target(service_request, tmp_path):
    source = Path(service_request["after_source"]["path"])
    link = tmp_path / "link.cpp"
    link.symlink_to(source)
    service_request["after_source"]["path"] = str(link)
    with pytest.raises(IntegrityError):
        verify_service_proposal(
            service_request, tmp_path / "refused", execute_trusted_project=True
        )
    assert pin(source)["sha256"] == service_request["after_source"]["sha256"]


def test_existing_output_preserved(service_request, tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    (output / "victim").write_text("preserved")
    with pytest.raises(FileExistsError):
        verify_service_proposal(service_request, output, execute_trusted_project=True)
    assert (output / "victim").read_text() == "preserved"


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_step",
        "command",
        "truncated",
        "input_hash",
        "raw_log",
        "compiled_artifact",
        "cpu_claim",
    ],
)
def test_replayed_metadata_cannot_replace_retained_observations(
    service_request, verified, mutation
):
    report, root = verified
    service_request = json.loads((root / "request.json").read_bytes())
    forged = deepcopy(report)
    if mutation == "missing_step":
        forged["steps"].pop()
    elif mutation == "command":
        forged["steps"][1]["argv"].append("-DOTHER=1")
    elif mutation == "truncated":
        forged["steps"][4]["outcome"]["stdout_bytes"] += 1
    elif mutation == "input_hash":
        forged["artifacts"][0]["sha256"] = "0" * 64
    elif mutation == "raw_log":
        forged["steps"][4]["stdout"] = deepcopy(forged["steps"][8]["stdout"])
    elif mutation == "compiled_artifact":
        forged["artifacts"] = [
            row for row in forged["artifacts"] if row["path"] != "after/probe"
        ]
    else:
        forged["qualification"]["cpu_enforced"] = True
    with pytest.raises((ContractError, IntegrityError)):
        validate_report(service_request, forged, root)


@pytest.mark.parametrize(
    "mutation", ["foreign_image", "stopped", "public_port", "wrong_owner", "bad_shape"]
)
def test_real_inspect_shape_requires_exact_owned_loopback_identity(
    service_request, mutation
):
    raw = subprocess.check_output([service_request["docker"]["path"]])
    value = json.loads(raw)
    if mutation == "foreign_image":
        value[0]["Image"] = "sha256:" + "3" * 64
    elif mutation == "stopped":
        value[0]["State"]["Running"] = False
    elif mutation == "public_port":
        value[0]["NetworkSettings"]["Ports"]["27017/tcp"][0]["HostIp"] = "0.0.0.0"
    elif mutation == "wrong_owner":
        value[0]["Config"]["Labels"]["cppulse.task"] = "other-task"
    else:
        value[0]["State"] = None
    with pytest.raises(ContractError):
        _service(json.dumps(value).encode(), service_request)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"namespace":"x","namespace":"x","cases":{},"observations":{}}',
        b'{"namespace":"x","cases":{"behavior":1},"observations":{}}',
        b'{"namespace":"x","cases":{},"observations":{"number":NaN}}',
        b'{"namespace":"x","cases":{"behavior":true,"object":true,"dependency":true},"observations":{"number":1e400}}',
    ],
)
def test_duplicate_nonfinite_and_incomplete_probe_is_unknown(service_request, raw):
    with pytest.raises(ContractError):
        _cases(raw, service_request, "x")


def test_clean_before_is_not_a_verified_repair(service_request, tmp_path):
    before = Path(service_request["before_source"]["path"])
    before.write_text(
        Path(service_request["after_source"]["path"]).read_text()
        + "// different bytes\n"
    )
    service_request["before_source"] = pin(before)
    report = verify_service_proposal(
        service_request, tmp_path / "clean-before", execute_trusted_project=True
    )
    assert report["status"] == "incomplete"
    assert any("genuine finite failure" in item for item in report["failures"])


def test_after_compile_failure_preserves_before_and_raw_failure(
    service_request, tmp_path
):
    after = Path(service_request["after_source"]["path"])
    after.write_text("invalid C++ source")
    service_request["after_source"] = pin(after)
    output = tmp_path / "failed-after"
    report = verify_service_proposal(
        service_request, output, execute_trusted_project=True
    )
    assert report["status"] == "incomplete"
    assert report["steps"][4]["outcome"]["returncode"] == 1
    assert report["steps"][5]["outcome"]["status"] == "failed"
    assert (output / "logs/after-compile.stderr").stat().st_size > 0
    assert (output / "report.json").is_file()


@pytest.mark.parametrize("failure", ["timeout", "log_limit", "runtime_failure"])
def test_actual_runtime_failures_remain_incomplete(service_request, tmp_path, failure):
    if failure == "runtime_failure":
        source = Path(service_request["after_source"]["path"])
        source.write_text('extern "C" int value() { return 2; }\n')
        service_request["after_source"] = pin(source)
    else:
        probe = Path(service_request["probe"]["path"])
        text = probe.read_text()
        if failure == "timeout":
            text = "#include <unistd.h>\n" + text
            text = text.replace(
                "if(argc!=2) return 2;", "if(argc!=2) { return 2; }\n sleep(10);"
            )
            service_request["limits"]["step_wall_seconds"] = 1
        else:
            text = text.replace(
                "if(argc!=2) return 2;",
                "if(argc!=2) { return 2; }\n for(int i=0;i<20000;++i) { std::putchar(88); }",
            )
            service_request["limits"]["log_bytes"] = 1024
        probe.write_text(text)
        service_request["probe"] = pin(probe)
    output = tmp_path / failure
    report = verify_service_proposal(
        service_request, output, execute_trusted_project=True
    )
    assert report["status"] == "incomplete"
    if failure == "timeout":
        assert report["steps"][-1]["outcome"]["status"] == "timed_out"
    elif failure == "log_limit":
        assert report["steps"][4]["outcome"]["stdout_bytes"] > 1024
        assert report["steps"][4]["stdout"]["size_bytes"] == 1024
    else:
        assert report["steps"][8]["outcome"]["returncode"] == 1
    validate_report(service_request, report, output)


def test_cancellation_retains_unstarted_attempt_without_receipts(
    service_request, tmp_path
):
    token = CancellationToken()
    token.cancel()
    output = tmp_path / "cancelled"
    report = verify_service_proposal(
        service_request, output, execute_trusted_project=True, cancel=token
    )
    assert report["status"] == "incomplete" and report["steps"] == []
    assert (output / "inputs/before/source.cpp").is_file()
    assert (output / "report.json").is_file()


def test_cli_opt_in_and_strict_request_boundary(service_request, tmp_path):
    selected = tmp_path / "service_request.json"
    selected.write_text(json.dumps(service_request))
    output = tmp_path / "no-implicit-execution"
    assert main(["--request", str(selected), "--output", str(output)]) == 2
    assert not output.exists()
    selected.write_text('{"version":"0.1.0","version":"0.1.0"}')
    assert (
        main(
            [
                "--request",
                str(selected),
                "--output",
                str(output),
                "--execute-trusted-project",
            ]
        )
        == 2
    )
    assert not output.exists()
