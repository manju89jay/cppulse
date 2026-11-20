"""Versioned per-process limits; actual probes do not imply aggregate isolation."""

from copy import deepcopy

import pytest

from cppulse.service_repair import validate_request
from tests.test_service_repair import _request


@pytest.fixture(scope="module")
def resource_request(tmp_path_factory):
    request = _request(tmp_path_factory.mktemp("service-resource"))
    request.update(version="0.2.0", profile="cpp17-elf-relink-loopback-v2")
    request["process_resources"] = {
        "build": {"cpu_seconds": [30, 40], "address_space_bytes": 1073741824},
        "test": {"cpu_seconds": [1, 2], "address_space_bytes": 268435456},
    }
    return request


def test_new_resource_profile_has_a_distinct_valid_contract(resource_request):
    validate_request(resource_request)


@pytest.mark.parametrize("cpu", [[2, 1], [True, 2], [0, 1], [1, 3601]])
def test_resource_limits_reject_invalid_cpu_contract(resource_request, cpu):
    from cppulse.errors import ContractError

    request = deepcopy(resource_request)
    request["process_resources"]["test"]["cpu_seconds"] = cpu
    with pytest.raises(ContractError):
        validate_request(request)


@pytest.fixture(scope="module")
def native_probe(tmp_path_factory):
    import subprocess

    directory = tmp_path_factory.mktemp("resource-native")
    source = directory / "probe.cpp"
    source.write_text(
        r"""
#include <csignal>
#include <cstdlib>
#include <cstring>
#include <sys/resource.h>
#include <unistd.h>
static void soft(int) { _exit(78); }
int main(int argc,char** argv) {
 if(argc!=2) return 2;
 if(std::strcmp(argv[1],"memory")==0) {
  void* p=std::malloc(128UL*1024*1024);
  if(!p) return 42;
  static_cast<volatile char*>(p)[0]=1;
  std::free(p);return 0;
 }
 if(std::strcmp(argv[1],"soft")==0) std::signal(SIGXCPU,soft);
 else if(std::strcmp(argv[1],"hard")==0) std::signal(SIGXCPU,SIG_IGN);
 else return 2;
 for(;;) { asm volatile("" ::: "memory"); }
}
"""
    )
    executable = directory / "probe"
    subprocess.run(
        ["g++", "-std=c++17", "-O2", str(source), "-o", str(executable)], check=True
    )
    return executable


def observe(native_probe, tmp_path, requested, mode):
    import json
    import subprocess
    import sys
    from cppulse.service_repair import _EXEC_CLEAN
    from cppulse.service_resources import RESOURCE_EXEC, validate_resource_receipt

    receipt = tmp_path / "resources.json"
    command = [
        sys.executable,
        "-I",
        "-c",
        RESOURCE_EXEC + _EXEC_CLEAN,
        json.dumps(requested),
        str(receipt),
        "probe",
        str(native_probe),
        mode,
    ]
    result = subprocess.run(command, capture_output=True, timeout=10)
    document = json.loads(receipt.read_bytes())
    validate_resource_receipt(document, requested)
    (tmp_path / "command.json").write_text(json.dumps(command))
    (tmp_path / "stdout").write_bytes(result.stdout)
    (tmp_path / "stderr").write_bytes(result.stderr)
    return result, document


@pytest.mark.parametrize("mode,expected", [("soft", 78), ("hard", -9)])
def test_actual_cpu_soft_handler_and_hard_limit(native_probe, tmp_path, mode, expected):
    result, receipt = observe(
        native_probe,
        tmp_path,
        {"cpu_seconds": [1, 2], "address_space_bytes": None},
        mode,
    )
    assert receipt["actual"]["cpu_seconds"] == [1, 2]
    assert result.returncode == expected


@pytest.mark.parametrize("address_space,expected", [(67108864, 42), (None, 0)])
def test_actual_address_space_failure_and_uncapped_control(
    native_probe, tmp_path, address_space, expected
):
    result, receipt = observe(
        native_probe,
        tmp_path,
        {"cpu_seconds": None, "address_space_bytes": address_space},
        "memory",
    )
    assert result.returncode == expected


def test_v2_actual_finite_pair_and_checked_resource_receipts(
    resource_request, tmp_path
):
    from cppulse.service_repair import verify_service_proposal, validate_report

    request = deepcopy(resource_request)
    request["process_resources"]["test"] = {
        "cpu_seconds": [5, 10],
        "address_space_bytes": 268435456,
    }
    output = tmp_path / "attempt"
    report = verify_service_proposal(request, output, execute_trusted_project=True)
    validate_report(request, report, output)
    assert report["status"] == "verified_finite_regression"
    assert len(report["steps"]) == 10
    assert all(
        row["resource_receipt"] is not None
        for row in report["steps"]
        if not row["id"].startswith("service-")
    )
    assert all(
        row["resource_receipt"] is None
        for row in report["steps"]
        if row["id"].startswith("service-")
    )


def test_failed_resource_setup_never_executes_selected_project(native_probe, tmp_path):
    import json
    import subprocess
    import sys
    from cppulse.service_repair import _EXEC_CLEAN
    from cppulse.service_resources import RESOURCE_EXEC, validate_resource_receipt
    from cppulse.errors import ContractError

    receipt = tmp_path / "resources.json"
    requested = {"cpu_seconds": [2, 2], "address_space_bytes": None}
    # Restrict only this owned child; a later request cannot raise its hard cap.
    code = (
        "import resource;resource.setrlimit(resource.RLIMIT_CPU,(1,1));\n"
        + RESOURCE_EXEC
        + _EXEC_CLEAN
    )
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            code,
            json.dumps(requested),
            str(receipt),
            "probe",
            str(native_probe),
            "memory",
        ],
        capture_output=True,
        timeout=10,
    )
    document = json.loads(receipt.read_bytes())
    assert result.returncode == 125
    assert document["status"] == "setup_failed"
    assert (
        document["inherited"]["cpu_seconds"]
        == document["actual"]["cpu_seconds"]
        == [1, 1]
    )
    assert document["reason"]
    with pytest.raises(ContractError, match="not applied"):
        validate_resource_receipt(document, requested)


@pytest.mark.parametrize(
    "mutation",
    ["actual", "requested", "requested-bool", "reason", "malformed", "pid", "scope"],
)
def test_resource_receipt_rejects_inconsistent_observations(mutation):
    from cppulse.errors import ContractError
    from cppulse.service_resources import validate_resource_receipt

    requested = {"cpu_seconds": [1, 2], "address_space_bytes": 67108864}
    receipt = {
        "version": "1.0.0",
        "scope": "linux-per-process-inherited-rlimit",
        "pid": 123,
        "step_id": "probe",
        "argv": ["/selected/probe"],
        "requested": deepcopy(requested),
        "inherited": {"cpu_seconds": [-1, -1], "address_space_bytes": [-1, -1]},
        "actual": {"cpu_seconds": [1, 2], "address_space_bytes": [67108864, 67108864]},
        "status": "applied",
        "reason": "",
    }
    validate_resource_receipt(receipt, requested)
    if mutation == "actual":
        receipt["actual"]["address_space_bytes"] = [-1, -1]
    elif mutation == "requested":
        receipt["requested"]["cpu_seconds"] = [3, 4]
    elif mutation == "requested-bool":
        receipt["requested"]["cpu_seconds"] = [True, 2]
    elif mutation == "reason":
        receipt["reason"] = {}
    elif mutation == "malformed":
        receipt["inherited"] = []
    elif mutation == "pid":
        receipt["pid"] = True
    else:
        receipt["scope"] = "cgroup-aggregate"
    with pytest.raises(ContractError):
        validate_resource_receipt(receipt, requested)


@pytest.mark.parametrize("raw", ["[]", "null", '"bad"'])
def test_schema_dispatch_refuses_non_object_json_without_traceback(tmp_path, raw):
    from cppulse.service_repair import main

    request = tmp_path / "request.json"
    request.write_text(raw)
    output = tmp_path / "attempt"
    assert (
        main(
            [
                "--request",
                str(request),
                "--output",
                str(output),
                "--execute-trusted-project",
            ]
        )
        == 2
    )
    assert not output.exists()
