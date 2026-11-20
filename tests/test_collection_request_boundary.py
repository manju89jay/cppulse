"""Independent static request boundary cases: no project commands are invoked."""

from __future__ import annotations

from copy import deepcopy
import subprocess
from typing import Any

import pytest

from cppulse.contracts import validate
from cppulse.errors import ContractError
from test_public_workflow_contracts import normalizer, request_document


@pytest.mark.parametrize(
    "case",
    [
        "input_role",
        "output_role",
        "step",
        "adapter_version",
        "unknown_field",
        "outcome",
        "duplicate_input",
        "zero_log",
        "large_log",
        "large_artifact",
        "zero_timeout",
        "too_many_jobs",
    ],
)
def test_declared_request_boundaries_are_checked_without_execution(
    case: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = request_document()
    request["normalizers"] = [normalizer("native_analysis")]
    item = request["normalizers"][0]
    if case == "input_role":
        item["registry"]["path"] = "unobserved.json"
    elif case == "output_role":
        item["report"]["path"] = "not-produced.json"
    elif case == "step":
        item["report"]["step_id"] = "not-declared"
    elif case == "adapter_version":
        item["normalizer_version"] = "2.0.0"
    elif case == "unknown_field":
        item["callback"] = "os.system"
    elif case == "outcome":
        item["outcome"] = "passed"
    elif case == "duplicate_input":
        request["plan"]["recipe"]["steps"][0]["inputs"] *= 2
    elif case == "zero_log":
        request["plan"]["limits"]["max_log_bytes"] = 0
    elif case == "large_log":
        request["plan"]["limits"]["max_log_bytes"] = 67108865
    elif case == "large_artifact":
        request["plan"]["limits"]["max_artifact_bytes"] = 268435457
    elif case == "zero_timeout":
        request["plan"]["recipe"]["steps"][0]["timeout_seconds"] = 0
    else:
        request["plan"]["recipe"]["jobs"] = 33

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Contract checking must not launch a process")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    with pytest.raises(ContractError):
        validate("collection_request", request)


def test_schema_valid_integral_float_limits_are_not_rewritten() -> None:
    request = request_document()
    for key in ["max_log_bytes", "max_artifact_bytes", "max_metadata_bytes"]:
        request["plan"]["limits"][key] = float(request["plan"]["limits"][key])
    before = deepcopy(request)
    validate("collection_request", request)
    assert request == before
    assert isinstance(request["plan"]["limits"]["max_log_bytes"], float)


def test_profile_binary_must_be_the_declared_exercised_test_input() -> None:
    request = request_document()
    item = normalizer("coverage")
    item["profiles"][0]["binary"] = {
        "step_id": "compile",
        "role": "output",
        "path": "build/main.o",
    }
    request["normalizers"] = [item]
    with pytest.raises(ContractError):
        validate("collection_request", request)
