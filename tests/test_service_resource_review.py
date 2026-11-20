"""Independent finite OS-limit receipt controls, without aggregate claims."""

from copy import deepcopy

import pytest

from cppulse.errors import ContractError
from cppulse.service_resources import validate_resource_receipt


def receipt():
    selected = {"cpu_seconds": None, "address_space_bytes": None}
    value = {
        "version": "1.0.0",
        "scope": "linux-per-process-inherited-rlimit",
        "pid": 123,
        "step_id": "probe",
        "argv": ["/selected/probe"],
        "requested": deepcopy(selected),
        "inherited": {"cpu_seconds": [-1, -1], "address_space_bytes": [-1, -1]},
        "actual": {"cpu_seconds": [-1, -1], "address_space_bytes": [-1, -1]},
        "status": "applied",
        "reason": "",
    }
    return value, selected


@pytest.mark.parametrize(
    "field,pair",
    [
        ("cpu_seconds", [2, 1]),
        ("cpu_seconds", [-1, 2]),
        ("address_space_bytes", [67108864, 33554432]),
        ("address_space_bytes", [-1, 33554432]),
    ],
)
def test_observed_limit_pairs_cannot_have_soft_above_hard(field, pair):
    value, selected = receipt()
    value["inherited"][field] = pair
    value["actual"][field] = pair
    with pytest.raises(ContractError):
        validate_resource_receipt(value, selected)


@pytest.mark.parametrize("pair", [[-1, -1], [0, -1], [1, -1], [1, 2], [0, 0]])
def test_inherited_os_limit_ordering_preserves_valid_unlimited_cases(pair):
    value, selected = receipt()
    for key in ("inherited", "actual"):
        value[key]["cpu_seconds"] = pair
    validate_resource_receipt(value, selected)


@pytest.fixture(scope="module")
def observed_pair(tmp_path_factory):
    from cppulse.service_repair import verify_service_proposal
    from tests.test_service_repair import _request

    root = tmp_path_factory.mktemp("resource-review-pair")
    selected = _request(root)
    selected.update(version="0.2.0", profile="cpp17-elf-relink-loopback-v2")
    selected["process_resources"] = {
        "build": {"cpu_seconds": [30, 40], "address_space_bytes": 1073741824},
        "test": {"cpu_seconds": [5, 10], "address_space_bytes": 268435456},
    }
    output = root / "attempt"
    result = verify_service_proposal(selected, output, execute_trusted_project=True)
    assert result["status"] == "verified_finite_regression"
    return selected, result, output


def test_resource_receipt_from_another_step_cannot_verify_selected_process(
    observed_pair, tmp_path
):
    import os
    import shutil
    from cppulse.identities import canonical_json_bytes
    from cppulse.service_repair import _fact, validate_report

    selected, original, original_root = observed_pair
    validate_report(selected, original, original_root)
    root = tmp_path / "view"
    shutil.copytree(original_root, root, copy_function=os.link)
    report = deepcopy(original)
    steps = {row["id"]: row for row in report["steps"]}
    names = ("before-compile", "after-compile")
    content = [
        (root / steps[name]["resource_receipt"]["path"]).read_bytes() for name in names
    ]
    assert content[0] != content[1]
    updated = set()
    for name, raw in zip(names, reversed(content)):
        path = root / steps[name]["resource_receipt"]["path"]
        path.unlink()
        path.write_bytes(raw)
        steps[name]["resource_receipt"] = _fact(path, root)
        updated.add(path.relative_to(root).as_posix())
        progress = root / (
            "progress-" + str(report["steps"].index(steps[name]) + 1) + ".json"
        )
        progress.unlink()
        progress.write_bytes(canonical_json_bytes(steps[name]))
        updated.add(progress.relative_to(root).as_posix())
    for artifact in report["artifacts"]:
        if artifact["path"] in updated:
            artifact.update(_fact(root / artifact["path"], root))
    with pytest.raises(ContractError):
        validate_report(selected, report, root)
    validate_report(selected, original, original_root)


def test_inspection_cannot_claim_a_build_test_resource_receipt(observed_pair, tmp_path):
    import os
    import shutil
    from cppulse.identities import canonical_json_bytes
    from cppulse.service_repair import _fact, validate_report

    selected, original, original_root = observed_pair
    validate_report(selected, original, original_root)
    root = tmp_path / "view"
    shutil.copytree(original_root, root, copy_function=os.link)
    report = deepcopy(original)
    inspection = report["steps"][0]
    build = report["steps"][1]
    destination = root / "logs/service-before.resources.json"
    destination.write_bytes((root / build["resource_receipt"]["path"]).read_bytes())
    inspection["resource_receipt"] = _fact(destination, root)
    progress = root / "progress-1.json"
    progress.unlink()
    progress.write_bytes(canonical_json_bytes(inspection))
    for artifact in report["artifacts"]:
        if artifact["path"] == "progress-1.json":
            artifact.update(_fact(progress, root))
    report["artifacts"].append(inspection["resource_receipt"])
    with pytest.raises(ContractError):
        validate_report(selected, report, root)
    validate_report(selected, original, original_root)
